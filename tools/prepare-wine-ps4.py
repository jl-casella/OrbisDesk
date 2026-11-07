#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Generate a reviewable, exact pinned-source overlay; never modify Wine.
The fstab and host-page changes follow prospero-win patches 0100 and 0510
(LGPL-2.1-or-later, prospero-win contributors), adapted to __ORBIS__.
"""
import difflib
import hashlib
import json
import pathlib
import subprocess

ROOT=pathlib.Path(__file__).resolve().parents[1]
source=ROOT/'.deps/wine/source'
overlay=ROOT/'.deps/wine/ps4-overlay'
commit=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']
if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=commit:
    raise SystemExit('Wine revision mismatch')
changes={}
def edit(name):
    path='dlls/ntdll/unix/'+name+'.c'
    old=(source/path).read_text()
    changes[path]=[old,old]
    return path
def replace(path,old,new,count=1):
    text=changes[path][1]
    if text.count(old)!=count: raise SystemExit('Unexpected source context: '+path+' '+old[:60])
    changes[path][1]=text.replace(old,new)

p=edit('virtual')
replace(p,'#include "unix_private.h"','#include "unix_private.h"\n#ifdef __ORBIS__\n#include "pw_wine_platform.h"\n#define mprotect pw_wine_memory_protect\n#define munmap pw_wine_memory_release\n#endif')
replace(p,'#ifdef __aarch64__\nstatic UINT_PTR host_page_size;', '#if defined(__aarch64__) || defined(__ORBIS__)\nstatic UINT_PTR host_page_size;')
replace(p,'#ifdef __aarch64__\n    host_page_size = sysconf( _SC_PAGESIZE );', '#if defined(__aarch64__) || defined(__ORBIS__)\n#ifdef __ORBIS__\n    host_page_size = 0x4000; /* PS4 kernel granularity; SDK sysconf is not the ABI. */\n#else\n    host_page_size = sysconf( _SC_PAGESIZE );\n#endif')
replace(p,'    void *ptr;\n\n#ifdef MAP_FIXED_NOREPLACE','''#ifdef __ORBIS__
    return pw_wine_anon_tryfixed( start, size, prot, flags );
#else
    void *ptr;

#ifdef MAP_FIXED_NOREPLACE''')
replace(p,'    return ptr;\n}\n\nstatic void reserve_area','    return ptr;\n#endif /* __ORBIS__ */\n}\n\nstatic void reserve_area')

p=edit('file')
replace(p,'#include "unix_private.h"', '''#include "unix_private.h"
#ifdef __ORBIS__
#include "pw_wine_platform.h"
#define stat(path,buffer) pw_wine_stat(path,buffer)
#define fstat(fd,buffer) pw_wine_fstat(fd,buffer)
#define lstat(path,buffer) pw_wine_lstat(path,buffer)
#endif''')
replace(p,'#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__) || defined(__DragonFly__)\n#include <fstab.h>', '''#ifdef __ORBIS__
/* Adapted from prospero-win 0100: no host drive-device discovery on PS4.
 * Wine still resolves files under explicitly configured drive mappings. */
static char *parse_mount_entries( FILE *f, dev_t dev, ino_t ino )
{
    return NULL;
}
#elif defined(__FreeBSD__) || defined(__FreeBSD_kernel__) || defined(__DragonFly__)
#include <fstab.h>''')
replace(p,'#elif defined(__APPLE__) || defined(__FreeBSD__) || defined(__FreeBSD_kernel__)\n    struct statfs *entry;', '#elif !defined(__ORBIS__) && (defined(__APPLE__) || defined(__FreeBSD__) || defined(__FreeBSD_kernel__))\n    struct statfs *entry;')
replace(p,'#if defined(__FreeBSD__) || defined(__FreeBSD_kernel__) || defined(__NetBSD__) || defined(__OpenBSD__) || defined(__DragonFly__) || defined(__APPLE__)\n/* helper', '#if !defined(__ORBIS__) && (defined(__FreeBSD__) || defined(__FreeBSD_kernel__) || defined(__NetBSD__) || defined(__OpenBSD__) || defined(__DragonFly__) || defined(__APPLE__))\n/* helper')
replace(p,'NTSTATUS get_device_info( int fd, FILE_FS_DEVICE_INFORMATION *info )\n{', '''NTSTATUS get_device_info( int fd, FILE_FS_DEVICE_INFORMATION *info )
{
#ifdef __ORBIS__
    /* Mount/device characteristics have not been implemented for PS4.
     * Preserve output instead of inventing read-only/local/device flags. */
    return STATUS_NOT_SUPPORTED;
#else''')
replace(p,'        info->Characteristics |= FILE_DEVICE_IS_MOUNTED;\n    }\n    return STATUS_SUCCESS;\n}', '        info->Characteristics |= FILE_DEVICE_IS_MOUNTED;\n    }\n    return STATUS_SUCCESS;\n#endif\n}')
replace(p,'static inline BOOL is_device_placeholder( int fd )','\n#ifndef __ORBIS__\nstatic inline BOOL is_device_placeholder( int fd )')
replace(p,'NTSTATUS get_device_info( int fd, FILE_FS_DEVICE_INFORMATION *info )','\n#endif /* !__ORBIS__ */\nNTSTATUS get_device_info( int fd, FILE_FS_DEVICE_INFORMATION *info )')

p=edit('env')
replace(p,'    if (output_fd != -1)\n    {\n        struct winsize size;', '    /* PS4 has no inherited host terminal geometry. */\n#ifndef __ORBIS__\n    if (output_fd != -1)\n    {\n        struct winsize size;')
replace(p,'            params->dwYCountChars = size.ws_row;\n        }\n    }','            params->dwYCountChars = size.ws_row;\n        }\n    }\n#else\n    (void)output_fd;\n#endif')

p=edit('loader')
replace(p,'    if (!home || !name)\n    {','''#ifdef __ORBIS__
    if (!home || home[0] != '/' || !name || !name[0])
        fatal_error( "PS4 requires explicit absolute HOME and USER before Wine startup\\n" );
#else
    if (!home || !name)
    {''')
replace(p,'        if (!name) name = "wine";\n    }','        if (!name) name = "wine";\n    }\n#endif')
replace(p,'    const char *prefix = getenv( "WINEPREFIX" );','''    const char *prefix = getenv( "WINEPREFIX" );
#ifdef __ORBIS__
    if (!prefix || prefix[0] != '/')
        fatal_error( "PS4 requires an explicit absolute WINEPREFIX before Wine startup\\n" );
#endif''')

p=edit('cdrom')
replace(p,'WINE_DEFAULT_DEBUG_CHANNEL(cdrom);','''#ifdef __ORBIS__
/* Outside the initial PS4 scope. Immediate NT error: no successful I/O or
 * asynchronous completion is claimed and caller buffers remain untouched. */
NTSTATUS cdrom_DeviceIoControl( HANDLE device, HANDLE event, PIO_APC_ROUTINE apc, void *apc_user,
                               IO_STATUS_BLOCK *io, UINT code, void *in_buffer,
                               UINT in_size, void *out_buffer, UINT out_size )
{
    return STATUS_NOT_SUPPORTED;
}
#else
WINE_DEFAULT_DEBUG_CHANNEL(cdrom);''')
changes[p][1]+='\n#endif /* __ORBIS__ */\n'

diff=[];hashes={}
for path,(old,new) in changes.items():
    target=overlay/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(new)
    diff.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),'a/'+path,'b/'+path))
    hashes[path]={'original_sha256':hashlib.sha256(old.encode()).hexdigest(),'patched_sha256':hashlib.sha256(new.encode()).hexdigest()}
patch=ROOT/'patches/wine/0001-ps4-memory-paths-files-cdrom.patch'
patch.parent.mkdir(parents=True,exist_ok=True);patch.write_text(''.join(diff))
(overlay/'manifest.json').write_text(json.dumps({'wine_commit':commit,'files':hashes,'patch_sha256':hashlib.sha256(patch.read_bytes()).hexdigest()},indent=2)+'\n')
print('Prepared five-file PS4 overlay:',overlay)
