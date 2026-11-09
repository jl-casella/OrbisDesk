#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build xinput for the hardware package: controller 0 is the console's pad (phase 7, W178).

Wine's xinput looks for controllers through HID (winebus and hidclass under winedevice), which a
PS4 title does not have. As prospero-win's patch 0470 does on the PS5 (upstream/prospero-win/wine/
patches/0470-xinput-ps5-title-controller.patch, rewritten here for the pinned Wine, whose context
differs), xinput gains a Unix library loaded by name, "xinput1_3", shared by every xinput version
built from dlls/xinput1_3. Its pad_init succeeds on the console and xinput then serves controller 0
from it and starts no HID thread:
- XInputGetState(Ex) and XInputGetKeystroke read the pad's state; after XInputEnable(FALSE) the
  state is neutral and still connected;
- XInputSetState and XInputEnable pass the rumble on;
- XInputGetCapabilities(Ex) report a wired Xbox 360 controller (045e:028e), which games look for;
  XInputGetBatteryInformation a wired one.
The Unix side calls the launcher's pw_wine_pad and pw_wine_set_rumble (native/hw_pad.c) directly:
the hardware ELF links every Unix library statically, so there is nothing to dlsym. Its call
tables become pw_xinput_unix_call_funcs and pw_xinput_unix_call_wow64_funcs for
platform/ps4/pw_wine_unixlibs.c (entry "xinput1_3.so"). One pad: 0471's four are for later.
The PE modules (xinput1_1, 1_2, 1_3, 1_4; x86_64 and i386) are compiled with the pinned build's
own commands (make -n) from the overlay; xinput9_1_0 forwards to xinput1_4 and is staged as built,
as is the 64-bit hid.dll xinput imports.
Output: out/xinput-hw/{x86_64,i386}-windows/*.dll, out/xinput-hw/xinput-unix.o, manifest.json.
"""
import hashlib,json,pathlib,shlex,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP='-ffile-prefix-map=%s=. -ffile-prefix-map=%s=vk-h0'%(ROOT,pathlib.Path.home()/'vk-h0')
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';UNIX=ROOT/'.deps/wine/ps4-unix'
work=ROOT/'build/xinput-hw';overlay=work/'overlay';out=ROOT/'out/xinput-hw'
MODULES=('xinput1_1','xinput1_2','xinput1_3','xinput1_4');ARCHES=('x86_64','i386')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
for folder in (work,out):
    if folder.exists():shutil.rmtree(folder)
shutil.copytree(SOURCE/'dlls/xinput1_3',overlay)
revisions=[]
def revise(old,new,why):
    target=overlay/'main.c';text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in main.c: '+old[:60])
    target.write_text(text.replace(old,new));revisions.append(why)

(overlay/'unixlib.h').write_text('''/*
 * The console's pad, for xinput (OrbisDesk, after prospero-win's patch 0470)
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 */

#include "wine/unixlib.h"

/* no pointers: the WoW64 calls are the same */
struct xinput_pad_state
{
    UINT32 packet;
    UINT16 buttons;  /* XINPUT_GAMEPAD_* */
    BYTE left_trigger;
    BYTE right_trigger;
    SHORT thumb_lx;
    SHORT thumb_ly;
    SHORT thumb_rx;
    SHORT thumb_ry;
    BYTE connected;
};

struct xinput_rumble_params
{
    UINT32 left;
    UINT32 right;
};

/* W213: kernelbase's guest launch/exit, for the pad's key profiles (native/hw_pad.c) */
struct xinput_profile_params
{
    char exe[260];  /* UTF-8 path or name of the guest program */
    UINT32 load;    /* 1: a guest started, 0: it ended */
};

enum xinput_unix_funcs
{
    unix_pad_init,
    unix_pad_state,
    unix_pad_rumble,
    unix_pad_profile,
    unix_funcs_count,
};
''')
(overlay/'unixlib.c').write_text('''/*
 * The console's pad, for xinput (OrbisDesk, after prospero-win's patch 0470)
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 */

#if 0
#pragma makedep unix
#endif

#include <stdarg.h>
#include <string.h>

#include "ntstatus.h"
#define WIN32_NO_STATUS
#include "windef.h"
#include "winternl.h"

#include "unixlib.h"

/* native/hw_pad.c: the launcher reads the pad and keeps its state; it also passes the rumble on.
 * An ELF without the launcher has weak definitions (platform/ps4/pw_wine_unixlibs.c) that report
 * no pad, and xinput then keeps its HID path. */
extern int pw_wine_pad_available( void );
extern int pw_wine_pad( struct xinput_pad_state *state );
extern void pw_wine_set_rumble( UINT32 left, UINT32 right );
extern void pw_wine_pad_profile( const char *exe, int load );

static NTSTATUS pad_init( void *args )
{
    return pw_wine_pad_available() ? STATUS_SUCCESS : STATUS_NOT_SUPPORTED;
}

static NTSTATUS pad_state( void *args )
{
    struct xinput_pad_state *state = args;

    if (!pw_wine_pad( state )) memset( state, 0, sizeof(*state) );
    return STATUS_SUCCESS;
}

static NTSTATUS pad_rumble( void *args )
{
    const struct xinput_rumble_params *params = args;

    pw_wine_set_rumble( params->left, params->right );
    return STATUS_SUCCESS;
}

static NTSTATUS pad_profile( void *args )
{
    struct xinput_profile_params *params = args;

    params->exe[sizeof(params->exe) - 1] = 0;
    pw_wine_pad_profile( params->exe, params->load );
    return STATUS_SUCCESS;
}

const unixlib_entry_t __wine_unix_call_funcs[] =
{
    pad_init,
    pad_state,
    pad_rumble,
    pad_profile,
};

C_ASSERT( ARRAYSIZE(__wine_unix_call_funcs) == unix_funcs_count );

#ifdef _WIN64

const unixlib_entry_t __wine_unix_call_wow64_funcs[] =
{
    pad_init,
    pad_state,
    pad_rumble,
    pad_profile,
};

C_ASSERT( ARRAYSIZE(__wine_unix_call_wow64_funcs) == unix_funcs_count );

#endif /* _WIN64 */
''')

revise('#include "wine/debug.h"\n','#include "wine/debug.h"\n\n#include "unixlib.h"\n','The pad\'s Unix library interface.')
revise('''static XINPUT_STATE current_state[XUSER_MAX_COUNT];
''','''static XINPUT_STATE current_state[XUSER_MAX_COUNT];

/* OrbisDesk (after prospero-win 0470): on the console, controller 0 is its pad, read by the
 * launcher; the HID stack this file otherwise uses does not exist there. */
static unixlib_handle_t console_pad;
static BOOL console_pad_enabled = TRUE;
static XINPUT_VIBRATION console_pad_vibration;

static BOOL WINAPI find_console_pad(INIT_ONCE *once, void *param, void **context)
{
    UNICODE_STRING name = RTL_CONSTANT_STRING(L"xinput1_3");
    unixlib_module_t module;
    unixlib_handle_t handle;
    NTSTATUS status;

    if ((status = __wine_load_unix_lib(&name, &module, &handle)))
    {
        TRACE("no Unix library, status %#lx: HID controllers\\n", status);
        return TRUE;
    }
    if ((status = __wine_unix_call(handle, unix_pad_init, NULL)))
    {
        TRACE("no console pad, status %#lx: HID controllers\\n", status);
        __wine_unload_unix_lib(module);
        return TRUE;
    }
    TRACE("controller 0 is the console's pad\\n");
    console_pad = handle;
    return TRUE;
}

static BOOL has_console_pad(void)
{
    static INIT_ONCE once = INIT_ONCE_STATIC_INIT;
    InitOnceExecuteOnce(&once, find_console_pad, NULL, NULL);
    return console_pad != 0;
}

/* W236: the controller type chosen in the overlay (native/hw_overlay.c writes C:\\orbis\\padtype.txt):
 * TRUE for an Xbox One controller; read at most once a second. A DualSense has no XInput on Windows,
 * so with it XInput stays an Xbox 360 controller. */
static BOOL console_pad_xbox_one(void)
{
    static DWORD checked;
    static BOOL one;
    DWORD now = GetTickCount(), got = 0;
    char text[16] = {0};
    HANDLE file;

    if (checked && now - checked < 1000) return one;
    checked = now | 1;
    file = CreateFileW(L"C:\\\\orbis\\\\padtype.txt", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                       NULL, OPEN_EXISTING, 0, NULL);
    if (file == INVALID_HANDLE_VALUE) one = FALSE;
    else
    {
        if (!ReadFile(file, text, sizeof(text) - 1, &got, NULL)) got = 0;
        CloseHandle(file);
        one = got >= 4 && !strncmp(text, "xone", 4);
    }
    return one;
}

static BOOL console_pad_state(DWORD index, XINPUT_STATE *state)
{
    struct xinput_pad_state pad = {0};

    if (index || __wine_unix_call(console_pad, unix_pad_state, &pad) || !pad.connected) return FALSE;
    memset(state, 0, sizeof(*state));
    state->dwPacketNumber = pad.packet;
    if (!console_pad_enabled) return TRUE;  /* XInputEnable(FALSE): neutral, still connected */
    state->Gamepad.wButtons = pad.buttons;
    state->Gamepad.bLeftTrigger = pad.left_trigger;
    state->Gamepad.bRightTrigger = pad.right_trigger;
    state->Gamepad.sThumbLX = pad.thumb_lx;
    state->Gamepad.sThumbLY = pad.thumb_ly;
    state->Gamepad.sThumbRX = pad.thumb_rx;
    state->Gamepad.sThumbRY = pad.thumb_ry;
    return TRUE;
}

/* xinput_cs must be held */
static void console_pad_rumble(void)
{
    struct xinput_rumble_params params = {0};

    if (console_pad_enabled)
    {
        params.left = console_pad_vibration.wLeftMotorSpeed;
        params.right = console_pad_vibration.wRightMotorSpeed;
    }
    __wine_unix_call(console_pad, unix_pad_rumble, &params);
}
''','Console pad: state and rumble through the Unix library.')
revise('''    TRACE("enable %d.\\n", enable);

    /* Setting to false''','''    TRACE("enable %d.\\n", enable);

    if (has_console_pad())
    {
        EnterCriticalSection(&xinput_cs);
        console_pad_enabled = enable;
        console_pad_rumble();
        LeaveCriticalSection(&xinput_cs);
        return;
    }

    /* Setting to false''','XInputEnable on the console pad.')
revise('''    TRACE("index %lu, vibration %p.\\n", index, vibration);

    start_update_thread();''','''    TRACE("index %lu, vibration %p.\\n", index, vibration);

    if (has_console_pad())
    {
        if (index >= XUSER_MAX_COUNT) return ERROR_BAD_ARGUMENTS;
        if (index) return ERROR_DEVICE_NOT_CONNECTED;
        EnterCriticalSection(&xinput_cs);
        console_pad_vibration = *vibration;
        console_pad_rumble();
        LeaveCriticalSection(&xinput_cs);
        return ERROR_SUCCESS;
    }

    start_update_thread();''','XInputSetState on the console pad.')
revise('''    if (!state) return ERROR_BAD_ARGUMENTS;

    start_update_thread();''','''    if (!state) return ERROR_BAD_ARGUMENTS;

    if (has_console_pad())
    {
        if (index >= XUSER_MAX_COUNT) return ERROR_BAD_ARGUMENTS;
        return console_pad_state(index, state) ? ERROR_SUCCESS : ERROR_DEVICE_NOT_CONNECTED;
    }

    start_update_thread();''','XInputGetState(Ex) and XInputGetKeystroke on the console pad.')
revise('''    if (!once++) FIXME("index %lu, type %u, battery %p.\\n", index, type, battery);

    if (index >= XUSER_MAX_COUNT) return ERROR_BAD_ARGUMENTS;''','''    if (!once++) FIXME("index %lu, type %u, battery %p.\\n", index, type, battery);

    if (index >= XUSER_MAX_COUNT) return ERROR_BAD_ARGUMENTS;
    if (has_console_pad())
    {
        XINPUT_STATE state;

        if (!console_pad_state(index, &state)) return ERROR_DEVICE_NOT_CONNECTED;
        battery->BatteryType = BATTERY_TYPE_WIRED;
        battery->BatteryLevel = BATTERY_LEVEL_FULL;
        return ERROR_SUCCESS;
    }''','XInputGetBatteryInformation: the console pad reports as wired.')
revise('''    TRACE("unk %lu, index %lu, flags %#lx, capabilities %p.\\n", unk, index, flags, caps);

    start_update_thread();''','''    TRACE("unk %lu, index %lu, flags %#lx, capabilities %p.\\n", unk, index, flags, caps);

    if (has_console_pad())
    {
        XINPUT_STATE state;

        if (index >= XUSER_MAX_COUNT) return ERROR_BAD_ARGUMENTS;
        if (!console_pad_state(index, &state)) return ERROR_DEVICE_NOT_CONNECTED;
        memset(caps, 0, sizeof(*caps));
        caps->Capabilities.Type = XINPUT_DEVTYPE_GAMEPAD;
        caps->Capabilities.SubType = XINPUT_DEVSUBTYPE_GAMEPAD;
        caps->Capabilities.Gamepad.wButtons = 0xf3ff;  /* every button but the guide */
        caps->Capabilities.Gamepad.bLeftTrigger = 0xff;
        caps->Capabilities.Gamepad.bRightTrigger = 0xff;
        caps->Capabilities.Gamepad.sThumbLX = (SHORT)0xffc0;
        caps->Capabilities.Gamepad.sThumbLY = (SHORT)0xffc0;
        caps->Capabilities.Gamepad.sThumbRX = (SHORT)0xffc0;
        caps->Capabilities.Gamepad.sThumbRY = (SHORT)0xffc0;
        caps->Capabilities.Vibration.wLeftMotorSpeed = 0xffff;
        caps->Capabilities.Vibration.wRightMotorSpeed = 0xffff;
        caps->VendorId = 0x045e;   /* a wired Xbox 360 controller, which games look for */
        caps->ProductId = console_pad_xbox_one() ? 0x02ea : 0x028e;   /* W236: or Xbox One */
        caps->VersionNumber = console_pad_xbox_one() ? 0x0408 : 0x0114;
        return ERROR_SUCCESS;
    }

    start_update_thread();''','XInputGetCapabilities(Ex): a wired Xbox 360 controller.')


# PE modules: the pinned build's commands, with the overlay's main.c and outputs under build/
targets=['dlls/%s/%s-windows/%s.dll'%(m,a,m) for m in MODULES for a in ARCHES]
dry=subprocess.run(['make','-n','-W','../../source/dlls/xinput1_3/main.c',*targets],cwd=BUILD,capture_output=True,text=True,check=True).stdout
dry=dry.replace('\\\n',' ');commands=[]
for line in dry.splitlines():
    if 'dlls/xinput' not in line or line.startswith('make'):continue
    line=line.replace('../../source/dlls/xinput1_3/main.c',str(overlay/'main.c'))
    for m in MODULES:
        for a in ARCHES:
            line=line.replace('dlls/%s/%s-windows/'%(m,a),str(work/m/a)+'/')
    commands.append(line)
if sum('winegcc' in c for c in commands)!=len(targets) or sum(str(overlay/'main.c') in c for c in commands)!=len(targets):
    raise SystemExit('make -n did not give one compile and one link per xinput module:\n'+dry[-3000:])
for m in MODULES:
    for a in ARCHES:(work/m/a).mkdir(parents=True,exist_ok=True)
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
modules={}
for a in ARCHES:
    (out/(a+'-windows')).mkdir(parents=True)
    for m in MODULES+('xinput9_1_0',):
        source=(work/m/a/(m+'.dll')) if m in MODULES else BUILD/'dlls'/m/(a+'-windows')/(m+'.dll')
        target=out/(a+'-windows')/(m+'.dll');shutil.copyfile(source,target)
        modules['%s/%s.dll'%(a,m)]={'path':'%s-windows/%s.dll'%(a,m),'sha256':sha(target),
                                   'patched':m in MODULES}
# xinput imports hid.dll, which the 64-bit view did not have (the 32-bit one is staged with the
# i386 DLLs); unpatched, from the pinned build, its own imports already in the prefix
target=out/'x86_64-windows/hid.dll';shutil.copyfile(BUILD/'dlls/hid/x86_64-windows/hid.dll',target)
modules['x86_64/hid.dll']={'path':'x86_64-windows/hid.dll','sha256':sha(target),'patched':False}

# Unix side: overlay/unixlib.c with the flags of the OrbisDesk Makefile's recipe for a Unix unit
# (as tools/build-unixlibs-ps4.py compiles platform sources), then local symbols and named tables.
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
unit='dlls/dnsapi/libresolv';compiled=work/'xinput-unixlib.o';final=out/'xinput-unix.o'
command=shlex.split(recipe(unit+'.o').replace('$@',str(compiled)))
wine_source=str(SOURCE/(unit+'.c'))
if command.count(wine_source)!=1:raise SystemExit('Unexpected recipe for '+unit)
command=[str(overlay/'unixlib.c') if arg==wine_source else arg for arg in command]
command+=['-D__ORBIS__','-I'+str(overlay),'-I'+str(ROOT/'platform/ps4'),'-ffunction-sections','-fdata-sections',
          '-include',str(ROOT/'platform/ps4/pw_wine_posix.h'),'-idirafter',str(BUILD/'include')]
run=subprocess.run(command,cwd=UNIX,capture_output=True,text=True)
if run.returncode:raise SystemExit(' '.join(command)[:300]+'\n'+run.stdout+run.stderr)
subprocess.run(['objcopy','--localize-hidden',
                '--redefine-sym','__wine_unix_call_funcs=pw_xinput_unix_call_funcs',
                '--redefine-sym','__wine_unix_call_wow64_funcs=pw_xinput_unix_call_wow64_funcs',
                str(compiled),str(final)],check=True)
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(__file__),'modules':modules,
          'unix_object':{'path':'xinput-unix.o','sha256':sha(final),
                         'tables':['pw_xinput_unix_call_funcs','pw_xinput_unix_call_wow64_funcs'],
                         'needs':['pw_wine_pad_available','pw_wine_pad','pw_wine_set_rumble','pw_wine_pad_profile']},
          'revisions':revisions,'commands':commands+[' '.join(command)]}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':len(modules),'unix_object':manifest['unix_object']['sha256'][:16],'revisions':len(revisions)}))
