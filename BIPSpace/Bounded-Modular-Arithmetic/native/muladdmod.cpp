// Research reference, not a Bitcoin Core patch. All operands are public.
// Independent bit-serial multiplication; no bignum library or integer division.
#include <array>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Word = std::array<std::uint8_t, 33>;
using Bytes = std::vector<std::uint8_t>;

static bool ge(const Word& a, const Word& b, std::size_t n) {
    for (std::size_t i = n; i-- > 0;) {
        if (a[i] != b[i]) return a[i] > b[i];
    }
    return true;
}

static Word addmod(const Word& a, const Word& b, const Word& m, std::size_t w) {
    Word r{};
    unsigned carry = 0;
    for (std::size_t i = 0; i <= w; ++i) {
        unsigned v = static_cast<unsigned>(a[i]) + b[i] + carry;
        r[i] = static_cast<std::uint8_t>(v & 255U);
        carry = v >> 8;
    }
    if (carry != 0) throw std::logic_error("addition bound");
    // Since a,b < m, their sum is < 2m. At most one subtraction is needed.
    if (ge(r, m, w + 1)) {
        int borrow = 0;
        for (std::size_t i = 0; i <= w; ++i) {
            int v = static_cast<int>(r[i]) - m[i] - borrow;
            borrow = v < 0 ? 1 : 0;
            if (borrow) v += 256;
            r[i] = static_cast<std::uint8_t>(v);
        }
        if (borrow) throw std::logic_error("subtraction bound");
    }
    return r;
}

static Bytes calculate(const Bytes& a, const Bytes& b, const Bytes& c, const Bytes& m) {
    const std::size_t w = m.size();
    if (w < 1 || w > 32 || m.back() == 0 || (w == 1 && m[0] < 2))
        throw std::invalid_argument("modulus");
    if (a.size() != w || b.size() != w || c.size() != w)
        throw std::invalid_argument("width");
    Word aa{}, bb{}, cc{}, mm{};
    for (std::size_t i = 0; i < w; ++i) {
        aa[i] = a[i]; bb[i] = b[i]; cc[i] = c[i]; mm[i] = m[i];
    }
    if (ge(aa, mm, w) || ge(bb, mm, w) || ge(cc, mm, w))
        throw std::invalid_argument("residue");
    Word r = cc, x = aa;
    for (std::size_t i = 0; i < 8 * w; ++i) {
        if ((bb[i / 8] >> (i % 8)) & 1U) r = addmod(r, x, mm, w);
        x = addmod(x, x, mm, w);
    }
    return Bytes(r.begin(), r.begin() + static_cast<std::ptrdiff_t>(w));
}

static Bytes unhex(const std::string& s) {
    if (s == "-") return {};
    if (s.size() % 2 != 0 || s.size() > 1040) throw std::invalid_argument("hex length");
    auto nibble = [](char c) -> unsigned {
        if (c >= '0' && c <= '9') return static_cast<unsigned>(c - '0');
        if (c >= 'a' && c <= 'f') return static_cast<unsigned>(c - 'a' + 10);
        if (c >= 'A' && c <= 'F') return static_cast<unsigned>(c - 'A' + 10);
        throw std::invalid_argument("hex digit");
    };
    Bytes out;
    for (std::size_t i = 0; i < s.size(); i += 2)
        out.push_back(static_cast<std::uint8_t>(16 * nibble(s[i]) + nibble(s[i + 1])));
    return out;
}

int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--bench") {
        constexpr unsigned repeats = 4000;
        for (std::size_t w : {1U, 4U, 8U, 16U, 32U}) {
            Bytes m(w, 255), a(w, 255), b(w, 255), c(w, 255);
            a[0] = b[0] = c[0] = 254;
            std::uint64_t checksum = 0;
            auto start = std::chrono::steady_clock::now();
            for (unsigned i = 0; i < repeats; ++i) {
                a[0] = static_cast<std::uint8_t>(i % 128);
                Bytes r = calculate(a, b, c, m);
                checksum += r[0];
            }
            double ns = std::chrono::duration<double, std::nano>(
                std::chrono::steady_clock::now() - start).count() / repeats;
            std::cout << w << " " << std::fixed << std::setprecision(2)
                      << ns << " " << checksum << "\n";
        }
        return 0;
    }
    if (argc != 1) return 2;
    std::string line;
    while (std::getline(std::cin, line)) {
        try {
            std::istringstream input(line);
            std::string a, b, c, m, extra;
            if (!(input >> a >> b >> c >> m) || (input >> extra))
                throw std::invalid_argument("four operands required");
            Bytes r = calculate(unhex(a), unhex(b), unhex(c), unhex(m));
            std::cout << "OK ";
            for (auto v : r) std::cout << std::hex << std::setw(2)
                << std::setfill('0') << static_cast<unsigned>(v);
            std::cout << std::dec << "\n";
        } catch (const std::invalid_argument&) {
            std::cout << "ERR\n";
        }
    }
}
