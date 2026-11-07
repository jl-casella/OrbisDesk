#!/usr/bin/env python3
"""Link unchanged native service probes without the Wine runtime/PE closure."""
import os
import sys
from common import ROOT, RESULTS, phase, run, sha, write_json
sys.path.insert(0, str(ROOT / 'tools'))
from sdk_libc import derive_libc


def main():
    sdk = ROOT / '.deps/sdk/OpenOrbis/PS4Toolchain'
    work = ROOT / 'build/ci-services'
    work.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / 'native' / name for name in (
        'ci_services.c', 'wine_ipc_probe.c', 'wine_pipe_probe.c',
        'wine_fs_probe.c', 'wine_metadata_probe.c')]
    sources += [ROOT / 'platform/ps4' / name for name in (
        'pw_wine_net.c', 'pw_wine_fs.c', 'pw_wine_platform.c',
        'pw_wine_signals.c', 'pw_vm_ps4_kernel.c')]
    flags = ['clang-19', '--target=x86_64-pc-freebsd12-elf', '-D__ORBIS__',
             '-fPIC', '-O2', '-g', '-march=btver2', '-ffunction-sections', '-fdata-sections',
             '-isysroot', str(sdk), '-isystem', str(sdk / 'include'), '-I' + str(ROOT / 'platform/ps4')]
    objects = []
    with phase('service-elf-build'):
        libc = derive_libc(sdk / 'lib/libc.a', work / 'lib/libc.a', boot=True)
        for source in sources:
            obj = work / (source.stem + '.o')
            run([*flags, '-c', source, '-o', obj], RESULTS / ('build-' + source.stem + '.log'))
            objects.append(obj)
        elf = work / 'services.elf'
        run(['ld.lld-19', '-m', 'elf_x86_64', '-pie', '--gc-sections', '--eh-frame-hdr',
             '--script', sdk / 'link.x', '-L', work / 'lib', '-L', sdk / 'lib', '-o', elf,
             *objects, sdk / 'lib/crt1.o', '-lc', '-lkernel', '-lkernel_sys', '-lSceNet'], RESULTS / 'services-link.log')
        converter = sdk / 'bin/linux/create-fself'
        converter.chmod(converter.stat().st_mode | 0o111)
        run([converter, '-in=' + str(elf), '-out=' + str(work / 'services.oelf'),
             '--eboot', work / 'eboot.bin', '--paid', '0x3800000000000011'],
            RESULTS / 'services-self.log', env=dict(os.environ, OO_PS4_TOOLCHAIN=str(sdk)))
        write_json(work / 'manifest.json', {
            'scope': 'Standalone existing native service probes; no Wine boot',
            'elf_sha256': sha(work / 'eboot.bin'),
            'libc': libc,
            'sources': {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}})


if __name__ == '__main__':
    main()
