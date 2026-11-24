"""Keep Windows awake until the exact overnight proof and release workers exit."""
import ctypes
from ctypes import wintypes
import sys


def main():
    pids = tuple(map(int, sys.argv[1:]))
    if not pids or len(set(pids)) != len(pids) or any(pid <= 0 for pid in pids):
        raise ValueError("invalid overnight worker process list")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForMultipleObjects.argtypes = (wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE), wintypes.BOOL, wintypes.DWORD)
    kernel.WaitForMultipleObjects.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.SetThreadExecutionState.argtypes = (wintypes.DWORD,)
    kernel.SetThreadExecutionState.restype = wintypes.DWORD

    handles = []
    try:
        for pid in pids:
            handle = kernel.OpenProcess(0x00100000, False, pid)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
        if not kernel.SetThreadExecutionState(0x80000001):
            raise ctypes.WinError(ctypes.get_last_error())
        print("Overnight workers are awake until their process handles signal exit.", flush=True)
        if kernel.WaitForMultipleObjects(len(handles), (wintypes.HANDLE * len(handles))(*handles), True, 0xFFFFFFFF) != 0:
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.SetThreadExecutionState(0x80000000)
        for handle in handles:
            kernel.CloseHandle(handle)


if __name__ == "__main__":
    main()
