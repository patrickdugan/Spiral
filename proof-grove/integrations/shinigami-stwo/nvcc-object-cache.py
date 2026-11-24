#!/usr/bin/env python3
"""Prepare a local resumable NVCC cache for the pinned Vortex SM86 overlay."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile


VORTEX_COMMIT = "1e88c31974bcb9906274d7a129bd9f2902d7ae2e"
CUDA_TREE = "ff5d216bc06c6cc85f2056be8629b704eeeb9ca2"
BUILD_RS = "cda9c4de5cb7809711e2008ca68d80b776302883fd038d329b1723edc3bfbcf4"
DEFINES = (
    "-DSHINOBI_HASH_REDUCE=1", "-DFORGE_NTT=1", "-DFORGE_NTT_BATCH=1",
    "-DFORGE_FRI=1", "-DFORGE_PERMUTE=1", "-DFORGE_BARYCENTRIC=1", "-DFORGE_GRIND=1",
)
INJECTORS = (
    "NVCC_CCBIN", "NVCC_PREPEND_FLAGS", "NVCC_APPEND_FLAGS", "GCC_EXEC_PREFIX",
    "COMPILER_PATH", "LIBRARY_PATH", "CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH",
    "LD_PRELOAD", "LD_AUDIT",
)
BUILD_ENV = ("PATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL", "LC_CTYPE", "SOURCE_DATE_EPOCH", "TMPDIR")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def git_id(kind, data):
    return hashlib.sha1(f"{kind} {len(data)}\0".encode() + data).digest()


def git_tree(path):
    entries = []
    for child in path.iterdir():
        name = os.fsencode(child.name)
        if child.is_symlink():
            raise ValueError(f"unexpected symlink in pinned CUDA tree: {child}")
        if child.is_dir():
            entries.append((name + b"/", b"40000 " + name + b"\0" + git_tree(child)))
        elif child.is_file():
            mode = b"100755" if child.stat().st_mode & 0o111 else b"100644"
            entries.append((name, mode + b" " + name + b"\0" + git_id("blob", child.read_bytes())))
        else:
            raise ValueError(f"unexpected entry in pinned CUDA tree: {child}")
    return git_id("tree", b"".join(entry for _, entry in sorted(entries)))


def pinned_source(root):
    return {
        "vortex_commit": VORTEX_COMMIT,
        "cuda_git_tree": git_tree(root / "cuda").hex(),
        "build_rs_sha256": file_hash(root / "build.rs"),
    }


def stat_id(path):
    info = path.stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def compiler_identity(toolkit):
    nvcc = toolkit / "bin/nvcc"
    host = {}
    for name in ("gcc", "g++"):
        program = shutil.which(name)
        if program is None:
            raise ValueError(f"missing host compiler: {name}")
        host[name] = str(Path(program).resolve())
    files = {nvcc, *(Path(path) for path in host.values())}
    for program in ("cc1plus", "as"):
        found = subprocess.check_output([host["g++"], f"-print-prog-name={program}"], text=True).strip()
        files.add(Path(shutil.which(found) or found))
    files.update(path for name in ("ptxas", "fatbinary", "nvcc.profile", "crt/link.stub")
                 if (path := toolkit / "bin" / name).is_file())
    files.update(path for name in ("bin/cicc", "libdevice/libdevice.10.bc")
                 if (path := toolkit / "nvvm" / name).is_file())
    files.update(path for path in (toolkit / "include").rglob("*") if path.is_file())
    versions = {name: subprocess.check_output([path, "--version"], text=True)
                for name, path in {"nvcc": str(nvcc), **host}.items()}
    return {
        "host": host, "versions": versions,
        "files": {str(path): {"stat": stat_id(path), "sha256": file_hash(path)}
                  for path in sorted(files)},
    }


def compiler_unchanged(identity):
    for name, path in identity["host"].items():
        candidate = shutil.which(name)
        if candidate is None or str(Path(candidate).resolve()) != path:
            return False
    try:
        return all(stat_id(Path(path)) == recorded["stat"]
                   for path, recorded in identity["files"].items())
    except OSError:
        return False


def prepare(source, toolkit, shim, cache):
    pin = pinned_source(source)
    if (pin["cuda_git_tree"], pin["build_rs_sha256"]) != (CUDA_TREE, BUILD_RS):
        raise ValueError("staged Vortex source differs from the pinned SM86 overlay")
    compiler = compiler_identity(toolkit)
    if "release 12.8," not in compiler["versions"]["nvcc"]:
        raise ValueError("this SM86 cache expects CUDA 12.8")
    shim.mkdir()
    (shim / "bin").mkdir()
    for directory in ("include", "lib64"):
        (shim / directory).symlink_to(toolkit / directory, target_is_directory=True)
    cache.mkdir(parents=True, exist_ok=True)
    config = shim / "config.json"
    config.write_bytes(canonical({"source": str(source), "pin": pin, "compiler": compiler,
                                  "nvcc": str(toolkit / "bin/nvcc"), "cache": str(cache)}))
    wrapper = shim / "bin/nvcc"
    command = shlex.join([sys.executable, "-B", str(Path(__file__).resolve()), "run", str(config), "--"])
    wrapper.write_text(f'#!/bin/sh\nexec {command} "$@"\n', encoding="utf-8", newline="\n")
    wrapper.chmod(0o755)


def compile_output(args):
    if len(args) < 8 or args[:2] != ["-c", "-O3"]:
        return None
    if args[-6:-2] != ["-gencode", "arch=compute_86,code=sm_86", "-Icuda/include", "-o"]:
        return None
    if any(option not in DEFINES for option in args[2:-6]):
        return None
    source, output = Path(args[-1]), Path(args[-2])
    if source.parent != Path("cuda") or source.suffix != ".cu" or output.suffix != ".o":
        return None
    return output


def atomic_file(path, write):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def object_from_cache(entry, recipe):
    try:
        with zipfile.ZipFile(entry) as archive:
            if archive.namelist() != ["receipt.json", "object.o"]:
                return None
            receipt = json.loads(archive.read("receipt.json"))
            data = archive.read("object.o")
        want = hashlib.sha256(data).hexdigest()
        if data and receipt == {"recipe": recipe, "object_sha256": want}:
            return data
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        pass
    return None


def publish(entry, recipe, data):
    def write(stream):
        receipt = {"recipe": recipe, "object_sha256": hashlib.sha256(data).hexdigest()}
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("receipt.json", canonical(receipt))
            archive.writestr("object.o", data)

    atomic_file(entry, write)


def exact_compile(nvcc, args):
    return subprocess.run([nvcc, *args], check=False).returncode


def run(config, args):
    nvcc = config["nvcc"]
    source = Path(config["source"])
    output = compile_output(args)
    if output is None or Path.cwd() != source or any(os.environ.get(name) for name in INJECTORS):
        return exact_compile(nvcc, args)
    pin = pinned_source(source)
    if pin != config["pin"]:
        raise ValueError("Vortex CUDA source changed after cache preparation")
    compiler = config["compiler"]
    if not compiler_unchanged(compiler):
        return exact_compile(nvcc, args)
    recipe = {
        "schema": "proof-grove/vortex-nvcc-object/v1", "argv": [nvcc, *args], "cwd": str(source),
        "source": pin, "compiler_sha256": hashlib.sha256(canonical(compiler)).hexdigest(),
        "compiler_versions": compiler["versions"],
        "environment": {name: os.environ.get(name) for name in BUILD_ENV},
    }
    entry = Path(config["cache"]) / (hashlib.sha256(canonical(recipe)).hexdigest() + ".zip")
    if (data := object_from_cache(entry, recipe)) is not None:
        atomic_file(output, lambda stream: stream.write(data))
        print(f"nvcc object cache hit: {args[-1]}", file=sys.stderr)
        return 0
    old = stat_id(output) if output.exists() else None
    result = exact_compile(nvcc, args)
    if result == 0 and output.is_file() and stat_id(output) != old and output.stat().st_size:
        if compiler_unchanged(compiler) and pinned_source(source) == pin:
            try:
                publish(entry, recipe, output.read_bytes())
                print(f"nvcc object cache saved: {args[-1]}", file=sys.stderr)
            except OSError as error:
                print(f"nvcc object cache unavailable: {error}", file=sys.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    for option in ("--source", "--toolkit", "--shim", "--cache"):
        setup.add_argument(option, type=Path, required=True)
    compile_parser = commands.add_parser("run")
    compile_parser.add_argument("config", type=Path)
    compile_parser.add_argument("nvcc_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source.resolve(), args.toolkit.resolve(), args.shim.resolve(), args.cache.resolve())
        return 0
    options = args.nvcc_args
    if options[:1] == ["--"]:
        options = options[1:]
    status = run(json.loads(args.config.read_bytes()), options)
    return 128 - status if status < 0 else status


if __name__ == "__main__":
    sys.exit(main())
