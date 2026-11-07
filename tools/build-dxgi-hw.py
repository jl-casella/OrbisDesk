#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variant of Wine's 64-bit dxgi.dll (PE64).

W192. Same method as build-ddraw-hw.py: the pinned sources are copied to an overlay and revised
there; each revised object is compiled with the exact command the pinned Wine build uses (taken
from `make -n`), only with the overlay source and a separate output.

Explorer and every 64-bit guest in its process load Wine's builtin dxgi (W190,
AppDefaults\\explorer.exe "dxgi"="builtin"): the Khronos loader, MangoHud and Gecko use it, and a
process holds one dxgi.dll. Direct3D 10/11 is DXVK's, and DXVK 2.x devices no longer offer the
interface Wine's factory creates swap chains with (IWineDXGISwapChainFactory): W189's
d3d11test64 failed with "This is not the device we're looking for". For a device that is neither
wined3d's nor a D3D12 queue, the factory now creates the swap chain through DXVK's own dxgi,
staged as system32\\dxvk_dxgi.dll so it can sit beside Wine's (tools/build-wine-hardware.py).
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/dxgi-hw-overlay';work=ROOT/'build/dxgi-hw';out=ROOT/'out/dxgi-hw'
UNITS=('factory',)
ARCH='x86_64-windows'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'dlls/dxgi',overlay)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[]
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})

revise('factory.c','''static HRESULT STDMETHODCALLTYPE dxgi_factory_CreateSwapChainForHwnd(IWineDXGIFactory *iface,''','''/* OrbisDesk W192: a swap chain for a DXVK device, through DXVK's dxgi (system32\\\\dxvk_dxgi.dll,
 * tools/build-dxgi-hw.py). The output is Wine's object, which DXVK's factory cannot use; Wine's
 * own path ignores it as well. */
static HRESULT dxgi_dxvk_swapchain(IUnknown *device, HWND window, const DXGI_SWAP_CHAIN_DESC1 *desc,
        const DXGI_SWAP_CHAIN_FULLSCREEN_DESC *fullscreen_desc, IDXGISwapChain1 **swapchain)
{
    static HRESULT (WINAPI *create_factory)(UINT flags, REFIID iid, void **factory);
    static LONG logged;
    IDXGIFactory2 *factory;
    HMODULE module;
    HRESULT hr;

    if (!create_factory)
    {
        if (!(module = LoadLibraryW(L"dxvk_dxgi.dll")))
        {
            ERR("PWDXGI dxvk_dxgi.dll did not load, error %lu.\\n", GetLastError());
            return DXGI_ERROR_UNSUPPORTED;
        }
        if (!(create_factory = (void *)GetProcAddress(module, "CreateDXGIFactory2")))
        {
            ERR("PWDXGI dxvk_dxgi.dll has no CreateDXGIFactory2.\\n");
            return DXGI_ERROR_UNSUPPORTED;
        }
    }
    if (FAILED(hr = create_factory(0, &IID_IDXGIFactory2, (void **)&factory)))
    {
        ERR("PWDXGI DXVK factory failed, hr %#lx.\\n", hr);
        return hr;
    }
    hr = IDXGIFactory2_CreateSwapChainForHwnd(factory, device, window, desc, fullscreen_desc, NULL, swapchain);
    IDXGIFactory2_Release(factory);
    if (FAILED(hr)) ERR("PWDXGI DXVK swap chain for window %p failed, hr %#lx.\\n", window, hr);
    else if (!InterlockedExchange(&logged, 1)) ERR("PWDXGI swap chain through DXVK's dxgi for window %p.\\n", window);
    return hr;
}

static HRESULT STDMETHODCALLTYPE dxgi_factory_CreateSwapChainForHwnd(IWineDXGIFactory *iface,''','Swap chain helper through DXVK dxgi.')
revise('factory.c','''        ID3D12CommandQueue_Release(command_queue);
        return hr;
    }

    ERR("This is not the device we're looking for.\\n");
    return DXGI_ERROR_UNSUPPORTED;
}''','''        ID3D12CommandQueue_Release(command_queue);
        return hr;
    }

    /* OrbisDesk W192: a DXVK Direct3D 10/11 device */
    return dxgi_dxvk_swapchain(device, window, desc, fullscreen_desc, swapchain);
}''','Devices that are not wined3d or D3D12 go to DXVK dxgi.')

dry=subprocess.run(['make','-n']+[f'-W../../source/dlls/dxgi/{u}.c' for u in UNITS]+
                   [f'dlls/dxgi/{ARCH}/dxgi.dll'],cwd=BUILD,capture_output=True,text=True,check=True).stdout
dry=dry.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'dlls/dxgi/' not in line:continue
    for u in UNITS:line=line.replace(f'../../source/dlls/dxgi/{u}.c',str(overlay/(u+'.c')))
    # Only the revised units and the link go to work/; the other objects are the pinned build's.
    for name in [u+'.o' for u in UNITS]+['dxgi.dll']:
        line=line.replace(f'dlls/dxgi/{ARCH}/'+name,str(work/name))
    commands.append(line)
if not all(any(str(overlay/(u+'.c')) in c for c in commands) for u in UNITS) or not any(str(work/'dxgi.dll') in c for c in commands):
    raise SystemExit('make -n did not give the dxgi commands:\n'+dry[-2000:])
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    if 'warning' in run.stderr:print(run.stderr)
target=out/'dxgi.dll';shutil.copyfile(work/'dxgi.dll',target)
manifest={'schema_version':1,'wine_commit':commit,'arch':ARCH,'dxgi':{'path':'dxgi.dll','sha256':sha(target)},
          'revisions':revisions,'commands':commands,
          'overlay_sha256':{u+'.c':sha(overlay/(u+'.c')) for u in UNITS},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'dxgi':str(target.relative_to(ROOT)),'sha256':manifest['dxgi']['sha256'],'revisions':len(revisions)}))
