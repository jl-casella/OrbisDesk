#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""W287: the i386 Khronos loader without a DXGI factory (tools/vk-h0/build-vulkan-loader-i386.sh).

    python3 patch-vulkan-loader-i386-nodxgi.py COPY/loader/loader_windows.c

Run on a copy of Vulkan-Loader v1.4.335, never on ~/vk-h0/src (the x64 loader is built from it). In explorer's
32-bit world syswow64's dxgi.dll is Wine's: a factory creates a wined3d adapter, and wined3d goes through this
loader (W257: endless recursion; W258: one more RADV instance per factory). CreateDXGIFactory1 becomes a function
that answers E_NOINTERFACE: no sorting of physical devices (one GPU), and registry drivers are taken without the
DXGI vendor check (it applies only to the loader's known vendor drivers, never to winevulkan.json).
Each change is checked against the text it expects; on a mismatch nothing is written.
"""
import pathlib,sys

if len(sys.argv)!=2:raise SystemExit(__doc__)
path=pathlib.Path(sys.argv[1]);text=path.read_text()
if 'pw_no_dxgi_factory' in text:raise SystemExit('NOT APPLIED: %s is patched already'%path)
EDITS=[
('''PFN_CreateDXGIFactory1 fpCreateDXGIFactory1;
''','''PFN_CreateDXGIFactory1 fpCreateDXGIFactory1;
/* Orbis-win W287: no DXGI in this loader (explorer's 32-bit world: Wine's dxgi creates a wined3d adapter, which goes
 * through this loader again) */
static HRESULT APIENTRY pw_no_dxgi_factory(REFIID riid, void **ppFactory) {
    (void)riid;
    *ppFactory = NULL;
    return E_NOINTERFACE;
}
'''),
('''    HMODULE dxgi_module = LoadLibraryW(systemPath);
    fpCreateDXGIFactory1 =
        dxgi_module == NULL ? NULL : (PFN_CreateDXGIFactory1)(void *)GetProcAddress(dxgi_module, "CreateDXGIFactory1");
''','''    (void)systemPath;  /* Orbis-win W287: dxgi.dll is not loaded */
    fpCreateDXGIFactory1 = pw_no_dxgi_factory;
'''),
('''        HRESULT hres = fpCreateDXGIFactory1(&IID_IDXGIFactory1, (void **)&dxgi_factory);
        if (hres != S_OK) {
            loader_log(inst, VULKAN_LOADER_WARN_BIT | log_target_flag, 0,
                       "windows_get_registry_files: Failed to create dxgi factory for ICD registry verification. No ICDs will be "
                       "added from "
                       "legacy registry locations");
            goto out;
        }
''','''        HRESULT hres = fpCreateDXGIFactory1(&IID_IDXGIFactory1, (void **)&dxgi_factory);
        if (hres != S_OK) {
            /* Orbis-win W287: no DXGI here; registry drivers are taken without the vendor check */
            loader_log(inst, VULKAN_LOADER_INFO_BIT | log_target_flag, 0,
                       "windows_get_registry_files: no dxgi factory (Orbis-win W287); registry drivers are not verified");
            dxgi_factory = NULL;
        }
'''),
('''                        if (i == sizeof(known_drivers) / sizeof(known_drivers[0])) {
''','''                        if (i == sizeof(known_drivers) / sizeof(known_drivers[0]) || dxgi_factory == NULL) {  /* W287 */
'''),
]
errors=[]
for old,new in EDITS:
    if text.count(old)!=1:errors.append('expected 1 match, found %d, of: %s'%(text.count(old),old.strip().splitlines()[0]))
    else:text=text.replace(old,new)
if errors:
    print('NOT APPLIED to %s; nothing was written:'%path)
    for e in errors:print('- '+e)
    raise SystemExit(1)
path.write_text(text)
print('patched',path)
