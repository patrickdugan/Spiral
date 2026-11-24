// Host bridge for the pinned Vortex Blake2s kernels. One call handles one disk batch.
#include <cuda_runtime.h>
#include <cstdint>
#include <vector>

extern "C" void cuda_build_leaves_lifted(const uint32_t* const*, const void*, uint32_t,
                                         uint32_t, uint32_t*, uint32_t);
extern "C" void cuda_merkle_hash_nodes(const uint32_t*, uint32_t*, uint32_t);

namespace {

constexpr uint32_t max_columns = 1 << 14;
constexpr uint32_t max_batch_log = 13;
constexpr size_t max_words = 1 << 24;
constexpr size_t hash_bytes = 32;

struct LeafChunk {
    uint32_t indices[16];
    uint32_t count;
    uint32_t log_size;
};

static_assert(sizeof(LeafChunk) == 72);

template <typename T>
class DeviceBuffer {
public:
    T* value = nullptr;

    DeviceBuffer() = default;
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
    ~DeviceBuffer() { if (value) cudaFree(value); }

    cudaError_t allocate(size_t count) {
        void* raw = nullptr;
        const auto status = cudaMalloc(&raw, count * sizeof(T));
        if (status == cudaSuccess) value = static_cast<T*>(raw);
        return status;
    }

    cudaError_t upload(const T* host, size_t count) {
        const auto status = allocate(count);
        if (status != cudaSuccess) return status;
        return cudaMemcpy(value, host, count * sizeof(T), cudaMemcpyHostToDevice);
    }
};

cudaError_t download(uint8_t* host, const void* device, size_t bytes) {
    auto status = cudaGetLastError();
    if (status != cudaSuccess) return status;
    status = cudaDeviceSynchronize();
    if (status != cudaSuccess) return status;
    return cudaMemcpy(host, device, bytes, cudaMemcpyDeviceToHost);
}

} // namespace

extern "C" int pg_disk_merkle_abi() { return 1; }

extern "C" int pg_disk_merkle_leaves(const uint32_t* words, size_t word_count,
                                      const uint32_t* column_logs, uint32_t column_count,
                                      uint32_t batch_log, uint8_t* hashes) {
    if (!words || !column_logs || !hashes || !word_count || word_count > max_words
        || !column_count || column_count > max_columns || !batch_log || batch_log > max_batch_log) {
        return cudaErrorInvalidValue;
    }

    try {
        std::vector<LeafChunk> chunks;
        std::vector<const uint32_t*> pointers;
        pointers.reserve(column_count);
        DeviceBuffer<uint32_t> values, output;
        auto status = values.allocate(word_count);
        if (status != cudaSuccess) return status;
        size_t offset = 0;
        for (uint32_t col = 0; col < column_count; ++col) {
            const uint32_t height = column_logs[col];
            if (!height || height > batch_log || offset + (size_t{1} << height) > word_count) {
                return cudaErrorInvalidValue;
            }
            if (chunks.empty() || chunks.back().log_size != height || chunks.back().count == 16) {
                chunks.push_back(LeafChunk{{}, 0, height});
            }
            auto& chunk = chunks.back();
            chunk.indices[chunk.count++] = col;
            pointers.push_back(values.value + offset);
            offset += size_t{1} << height;
        }
        if (offset != word_count) return cudaErrorInvalidValue;
        status = cudaMemcpy(values.value, words, word_count * sizeof(uint32_t), cudaMemcpyHostToDevice);
        if (status != cudaSuccess) return status;
        DeviceBuffer<const uint32_t*> columns;
        DeviceBuffer<LeafChunk> schedule;
        status = columns.upload(pointers.data(), pointers.size());
        if (status != cudaSuccess) return status;
        status = schedule.upload(chunks.data(), chunks.size());
        if (status != cudaSuccess) return status;
        const uint32_t count = 1U << batch_log;
        status = output.allocate(count * (hash_bytes / sizeof(uint32_t)));
        if (status != cudaSuccess) return status;
        cuda_build_leaves_lifted(columns.value, schedule.value, chunks.size(), batch_log, output.value, count);
        return download(hashes, output.value, count * hash_bytes);
    } catch (...) {
        return cudaErrorMemoryAllocation;
    }
}

extern "C" int pg_disk_merkle_parents(const uint8_t* children, uint32_t count, uint8_t* hashes) {
    if (!children || !hashes || !count || count > (1U << max_batch_log)) return cudaErrorInvalidValue;
    DeviceBuffer<uint8_t> input, output;
    auto status = input.upload(children, count * 2 * hash_bytes);
    if (status != cudaSuccess) return status;
    status = output.allocate(count * hash_bytes);
    if (status != cudaSuccess) return status;
    cuda_merkle_hash_nodes(reinterpret_cast<const uint32_t*>(input.value),
                          reinterpret_cast<uint32_t*>(output.value), count);
    return download(hashes, output.value, count * hash_bytes);
}
