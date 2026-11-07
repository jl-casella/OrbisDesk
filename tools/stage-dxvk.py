#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W124, phase 4 of the PE32 plan: DXVK (Direct3D 8/9/10/11 on Vulkan) for the console.

The upstream mingw release (https://github.com/doitsujin/dxvk, zlib licence), pinned by
SHA-256: x64 DLLs for 64-bit programs (system32) and x32 for 32-bit ones (syswow64).
W197: in the x64 DLLs that load Vulkan, DXVK's first loader name "winevulkan.dll" becomes
"vulkan-1.dll" (LOADER below), so 64-bit Direct3D goes through the Khronos loader and MangoHud's
layer like other Vulkan programs. W247: the x32 ones try "vulkan-1.dll" first and "winevulkan.dll" second
(LOADER32), for the i386 loader and MangoHud layer of W245, with winevulkan as fallback. 2.7.1 is the last release with the 2.x shader compiler; 3.x compiles more on
the CPU (its release notes), which the console's Jaguar cores can least afford.
Output: out/dxvk/{x64,x32}/*.dll and manifest.json.
"""
import hashlib,json,pathlib,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
VERSION='2.7.1'
ARCHIVE=ROOT/'.deps/downloads/dxvk-2.7.1/dxvk-2.7.1.tar.gz'
SHA256='d85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87'
DLLS=('d3d8.dll','d3d9.dll','d3d10core.dll','d3d11.dll','dxgi.dll')
# W197 (W195: no MangoHud on DXVK): DXVK 2.7.1 takes vkGetInstanceProcAddr from the first of
# "winevulkan.dll" and "vulkan-1.dll" that loads (src/vulkan/vulkan_loader.cpp, a fixed list), so
# it used winevulkan directly and skipped the Khronos loader (system32 vulkan-1.dll, W086) that
# loads MangoHud's implicit layer. Both entries name vulkan-1.dll; same length, NUL padded.
LOADER=(b'winevulkan.dll\x00vulkan-1.dll\x00',b'vulkan-1.dll\x00\x00\x00vulkan-1.dll\x00')
LOADER_DLLS=('x64/d3d9.dll','x64/d3d11.dll','x64/dxgi.dll')
# W247 (W245: d3d9test32 found vkGetInstanceProcAddr in winevulkan.dll and never loaded syswow64's Khronos
# loader, so no MangoHud i386): in the x32 DLLs the two names swap places, "vulkan-1.dll" first and
# "winevulkan.dll" second, so DXVK still falls back to winevulkan if the i386 loader does not load. DXVK's
# array of the two string pointers follows them 4-aligned: ptr0 = the strings, ptr1 = 15 bytes on; the new
# second string uses the 2 NUL bytes of padding before that array, and no pointer moves.
LOADER32=(b'winevulkan.dll\x00vulkan-1.dll\x00\x00\x00',b'vulkan-1.dll\x00\x00\x00winevulkan.dll\x00')
LOADER32_DLLS=('x32/d3d9.dll','x32/d3d11.dll','x32/dxgi.dll')
out=ROOT/'out/dxvk'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
if sha(ARCHIVE)!=SHA256:raise SystemExit('DXVK archive differs from the pinned release')
files={}
with tarfile.open(ARCHIVE) as archive:
    for arch in ('x64','x32'):
        (out/arch).mkdir(parents=True,exist_ok=True)
        for name in DLLS:
            member=archive.getmember('dxvk-%s/%s/%s'%(VERSION,arch,name))
            if not member.isfile():raise SystemExit('Unexpected archive entry: '+member.name)
            target=out/arch/name
            with archive.extractfile(member) as source:data=source.read()
            entry={'path':arch+'/'+name,'release_sha256':hashlib.sha256(data).hexdigest()}
            if arch+'/'+name in LOADER_DLLS:
                if data.count(LOADER[0])!=1 or data.count(b'winevulkan.dll')!=1:
                    raise SystemExit('DXVK loader names not found once in '+arch+'/'+name)
                data=data.replace(*LOADER);entry['patched']='Vulkan loader: vulkan-1.dll first (W197)'
            if arch+'/'+name in LOADER32_DLLS:
                # the pointer layout was checked in this release (the archive's SHA-256 is pinned above)
                if data.count(LOADER32[0])!=1 or data.count(b'winevulkan.dll')!=1:
                    raise SystemExit('DXVK loader names not found once in '+arch+'/'+name)
                data=data.replace(*LOADER32);entry['patched']='Vulkan loader: vulkan-1.dll, then winevulkan.dll (W247)'
            target.write_bytes(data)
            files[arch+'/'+name]=dict(entry,sha256=sha(target))
manifest={'schema_version':1,'version':VERSION,'source':'https://github.com/doitsujin/dxvk/releases/tag/v'+VERSION,
          'archive_sha256':SHA256,'license':'zlib','files':files,'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'version':VERSION,'files':len(files)}))
