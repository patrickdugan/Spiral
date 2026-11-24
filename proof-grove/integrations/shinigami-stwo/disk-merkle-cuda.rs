//! Optional CUDA bridge for stock Blake2s disk commitments.

use std::ffi::{c_char, c_int, c_void, CStr, CString};
use std::io;
use std::os::unix::ffi::OsStrExt;
use std::path::Path;
use std::ptr::NonNull;

const HASH_BYTES: usize = 32;
const MAX_COLUMNS: usize = 1 << 14;
const MAX_WORDS: usize = 1 << 24;

type Leaves = unsafe extern "C" fn(*const u32, usize, *const u32, u32, u32, *mut u8) -> c_int;
type Parents = unsafe extern "C" fn(*const u8, u32, *mut u8) -> c_int;

#[link(name = "dl")]
extern "C" {
    fn dlopen(filename: *const c_char, flags: c_int) -> *mut c_void;
    fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
    fn dlclose(handle: *mut c_void) -> c_int;
}

struct Library(NonNull<c_void>);

impl Library {
    fn symbol(&self, name: &CStr) -> io::Result<NonNull<c_void>> {
        // The absolute library path and the three C signatures are part of the pinned bridge ABI.
        NonNull::new(unsafe { dlsym(self.0.as_ptr(), name.as_ptr()) })
            .ok_or_else(|| io::Error::other(format!("missing CUDA disk Merkle symbol {name:?}")))
    }
}

impl Drop for Library {
    fn drop(&mut self) {
        unsafe { dlclose(self.0.as_ptr()) };
    }
}

pub(super) struct CudaDiskMerkle {
    _library: Library,
    leaves: Leaves,
    parents: Parents,
    words: Vec<u32>,
    column_logs: Vec<u32>,
}

impl CudaDiskMerkle {
    pub(super) fn leaf_batch_size(mut nodes: usize, shifts: &[u32]) -> io::Result<usize> {
        if shifts.len() > MAX_COLUMNS {
            return Err(io::Error::other("CUDA disk Merkle tree has too many columns"));
        }
        while shifts.iter().map(|&shift| (nodes >> shift).max(2)).sum::<usize>() > MAX_WORDS {
            nodes /= 2;
        }
        Ok(nodes)
    }

    pub(super) fn from_environment() -> io::Result<Option<Self>> {
        let Some(path) = std::env::var_os("STWO_CUDA_DISK_MERKLE_LIBRARY") else {
            return Ok(None);
        };
        if !Path::new(&path).is_absolute() {
            return Err(io::Error::other("CUDA disk Merkle library path must be absolute"));
        }
        let filename = CString::new(path.as_bytes())?;
        // RTLD_NOW resolves the CUDA library and all its symbols before any proof work.
        let handle = NonNull::new(unsafe { dlopen(filename.as_ptr(), 2) })
            .ok_or_else(|| io::Error::other(format!("cannot load CUDA disk Merkle bridge {path:?}")))?;
        let library = Library(handle);
        let abi: unsafe extern "C" fn() -> c_int =
            unsafe { std::mem::transmute(library.symbol(c"pg_disk_merkle_abi")?.as_ptr()) };
        if unsafe { abi() } != 1 {
            return Err(io::Error::other("unsupported CUDA disk Merkle ABI"));
        }
        let leaves: Leaves =
            unsafe { std::mem::transmute(library.symbol(c"pg_disk_merkle_leaves")?.as_ptr()) };
        let parents: Parents =
            unsafe { std::mem::transmute(library.symbol(c"pg_disk_merkle_parents")?.as_ptr()) };
        Ok(Some(Self {
            _library: library,
            leaves,
            parents,
            words: Vec::new(),
            column_logs: Vec::new(),
        }))
    }

    pub(super) fn hash_leaves(
        &mut self,
        first: usize,
        shifts: &[u32],
        output: &mut [u8],
        value: impl Fn(usize, usize) -> u32,
    ) -> io::Result<()> {
        let count = output.len() / HASH_BYTES;
        assert!(count >= 2 && count.is_power_of_two() && first % count == 0);
        assert_eq!(output.len(), count * HASH_BYTES);
        self.words.clear();
        self.column_logs.clear();
        for (column, &shift) in shifts.iter().enumerate() {
            // An aligned power-of-two batch either covers successive source pairs or repeats one.
            let start = (first >> (shift + 1)) << 1;
            let len = (count >> shift).max(2);
            if self.words.len() + len > MAX_WORDS {
                return Err(io::Error::other("CUDA disk Merkle leaf batch exceeds 64 MiB"));
            }
            self.words.extend((start..start + len).map(|row| value(column, row)));
            self.column_logs.push(len.ilog2());
        }
        let columns = u32::try_from(shifts.len()).map_err(io::Error::other)?;
        // Buffers are owned by this call and unchanged until the synchronous bridge returns.
        let result = unsafe {
            (self.leaves)(
                self.words.as_ptr(), self.words.len(), self.column_logs.as_ptr(), columns,
                count.ilog2(), output.as_mut_ptr(),
            )
        };
        cuda_status("leaf", result)
    }

    pub(super) fn hash_parents(&self, children: &[u8], output: &mut [u8]) -> io::Result<()> {
        assert_eq!(children.len(), output.len() * 2);
        assert_eq!(output.len() % HASH_BYTES, 0);
        let count = u32::try_from(output.len() / HASH_BYTES).map_err(io::Error::other)?;
        let result = unsafe { (self.parents)(children.as_ptr(), count, output.as_mut_ptr()) };
        cuda_status("parent", result)
    }
}

fn cuda_status(stage: &str, status: c_int) -> io::Result<()> {
    if status == 0 {
        return Ok(());
    }
    Err(io::Error::other(format!("CUDA disk Merkle {stage} failed with status {status}")))
}
