#!/usr/bin/env python3
"""Build PS4 diagnostics and genuine i386 Windows fixtures under Linux/WSL."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(command, env=None):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", type=pathlib.Path, default=ROOT / ".deps/sdk/OpenOrbis/PS4Toolchain")
    parser.add_argument("--cc", default="clang")
    parser.add_argument("--ld", default="ld.lld")
    parser.add_argument("--with-wine-platform", action="store_true")
    parser.add_argument("--fixtures-only", action="store_true", help="Build only own Windows fixtures; no SDK/upstream checkout required")
    parser.add_argument("--diagnostics-only", action="store_true", help="Reuse verified CI fixtures and build only the diagnostic ELF")
    args = parser.parse_args()
    if args.fixtures_only and args.diagnostics_only: parser.error("Choose fixtures-only or diagnostics-only")
    sdk = args.sdk.resolve()
    if not args.fixtures_only: run(["python3", ROOT / "tools/lock_sources.py"])
    for tool in (("i686-w64-mingw32-gcc",) if args.fixtures_only else (args.cc, args.ld, "i686-w64-mingw32-gcc")):
        if not shutil.which(tool):
            raise SystemExit(f"Missing {tool}; see README.md")
    if not args.fixtures_only and not (sdk / "lib/crt1.o").is_file():
        raise SystemExit(f"Missing OpenOrbis SDK: {sdk}")
    build = ROOT / "build/ps4"
    out = ROOT / "out"
    build.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)
    wine_build = None
    if not args.fixtures_only:
        flags = ["--target=x86_64-pc-freebsd12-elf", "-fPIC", "-funwind-tables", "-march=btver2",
                 "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-isysroot", sdk,
                 "-isystem", sdk / "include", "-DWITH_TRANSLATOR", "-I", ROOT / "upstream/prospero-win/src",
                 "-I", ROOT / "upstream/prospero-win/include", "-I", ROOT / "platform/ps4"]
        sources = [ROOT / "native/probe.c", ROOT / "native/fault.S", ROOT / "native/translator_runtime.c", ROOT / "native/dispatcher.c", ROOT / "native/pe32_probe.c", ROOT / "platform/ps4/pw_vm_ps4.c",
                   ROOT / "platform/ps4/pw_pe32.c", ROOT / "platform/ps4/pw_pe32_tables.c", ROOT / "native/dll_probe.c",
                   ROOT / "platform/ps4/pw_pe32_lifecycle.c", ROOT / "native/lifecycle_probe.c",
                   ROOT / "platform/ps4/pw_cpu_ps4.c", ROOT / "platform/ps4/pw_k32_ps4.c", ROOT / "platform/ps4/pw_msvcrt_ps4.c", ROOT / "platform/ps4/pw_process_ps4.c", ROOT / "native/process_probe.c", ROOT / "native/wine_probe.c",
                   ROOT / "platform/ps4/pw_vm_ps4_kernel.c",
                   ROOT / "platform/ps4/pw_pthread_ps4.c"]
        sources += [ROOT / "upstream/prospero-win/src" / name for name in
                    ("pw_x86_block.c", "pw_x86_hostexec.c", "pw_x86_engine.c", "pw_x86_cache.c", "pw_x86_reencode.c",
                     "pw_x87.c", "pw_guest_fp.c", "pw_guest_call.c", "pw_vm.c")]
        objects = []
        wine_build = None
        if args.with_wine_platform:
            run(["python3", ROOT / "tools/build-wine-ps4.py"])
            wine_build = json.loads((ROOT / "build/wine-ps4/report.json").read_text())
            flags += ["-DWITH_WINE_PLATFORM"]
            sources += [ROOT / "platform/ps4/pw_wine_platform.c", ROOT / "native/wine_platform_probe.c"]
            objects += [ROOT / "build/wine-ps4" / (name + ".diagnostic.o") for name in ("harness", "loader-harness", "file", "cdrom")]
        for source in sources:
            obj = build / (source.stem + ".o")
            run([args.cc, *flags, "-c", source, "-o", obj])
            objects.append(obj)
        library_paths = ["-L", ROOT / "build/wine-ps4/lib"] if args.with_wine_platform else []
        run([args.ld, "-m", "elf_x86_64", "-pie", "--gc-sections", "--script", sdk / "link.x", "--eh-frame-hdr",
             *library_paths, "-L", sdk / "lib", "-o", out / "probe.elf", *objects, sdk / "lib/crt1.o", "-lc", "-lkernel"])
        converter = sdk / "bin/linux/create-fself"
        converter.chmod(converter.stat().st_mode | 0o111)
        env = dict(os.environ, OO_PS4_TOOLCHAIN=str(sdk))
        run([converter, f"-in={out / 'probe.elf'}", f"-out={out / 'probe.oelf'}",
             "--eboot", out / "eboot.bin", "--paid", "0x3800000000000011"], env)
    artifacts = {}
    if not args.diagnostics_only:
        for name in ("console", "gdi"):
            command = ["i686-w64-mingw32-gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-static-libgcc", "-Wl,--no-insert-timestamp",
                       ROOT / f"fixtures/win32/{name}.c", "-o", out / f"{name}32.exe"]
            if name == "gdi":
                command += ["-mwindows", "-lgdi32", "-luser32"]
            run(command)
        for fixture, alignment in (("minimal32.exe", "0x4000"), ("minimal4k32.exe", "0x1000")):
            run(["i686-w64-mingw32-gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
                 "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-nostdlib",
                 ROOT / "fixtures/win32/minimal.c", "-Wl,--entry,_entry,--image-base,0x30000000,"
                 f"--section-alignment,{alignment},--file-alignment,0x200,--enable-reloc-section,--no-insert-timestamp",
                 "-o", out / fixture])
        run(["i686-w64-mingw32-gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
             "-fno-stack-protector", "-fno-asynchronous-unwind-tables", "-nostdlib", ROOT / "fixtures/win32/process.c",
             "-Wl,--entry,_entry,--image-base,0x30000000,--section-alignment,0x1000,--enable-reloc-section,--no-insert-timestamp",
             "-o", out / "process32.exe"])
        pe_flags = ["-O2", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-stack-protector",
                    "-fno-asynchronous-unwind-tables", "-fno-optimize-sibling-calls", "-nostdlib"]
        pe_link = "--section-alignment,0x1000,--enable-reloc-section,--no-insert-timestamp"
        run(["i686-w64-mingw32-gcc", *pe_flags, "-shared", ROOT / "fixtures/win32/testmath.c",
             ROOT / "fixtures/win32/testmath.def", f"-Wl,--entry,0,--image-base,0x32000000,{pe_link},"
             f"--out-implib,{build / 'testmath.dll.a'}", "-o", out / "testmath.dll"])
        run(["i686-w64-mingw32-gcc", *pe_flags, ROOT / "fixtures/win32/imports.c", build / "testmath.dll.a",
             f"-Wl,--entry,_entry,--image-base,0x30000000,{pe_link}", "-o", out / "imports32.exe"])
        run(["i686-w64-mingw32-gcc", *pe_flags, "-shared", ROOT / "fixtures/win32/nested.c",
             ROOT / "fixtures/win32/nested.def", build / "testmath.dll.a",
             f"-Wl,--entry,0,--image-base,0x33000000,{pe_link}", "-o", out / "nested.dll"])
        for name, base, reject in (("lifecycle.dll", "0x32000000", 0), ("lifecycle-peer.dll", "0x33000000", 0),
                                   ("lifecycle-fail.dll", "0x33000000", 1)):
            run(["i686-w64-mingw32-gcc", *pe_flags, "-shared", f"-DREJECT_ATTACH={reject}",
                 ROOT / "fixtures/win32/lifecycle.c", ROOT / "fixtures/win32/lifecycle.def",
                 f"-Wl,--entry,_DllMain@12,--image-base,{base},{pe_link}", "-o", out / name])
        run(["i686-w64-mingw32-gcc", *pe_flags, ROOT / "fixtures/win32/lifecycle_host.c",
             "-Wl,--entry,_entry,--no-insert-timestamp", "-lkernel32", "-o", out / "lifecycle-host.exe"])
        run(["python3", ROOT / "tools/build-console-bare.py"])
    for name in ("probe.elf", "probe.oelf", "eboot.bin", "console32.exe", "console32-bare.exe", "gdi32.exe", "minimal32.exe", "minimal4k32.exe",
                 "testmath.dll", "imports32.exe", "nested.dll", "lifecycle.dll", "lifecycle-peer.dll", "lifecycle-fail.dll",
                 "lifecycle-host.exe", "process32.exe"):
        if args.fixtures_only and name in ("probe.elf", "probe.oelf", "eboot.bin"): continue
        path = out / name
        artifacts[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    versions = {tool: subprocess.check_output([tool, "--version"], text=True).splitlines()[0]
                for tool in (("i686-w64-mingw32-gcc",) if args.fixtures_only else (args.cc, args.ld, "i686-w64-mingw32-gcc"))}
    local_inputs = sorted(set([*ROOT.glob("native/*.[chS]"), *ROOT.glob("platform/ps4/*.[ch]"),
                               *ROOT.glob("fixtures/win32/*.c"), *ROOT.glob("fixtures/win32/*.def"), ROOT / "tools/build.py",
                               ROOT / "tools/build-console-bare.py", ROOT / "tools/verify_artifacts.py"]))
    if args.with_wine_platform:
        local_inputs += [ROOT / "tools/build-wine-ps4.py", ROOT / "tools/prepare-wine-ps4.py",
                         ROOT / "patches/wine/0001-ps4-memory-paths-files-cdrom.patch",
                         ROOT / ".deps/wine/ps4-overlay/manifest.json", ROOT / ".deps/wine/ps4-unix/include/config.h",
                         ROOT / ".deps/wine/ps4-unix/orbis-cc"]
        local_inputs += sorted((ROOT / ".deps/wine/ps4-overlay/dlls/ntdll/unix").glob("*.c"))
    local_hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in local_inputs}
    (out / "build.json").write_text(json.dumps({"sources": json.loads((ROOT / "sources.lock.json").read_text()),
                                               "local_inputs": local_hashes,
                                               "tools": versions, "artifacts": artifacts, "wine_unix": wine_build}, indent=2) + "\n")
    run(["python3", ROOT / "tools/verify_artifacts.py", *(["--fixtures-only"] if args.fixtures_only else [])])


if __name__ == "__main__":
    main()
