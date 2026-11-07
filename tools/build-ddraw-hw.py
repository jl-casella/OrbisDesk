#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build the hardware variant of Wine's 32-bit ddraw.dll (PE32).

W128, phase 4b of the PE32 plan. Same method as build-taskmgr-hw.py: the pinned sources are
copied to an overlay and revised there; each object is compiled with the exact command the
pinned Wine build uses (taken from `make -n`), only with the overlay source and a separate
output.

In a windowed (DDSCL_NORMAL) program ddraw shows the primary surface by blitting it into the
swapchain's front buffer, which OpenGL draws straight to the window. wined3d's Vulkan
renderer has no front buffer it can blit into ("Unimplemented load from
WINED3D_LOCATION_DRAWABLE"): W127's ddraw7test32.exe drew a blank window, and Blitz3D
(SuperMarioKart.exe) ended in an access violation. With the Vulkan renderer the primary goes
into the back buffer and is presented to the part of the window it covers.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
overlay=ROOT/'.deps/wine/ddraw-hw-overlay';work=ROOT/'build/ddraw-hw';out=ROOT/'out/ddraw-hw'
UNITS=('surface',)
ARCH='i386-windows'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
if overlay.exists():shutil.rmtree(overlay)
shutil.copytree(SOURCE/'dlls/ddraw',overlay)
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
revisions=[]
def revise(path,old,new,why):
    target=overlay/path;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})

revise('surface.c','''        if (swap_interval)
            dst_texture = wined3d_swapchain_get_back_buffer(ddraw->wined3d_swapchain, 0);
        else
            dst_texture = wined3d_swapchain_get_front_buffer(ddraw->wined3d_swapchain);
''','''        /* OrbisDesk W128: wined3d's Vulkan renderer cannot blit into the front buffer
         * (WINED3D_LOCATION_DRAWABLE); there the primary goes into the back buffer and is
         * presented to the part of the swapchain window it covers. */
        if (!swap_interval && ddraw_vulkan_frontbuffer())
            return ddraw_vulkan_update_frontbuffer(ddraw, surface, rect);
        if (swap_interval)
            dst_texture = wined3d_swapchain_get_back_buffer(ddraw->wined3d_swapchain, 0);
        else
            dst_texture = wined3d_swapchain_get_front_buffer(ddraw->wined3d_swapchain);
''','Windowed primary updates through back buffer and present with the Vulkan renderer.')
revise('surface.c','''/* This is slow, of course. Also, in case of locks, we can't prevent other''','''/* OrbisDesk W128: the renderer is chosen per process with WINE_D3D_CONFIG (the launcher sets
 * renderer=vulkan for 32-bit programs, native/wine_hardware.c). */
static BOOL ddraw_vulkan_frontbuffer(void)
{
    static int vulkan = -1;
    char config[256];

    if (vulkan < 0)
    {
        DWORD len = GetEnvironmentVariableA("WINE_D3D_CONFIG", config, sizeof(config));
        vulkan = len && len < sizeof(config) && strstr(config, "renderer=vulkan");
        TRACE("Vulkan renderer front buffer path %d.\\n", vulkan);
    }
    return vulkan;
}

/* The primary covers the screen, the swapchain window only part of it: blit the visible part
 * of `rect` into the back buffer at the same place and present it at the window's client
 * coordinates. Parts outside the window are not on any surface Vulkan can present. */
static HRESULT ddraw_vulkan_update_frontbuffer(struct ddraw *ddraw, struct ddraw_surface *surface, const RECT *rect)
{
    struct wined3d_texture *back_buffer = wined3d_swapchain_get_back_buffer(ddraw->wined3d_swapchain, 0);
    RECT client, visible, dst;
    POINT origin = {0, 0};
    HRESULT hr;

    if (!GetClientRect(ddraw->swapchain_window, &client) || !ClientToScreen(ddraw->swapchain_window, &origin))
        return DD_OK;
    OffsetRect(&client, origin.x, origin.y);
    if (!IntersectRect(&visible, rect, &client))
        return DD_OK;
    if (FAILED(hr = wined3d_device_context_blt(ddraw->immediate_context, back_buffer, 0, &visible,
            ddraw_surface_get_any_texture(surface, DDRAW_SURFACE_READ), surface->sub_resource_idx, &visible, 0,
            NULL, WINED3D_TEXF_POINT)))
    {
        ERR("PWDDRAW back buffer blit %s failed, hr %#lx.\\n", wine_dbgstr_rect(&visible), hr);
        return hr;
    }
    dst = visible;
    OffsetRect(&dst, -origin.x, -origin.y);
    /* W232: the window is named: a NULL override makes wined3d go back to the device window at each
     * present (cs.c wined3d_cs_exec_present), undoing a clipper's window (quartz's VMR7 video window, W230) */
    if (FAILED(hr = wined3d_swapchain_present(ddraw->wined3d_swapchain, &visible, &dst, ddraw->swapchain_window, 0, 0)))
        ERR("PWDDRAW present %s to %s failed, hr %#lx.\\n", wine_dbgstr_rect(&visible), wine_dbgstr_rect(&dst), hr);
    return hr;
}

/* This is slow, of course. Also, in case of locks, we can't prevent other''','Helpers for the Vulkan front buffer path.')

dry=subprocess.run(['make','-n']+[f'-W../../source/dlls/ddraw/{u}.c' for u in UNITS]+
                   [f'dlls/ddraw/{ARCH}/ddraw.dll'],cwd=BUILD,capture_output=True,text=True,check=True).stdout
dry=dry.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'dlls/ddraw/' not in line:continue
    for u in UNITS:line=line.replace(f'../../source/dlls/ddraw/{u}.c',str(overlay/(u+'.c')))
    # Only the revised units and the link go to work/; the other objects are the pinned build's.
    for name in [u+'.o' for u in UNITS]+['ddraw.dll']:
        line=line.replace(f'dlls/ddraw/{ARCH}/'+name,str(work/name))
    commands.append(line)
if not all(any(str(overlay/(u+'.c')) in c for c in commands) for u in UNITS) or not any(str(work/'ddraw.dll') in c for c in commands):
    raise SystemExit('make -n did not give the ddraw commands:\n'+dry[-2000:])
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    if 'warning' in run.stderr:print(run.stderr)
target=out/'ddraw.dll';shutil.copyfile(work/'ddraw.dll',target)
manifest={'schema_version':1,'wine_commit':commit,'arch':ARCH,'ddraw':{'path':'ddraw.dll','sha256':sha(target)},
          'revisions':revisions,'commands':commands,
          'overlay_sha256':{u+'.c':sha(overlay/(u+'.c')) for u in UNITS},
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'ddraw':str(target.relative_to(ROOT)),'sha256':manifest['ddraw']['sha256'],'revisions':len(revisions)}))
