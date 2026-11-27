#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-3.0-or-later
"""Build the pinned gbe startup addon with guest-context guards. Never uploads/packages.

The matching archive is shared with build-steam-hosted.py. Generated upstream sources
and all compiler outputs stay under this checkout's build/steamstub-addon.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_HASH = 'ce3ce7aee0439f1b7aff2404106fe68184185a8d0b7ca5ab2677a046ea464cbd'
ARCHIVE = ROOT / '.deps/steam/downloads/gbe_fork-2026_09_27/gbe_fork-release-2026_09_27-source.tar.gz'


def adapt_stub(text):
    # Hooks are process-wide, but guest EXE identity is per thread. Never inspect or
    # modify another guest's dynamically generated code through those hooks.
    old = '    if (!ret_addr) return;'
    if text.count(old) != 1:
        raise ValueError('upstream patch_if_possible context changed')
    text = text.replace(old, '    if (!ret_addr || (uint8_t *)GetModuleHandleW(nullptr) != exe_addr_base) return;')
    old = '    if (anything_found) {\n'
    if text.count(old) != 1:
        raise ValueError('upstream patch result context changed')
    text = text.replace(old, '    if (anything_found) {\n        orbisdesk_stub_trace("matched");\n')
    # A matched pattern is not a successful write. Retain hook cleanup on success
    # only, and report failed writes separately instead of fabricating completion.
    old = '                anything_found = true;\n                change_mem_access |= stub_details.change_mem_access;\n'
    if text.count(old) != 1:
        raise ValueError('upstream write context changed')
    text = text.replace(old, '')
    old = '                    GetCurrentProcess());\n#ifdef STUB_EXTRA_DEBUG'
    if text.count(old) != 1:
        raise ValueError('upstream write result context changed')
    text = text.replace(old, '                    GetCurrentProcess());\n'
                        '                if (ok) { anything_found = true; change_mem_access |= stub_details.change_mem_access; }\n'
                        '                else orbisdesk_stub_trace("write_failed");\n#ifdef STUB_EXTRA_DEBUG')
    text = text.replace('static bool GetTickCount_hooked = false;',
                        'static bool hooks_installed = false;\nstatic bool GetTickCount_hooked = false;')
    start = text.index('static bool redirect_win32_apis()\n{')
    end = text.index('static bool calc_bind_section_boundaries()', start)
    text = text[:start] + '''static bool redirect_win32_apis()
{
    if (DetourTransactionBegin() != NO_ERROR) return false;
    if (DetourUpdateThread(GetCurrentThread()) != NO_ERROR ||
        DetourAttach((PVOID *)&actual_GetTickCount, (PVOID)GetTickCount_hook) != NO_ERROR ||
        DetourAttach((PVOID *)&actual_GetModuleHandleA, (PVOID)GetModuleHandleA_hook) != NO_ERROR ||
        DetourAttach((PVOID *)&actual_GetModuleHandleExA, (PVOID)GetModuleHandleExA_hook) != NO_ERROR) {
        DetourTransactionAbort();
        return false;
    }
    if (DetourTransactionCommit() != NO_ERROR) return false;
    hooks_installed = GetTickCount_hooked = GetModuleHandleA_hooked = GetModuleHandleExA_hooked = true;
    return true;
}

static bool restore_win32_apis()
{
    std::lock_guard lock(mtx_win32_api);
    GetTickCount_hooked = GetModuleHandleA_hooked = GetModuleHandleExA_hooked = false;
    if (!hooks_installed) return true;
    if (DetourTransactionBegin() != NO_ERROR) return false;
    if (DetourUpdateThread(GetCurrentThread()) != NO_ERROR ||
        DetourDetach((PVOID *)&actual_GetTickCount, (PVOID)GetTickCount_hook) != NO_ERROR ||
        DetourDetach((PVOID *)&actual_GetModuleHandleA, (PVOID)GetModuleHandleA_hook) != NO_ERROR ||
        DetourDetach((PVOID *)&actual_GetModuleHandleExA, (PVOID)GetModuleHandleExA_hook) != NO_ERROR) {
        DetourTransactionAbort();
        return false;
    }
    if (DetourTransactionCommit() != NO_ERROR) return false;
    hooks_installed = false;
    return true;
}

''' + text[end:]
    old = '        restore_win32_apis();\n        if (change_mem_access)'
    if text.count(old) != 1:
        raise ValueError('upstream hook restoration context changed')
    text = text.replace(old,
                        '        if (!restore_win32_apis()) { orbisdesk_stub_trace("restore_failed"); return; }\n'
                        '        if (change_mem_access)')
    return '#include "orbisdesk_stub_trace.h"\n' + text.replace('#include <Windows.h>', '#include <windows.h>')


def adapt_entry(text):
    for old, new in (
        ('#include <Windows.h>', '#include <windows.h>'),
        ('            unload_dll = true;\n            return FALSE;',
         '            orbisdesk_stub_trace("not_armed");\n            unload_dll = true;\n            return FALSE;'),
        ('        unload_thread_handle = CreateThread(',
         '        orbisdesk_stub_trace("armed");\n        unload_thread_handle = CreateThread('),
        ('            stubdrm::restore();', '            orbisdesk_stub_trace("restore");\n            stubdrm::restore();'),
        ('    FreeLibraryAndExitThread(my_hModule, 0);',
         '    if (!stubdrm::restore()) {\n'
         '        HMODULE retained;\n'
         '        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_PIN | GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,\n'
         '                           (LPCWSTR)&self_unload, &retained);\n'
         '        orbisdesk_stub_trace("restore_failed_retained_restart_required");\n'
         '        return 0;\n'
         '    }\n'
         '    FreeLibraryAndExitThread(my_hModule, 0);'),
    ):
        if text.count(old) != 1:
            raise ValueError('upstream addon entry context changed: ' + old)
        text = text.replace(old, new)
    return '#include "orbisdesk_stub_trace.h"\n' + text


def build(toolchain):
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != SOURCE_HASH:
        raise ValueError('gbe source archive does not match pin')
    work = ROOT / 'build/steamstub-addon'
    source = work / 'source'
    source.mkdir(parents=True, exist_ok=True)
    # Extract only regular source files; never restore archive links or paths.
    with tarfile.open(ARCHIVE) as archive:
        for entry in archive.getmembers():
            parts = pathlib.PurePosixPath(entry.name).parts
            if not entry.isfile() or len(parts) < 2 or '..' in parts:
                continue
            relative = pathlib.Path(*parts[1:])
            if parts[1] not in ('helpers', 'libs', 'tools'):
                continue
            if relative.suffix not in ('.cpp', '.h', '.hpp', '.cc', '.inl', '.txt'):
                continue
            dest = source / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.extractfile(entry).read())
    extra = source / 'tools/steamclient_loader/win/extra_protection'
    (extra / 'stubdrm.cpp').write_text(adapt_stub((extra / 'stubdrm.cpp').read_text()))
    (extra / 'dllmain.cpp').write_text(adapt_entry((extra / 'dllmain.cpp').read_text()))
    (extra / 'orbisdesk_stub_trace.h').write_text('''#pragma once
#include <windows.h>
#include <stdio.h>
static void orbisdesk_stub_trace(const char *phase)
{
    char line[160]; DWORD written;
    int n = snprintf(line, sizeof(line), "PWSTUB phase=%s pid=%lu tid=%lu tick=%llu\\r\\n",
                     phase, GetCurrentProcessId(), GetCurrentThreadId(), (unsigned long long)GetTickCount64());
    HANDLE file = CreateFileW(L"Z:\\\\orbisdesk\\\\steamstub-startup.log", FILE_APPEND_DATA,
                              FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_ALWAYS, 0, NULL);
    if (file != INVALID_HANDLE_VALUE) { if (n > 0 && n < (int)sizeof(line)) WriteFile(file, line, n, &written, NULL); CloseHandle(file); }
}
''')
    inputs = [extra / 'dllmain.cpp', extra / 'stubdrm.cpp', source / 'helpers/pe_helpers.cpp',
              source / 'helpers/common_helpers.cpp']
    inputs += [source / ('libs/detours/' + name + '.cpp') for name in
               ('detours', 'disasm', 'modules', 'image', 'creatwth')]
    includes = [source / 'helpers', source / 'libs', extra]
    manifest = {'source_archive_sha256': SOURCE_HASH, 'files': {}, 'source_hashes': {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (pathlib.Path(__file__),)}}
    with (work / 'build.log').open('w') as log:
        for arch, target in (('x86', 'i686'), ('x64', 'x86_64')):
            output = work / ('orbisdesk_steamstub_' + arch + '.dll')
            command = [str(toolchain / 'bin' / (target + '-w64-mingw32-clang++')), '-std=c++17',
                       '-O2', '-shared', '-static', '-ffunction-sections', '-fdata-sections',
                       '-Wl,--gc-sections', '-DDETOURS_INTERNAL', '-DUNICODE', '-D_UNICODE',
                       *('-I' + str(p) for p in includes), *map(str, inputs), '-luser32', '-ladvapi32',
                       '-o', str(output)]
            log.write(' '.join(command) + '\n'); log.flush()
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            manifest['files'][output.name] = {'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                                            'bytes': output.stat().st_size}
    (work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=pathlib.Path, default=pathlib.Path.home() / 'vk-h0/llvm-mingw')
    build(parser.parse_args().toolchain)
