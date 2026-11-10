#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build Wine's HID stack for the hardware package: the console's pad as an XInput HID gamepad.

Games such as Unity 2020 (classic input) and SDL find controllers only through HID: a raw input
device whose name holds "IG_" is paired with an XInput slot, then opened for its HID data. On a PC
winedevice.exe hosts winebus.sys -> winexinput.sys -> winehid.sys/hidclass.sys for that; a PS4 title
has one process and no service manager. Here:
- ntoskrnl.exe from an overlay of the pinned source (revisions below): drivers load from their
  service registry key when there is no service manager, and the IRP loop sets the named event
  PwNtoskrnlPnpReady once its PnP manager runs;
- hidclass.sys, hidparse.sys, winebus.sys, winehid.sys and winexinput.sys unchanged from the pinned
  build, and whatever of their imports the last hardware runtime lacks;
- winebus's Unix side (winebus-unix.o for the boot ELF): the pinned unixlib.c, hid.c and the
  bus_udev.c/bus_iohid.c stubs (no udev or IOKit in the Orbis build), with native/winebus_orbis.c in
  place of bus_sdl.c, linked with ld -r; its table becomes pw_winebus_unix_call_funcs for
  platform/ps4/pw_wine_unixlibs.c (entry "winebus.so"). It reads native/hw_pad.c's pw_wine_pad_peek;
- pwhidhost.dll (native/pwhidhost.c): explorer loads it; it runs the IRP loop and loads winebus.
Output: out/hidstack-hw/ (x86_64-windows/*, winebus-unix.o, pwhidhost.dll, manifest.json).
"""
import hashlib,json,pathlib,shlex,shutil,struct,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP='-ffile-prefix-map=%s=. -ffile-prefix-map=%s=vk-h0'%(ROOT,pathlib.Path.home()/'vk-h0')
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';UNIX=ROOT/'.deps/wine/ps4-unix'
work=ROOT/'build/hidstack-hw';overlay=work/'ntoskrnl-overlay';out=ROOT/'out/hidstack-hw'
# what the runtime already ships (an import found there is not staged again): the x64 modules of the
# staging manifests the product recipe builds before this one (tools/ci/build-product.py), not a
# previous hardware build, which a clean build does not have. W303's runtime gave the same closure.
PRESENT_MANIFESTS=('out/wine-pe64/manifest.json','out/wine-gui/manifest.json','out/wine-programs/manifest.json',
                   'out/wine-i386/manifest.json','out/wine-extras/manifest.json','out/mshtml-hw/manifest.json')
DRIVERS=('hidclass.sys','hidparse.sys','winebus.sys','winehid.sys','winexinput.sys')
CONT=chr(92)+chr(10)  # a make -n line continuation
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
# W206: hidclass.sys also from an overlay (a new client queue starts with the last report).
# W214: the W202/W205 diagnostic traces are gone; winexinput.sys and winebus.sys are the pinned build's.
OVERLAID={'ntoskrnl.exe':('ntoskrnl',),'hidclass.sys':('device',)}
def overlay_dir(module):return overlay if module=='ntoskrnl.exe' else work/(module+'-overlay')
for module in OVERLAID:
    if overlay_dir(module).exists():shutil.rmtree(overlay_dir(module))
    shutil.copytree(SOURCE/'dlls'/module,overlay_dir(module))
(out/'x86_64-windows').mkdir(exist_ok=True)
revisions=[];commands=[]
def revise(path,old,new,why):
    """path: a unit of ntoskrnl's overlay, or "<module>:<unit>" for another overlay"""
    module,_,unit=path.rpartition(':')
    target=overlay_dir(module or 'ntoskrnl.exe')/unit;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in '+path+': '+old[:60])
    target.write_text(text.replace(old,new));revisions.append({'path':path,'why':why})
def run(command,cwd=None,shell=False):
    commands.append(command if shell else ' '.join(map(str,command)))
    result=subprocess.run(command,cwd=cwd,shell=shell,capture_output=True,text=True)
    if result.returncode:raise SystemExit(str(command)[:400]+'\n'+result.stdout+result.stderr)
    if 'warning' in result.stderr:print(result.stderr)

# ntoskrnl: no service manager in a title
revise('ntoskrnl.c','''    if (!(manager_handle = OpenSCManagerW( NULL, NULL, SC_MANAGER_CONNECT )))
    {
        WARN( "failed to connect to service manager\\n" );
        RtlFreeHeap( GetProcessHeap(), 0, name );
        return STATUS_NOT_SUPPORTED;
    }
''','''    /* OrbisDesk: a PS4 title has no service manager, and asking for one is not a reliable test:
     * W198 got a non-NULL handle back from OpenSCManagerW after RPC_S_SERVER_UNAVAILABLE, then
     * OpenServiceW failed on it (NDRCContextBinding invalid handle). The driver is accepted from
     * its service key, with the type check QueryServiceConfig would make; it has no service status. */
    {
        DWORD type = 0, size = sizeof(type);
        LONG error = RegGetValueW( HKEY_LOCAL_MACHINE, name + 18 /* skip \\registry\\machine\\ */, L"Type",
                                   RRF_RT_REG_DWORD, NULL, &type, &size );
        *service = NULL;
        if (error || (type != SERVICE_KERNEL_DRIVER && type != SERVICE_FILE_SYSTEM_DRIVER))
        {
            ERR( "PWHID driver %s: service key error %ld, type %lu\\n", debugstr_w(name), error, type );
            RtlFreeHeap( GetProcessHeap(), 0, name );
            return STATUS_UNSUCCESSFUL;
        }
        ERR( "PWHID driver %s from its service key\\n", debugstr_w(name) );
        RtlFreeHeap( GetProcessHeap(), 0, name );
        return STATUS_SUCCESS;
    }

    if (!(manager_handle = OpenSCManagerW( NULL, NULL, SC_MANAGER_CONNECT )))
    {
        WARN( "failed to connect to service manager\\n" );
        RtlFreeHeap( GetProcessHeap(), 0, name );
        return STATUS_NOT_SUPPORTED;
    }
''','W200: load a kernel driver from its service registry key, never through the service manager.')
# ntoskrnl relocates every executable the loader left unrelocated (winedevice only loads drivers).
# Here guest programs are executables loaded away from their base and already relocated by the
# guest loader: a second pass broke their pointers (W198: faults at 0xC02xxxxx in wfm.exe and
# rundll32). Only native-subsystem images, the drivers, are its business.
revise('ntoskrnl.c','''    module = data->Loaded.DllBase;
    nt = RtlImageNtHeader( module );
    base = (char *)nt->OptionalHeader.ImageBase;''','''    module = data->Loaded.DllBase;
    nt = RtlImageNtHeader( module );
    /* OrbisDesk: drivers only; guest executables share this process */
    if (nt->OptionalHeader.Subsystem != IMAGE_SUBSYSTEM_NATIVE) return;
    base = (char *)nt->OptionalHeader.ImageBase;''','W200: relocate and fix the security cookie of drivers only, not of guest programs.')
revise('ntoskrnl.c','''    SERVICE_STATUS status;
    status.dwServiceType             = SERVICE_WIN32;''','''    SERVICE_STATUS status;
    if (!handle) return;  /* OrbisDesk: a driver loaded without the service manager */
    status.dwServiceType             = SERVICE_WIN32;''','No service status for a driver loaded without the service manager.')
revise('ntoskrnl.c','''    pnp_manager_start();

    handles[0] = stop_event;''','''    pnp_manager_start();

    /* OrbisDesk: pwhidhost.dll loads winebus once the PnP manager exists (winedevice gets that
     * order from the service manager) */
    {
        HANDLE ready = OpenEventW( EVENT_MODIFY_STATE, FALSE, L"PwNtoskrnlPnpReady" );
        if (ready) { SetEvent( ready ); CloseHandle( ready ); }
        ERR( "PWHID irp loop running, ready event %s\\n", ready ? "set" : "absent" );
    }

    handles[0] = stop_event;''','Tell pwhidhost.dll when the PnP manager has started.')
# W206: a new client queue starts with the device's last report. W205: Unity's first read on the pad
# (issued by its main thread) stayed pending in hidclass; when a report completed it, the completion
# needs a system APC on that thread (server/async.c APC_ASYNC_IO), which that thread did not run, so
# its OVERLAPPED event never fired and Unity's input thread never read again. A read that a queued
# report completes during the dispatch is finished while the requesting thread waits for the initial
# status, so the first read no longer depends on a later APC; Unity's input thread issues the next
# ones and waits in WaitForMultipleObjects, where its APCs run. The extra report is the current state.
revise('hidclass.sys:device.c','''static void hid_device_queue_input( struct phys_device *pdo, HID_XFER_PACKET *packet, BOOL polled )
{''','''/* OrbisDesk (W206): each device's last report, to start a new client queue with */
static struct { struct phys_device *pdo; struct hid_report *report; } pw_last[16];
static KSPIN_LOCK pw_last_lock;
static void pw_last_set( struct phys_device *pdo, struct hid_report *report )
{
    struct hid_report *old = NULL;
    unsigned int i;
    KIRQL irql;

    KeAcquireSpinLock( &pw_last_lock, &irql );
    for (i = 0; i < ARRAY_SIZE(pw_last); i++) if (pw_last[i].pdo == pdo || !pw_last[i].pdo) break;
    if (i < ARRAY_SIZE(pw_last))
    {
        hid_report_incref( report );
        old = pw_last[i].report;
        pw_last[i].pdo = pdo;
        pw_last[i].report = report;
    }
    KeReleaseSpinLock( &pw_last_lock, irql );
    hid_report_decref( old );
}
static struct hid_report *pw_last_get( struct phys_device *pdo )
{
    struct hid_report *report = NULL;
    unsigned int i;
    KIRQL irql;

    KeAcquireSpinLock( &pw_last_lock, &irql );
    for (i = 0; i < ARRAY_SIZE(pw_last) && pw_last[i].pdo; i++)
        if (pw_last[i].pdo == pdo && (report = pw_last[i].report)) { hid_report_incref( report ); break; }
    KeReleaseSpinLock( &pw_last_lock, irql );
    return report;
}

static void hid_device_queue_input( struct phys_device *pdo, HID_XFER_PACKET *packet, BOOL polled )
{''','W206: remember the last report of each device.')
revise('hidclass.sys:device.c','''    InitializeListHead( &completed );

    KeAcquireSpinLock( &pdo->lock, &irql );
    if (pdo->removed) WARN( "Device has been removed, dropping report\\n" );''','''    InitializeListHead( &completed );
    pw_last_set( pdo, last_report );

    KeAcquireSpinLock( &pdo->lock, &irql );
    if (pdo->removed) WARN( "Device has been removed, dropping report\\n" );''','W206: store the last report.')
revise('hidclass.sys:device.c','''    if (!(queue = hid_queue_create())) irp->IoStatus.Status = STATUS_NO_MEMORY;
    else
    {''','''    if (!(queue = hid_queue_create())) irp->IoStatus.Status = STATUS_NO_MEMORY;
    else
    {
        struct hid_report *last;
        if ((last = pw_last_get( pdo )))
        {
            hid_queue_push_report( queue, last );
            hid_report_decref( last );
        }''','W206: a new client queue starts with the last report.')

# The pinned build's own commands for each overlaid module (make -n), with the overlay units and
# separate outputs; the other objects are the pinned build's own.
def build_overlay(module,units):
    folder=overlay_dir(module);out_dir=work/(module+'-build');out_dir.mkdir(exist_ok=True)
    dry=subprocess.run(['make','-n']+['-W../../source/dlls/%s/%s.c'%(module,u) for u in units]+
                       ['dlls/%s/x86_64-windows/%s'%(module,module)],cwd=BUILD,capture_output=True,text=True,check=True).stdout
    steps=[]
    for line in dry.replace(CONT,' ').splitlines():
        if 'dlls/%s/'%module not in line:continue
        for u in units:
            line=line.replace('../../source/dlls/%s/%s.c'%(module,u),str(folder/(u+'.c')))
            line=line.replace('dlls/%s/x86_64-windows/%s.o'%(module,u),str(out_dir/(u+'.o')))
        line=line.replace('dlls/%s/x86_64-windows/%s'%(module,module),str(out_dir/module))
        steps.append(line)
    if not all(any(str(folder/(u+'.c')) in s for s in steps) for u in units) or not any(str(out_dir/module) in s for s in steps):
        raise SystemExit('make -n did not give the %s commands: '%module+dry[-2000:])
    for step in steps:run(step,cwd=BUILD,shell=True)
    return out_dir/module
built_overlays={module:build_overlay(module,units) for module,units in OVERLAID.items()}

# PE modules and the imports the last hardware runtime lacks
def imports(path):
    data=path.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0];optional=pe+24
    count=struct.unpack_from('<H',data,pe+6)[0];size=struct.unpack_from('<H',data,pe+20)[0]
    sections=[struct.unpack_from('<IIII',data,optional+size+40*i+8) for i in range(count)]
    def offset(rva):
        for vsize,address,raw_size,raw in sections:
            if address<=rva<address+max(vsize,raw_size):return raw+rva-address
    names=set()
    for directory,entry_size,field in ((1,20,12),(13,32,4)):
        rva=struct.unpack_from('<I',data,optional+112+8*directory)[0];at=offset(rva) if rva else None
        while at is not None:
            entry=data[at:at+entry_size]
            if entry==bytes(entry_size):break
            name_at=offset(struct.unpack_from('<I',entry,field)[0])
            names.add(data[name_at:data.index(b'\0',name_at)].decode().lower());at+=entry_size
    return names
def built(name):
    stem=name.rsplit('.',1)[0] if not name.endswith('.exe') else name
    for candidate in (BUILD/'dlls'/name/'x86_64-windows'/name,BUILD/'dlls'/stem/'x86_64-windows'/name):
        if candidate.is_file():return candidate
modules={'ntoskrnl.exe':built_overlays['ntoskrnl.exe']}
for name in DRIVERS:modules[name]=built_overlays.get(name) or built(name)
pending=list(modules)
present=set()
for path in PRESENT_MANIFESTS:
    listed=json.loads((ROOT/path).read_text())
    if path=='out/wine-i386/manifest.json':names=listed['modules_x64']
    elif path=='out/wine-extras/manifest.json':names=[k.split('/')[1] for k in listed['modules'] if k.startswith('x86_64')]
    elif path=='out/mshtml-hw/manifest.json':names=listed['modules']['x86_64-windows']
    else:names=listed['modules']
    present|={n.lower() for n in names}
while pending:
    for name in sorted(imports(modules[pending.pop()])):
        if name in modules or name in present or name.startswith(('api-ms-','ext-ms-')):continue
        source=built(name)
        if not source:raise SystemExit('Import without a pinned build: '+name)
        modules[name]=source;pending.append(name)
staged={}
for name,source in modules.items():
    target=out/'x86_64-windows'/name;shutil.copyfile(source,target)
    staged[name]={'path':'x86_64-windows/'+name,'sha256':sha(target),'patched':name in OVERLAID,
                  'driver':name.endswith('.sys')}

# winebus's Unix side: the Orbis build's recipes for its units, bus_sdl.c replaced by the pad bus
makefile=(UNIX/'Makefile').read_text().splitlines()
def recipe(target):
    index=next((i for i,line in enumerate(makefile) if line.startswith(target+': ') and i+1<len(makefile)
                and makefile[i+1].startswith('\t$(CC)')),None)
    if index is None:raise SystemExit('No recipe for '+target)
    parts=[];index+=1
    while True:
        line=makefile[index];parts.append(line.rstrip().removesuffix('\\'))
        if not line.rstrip().endswith('\\'):break
        index+=1
    return ' '.join(parts).replace('$(CC)',str(UNIX/'orbis-cc')).replace('$(CFLAGS)','-g -O2 '+PREFIX_MAP)
units=[]
for unit,source in (('unixlib',None),('hid',None),('bus_udev',None),('bus_iohid',None),
                    ('bus_sdl',ROOT/'native/winebus_orbis.c')):
    compiled=work/('winebus-'+unit+'.o')
    command=shlex.split(recipe('dlls/winebus.sys/'+unit+'.o').replace('$@',str(compiled)))
    if source:
        pinned=str(SOURCE/'dlls/winebus.sys'/(unit+'.c'))
        if command.count(pinned)!=1:raise SystemExit('Unexpected recipe for '+unit)
        command=[str(source) if arg==pinned else arg for arg in command]
    command+=['-D__ORBIS__','-ffunction-sections','-fdata-sections',
              '-include',str(ROOT/'platform/ps4/pw_wine_posix.h'),'-idirafter',str(BUILD/'include')]
    run(command,cwd=UNIX);units.append(compiled)
combined=work/'winebus-unix-combined.o';final=out/'winebus-unix.o'
run(['ld.lld','-r','-o',str(combined)]+[str(u) for u in units])
run(['objcopy','--localize-hidden','--redefine-sym','__wine_unix_call_funcs=pw_winebus_unix_call_funcs',
     str(combined),str(final)])
undefined=subprocess.run(['nm','-u',str(final)],capture_output=True,text=True,check=True).stdout.split()

# pwhidhost.dll
host=out/'pwhidhost.dll'
run(['x86_64-w64-mingw32-gcc','-std=c11','-O2','-Wall','-municode','-shared',*PREFIX_MAP.split(),str(ROOT/'native/pwhidhost.c'),
     '-o',str(host),'-ladvapi32','-Wl,--no-insert-timestamp','-s'])

manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(__file__),
          'present_from':list(PRESENT_MANIFESTS),'modules':staged,
          'unix_object':{'path':'winebus-unix.o','sha256':sha(final),'tables':['pw_winebus_unix_call_funcs'],
                         'needs':['pw_wine_pad_available','pw_wine_pad_peek','pw_wine_set_rumble'],
                         'undefined':[s for s in undefined if s.startswith('pw_')]},
          'host':{'path':'pwhidhost.dll','sha256':sha(host),'source_sha256':sha(ROOT/'native/pwhidhost.c')},
          'bus_source_sha256':sha(ROOT/'native/winebus_orbis.c'),
          'overlay_sha256':{m+'/'+u+'.c':sha(overlay_dir(m)/(u+'.c')) for m,units in OVERLAID.items() for u in units},'revisions':revisions,'commands':commands,
          'hardware_validation':'pending'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':sorted(staged),'unix_object':manifest['unix_object']['sha256'][:16],
                  'host':manifest['host']['sha256'][:16],'revisions':len(revisions)}))
