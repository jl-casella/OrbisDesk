#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build dinput and dinput8 for the hardware package: the console's pad as a DirectInput gamepad (phase 7, W179).

Wine's DirectInput finds joysticks only through HID (dlls/dinput/joystick_hid.c), which a PS4 title
does not have, so no game controller appeared. A new device, joystick_pad.c (written here, not from
prospero-win), shows XInput controller 0 (the console's pad, tools/build-xinput-hw.py) as a gamepad
laid out like Windows' Xbox 360 controller driver: X/Y the left stick, Rx/Ry the right one, Z both
triggers, ten buttons (A B X Y LB RB Back Start LS RS) and the d-pad as a POV hat; VID/PID 045e:028e.
It polls XInput every 8 ms on dinput's input thread through a waitable timer (its read_event), and
on Poll(); the axes follow the range, dead zone and saturation the program sets, as joystick_hid.c's
scale_axis_value does. dinput.c enumerates it with the game controllers and creates it by GUID.
Reading XInput counts for native/hw_pad.c's game mode, so the pad stops driving the pointer then.
dinput and dinput8 (x86_64 and i386) are compiled with the pinned build's own commands (make -n):
dinput.c from the overlay, joystick_pad.c with joystick_hid.c's command, linked in after it.
Output: out/dinput-hw/{x86_64,i386}-windows/{dinput,dinput8}.dll and manifest.json.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
work=ROOT/'build/dinput-hw';overlay=work/'overlay';out=ROOT/'out/dinput-hw'
MODULES=('dinput','dinput8');ARCHES=('x86_64','i386')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
for folder in (work,out):
    if folder.exists():shutil.rmtree(folder)
shutil.copytree(SOURCE/'dlls/dinput',overlay)
revisions=[]
def revise(old,new,why):
    target=overlay/'dinput.c';text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in dinput.c: '+old[:60])
    target.write_text(text.replace(old,new));revisions.append(why)

(overlay/'joystick_pad.c').write_text(r'''/*
 * DirectInput gamepad backed by XInput controller 0 (OrbisDesk, phase 7)
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 */

#include <stdarg.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>

#include "windef.h"
#include "winbase.h"
#include "winerror.h"
#include "winuser.h"
#include "winreg.h"
#include "ddk/hidclass.h"
#include "cfgmgr32.h"
#include "devguid.h"
#include "dinput.h"
#include "xinput.h"

#include "dinput_private.h"
#include "device_private.h"
#include "wine/debug.h"

WINE_DEFAULT_DEBUG_CHANNEL(dinput);

/* On the PS4 there is no HID stack, so joystick_hid.c's devices never appear. The console's pad is
 * XInput controller 0 (xinput built by tools/build-xinput-hw.py); this device shows it to
 * DirectInput as a gamepad laid out like Windows' Xbox 360 controller driver. */

static const GUID pad_instance_guid = {0x6f726269,0x7350,0x6164,{0x80,0x00,0x00,0x00,0x00,0x00,0x00,0x01}};

#define PAD_VENDOR  0x045e
#define PAD_PRODUCT (pad_xbox_one() ? 0x02ea : 0x028e)  /* W236 */

/* W236: the controller type chosen in the overlay (native/hw_overlay.c, C:\orbis\padtype.txt): TRUE
 * for an Xbox One controller, read at most once a second. A DualSense keeps this device an Xbox 360
 * one: its layout here is the Xbox driver's (winebus adds the DualSense as an HID device). */
static BOOL pad_xbox_one(void)
{
    static DWORD checked;
    static BOOL one;
    DWORD now = GetTickCount(), got = 0;
    char text[16] = {0};
    HANDLE file;

    if (checked && now - checked < 1000) return one;
    checked = now | 1;
    file = CreateFileW( L"C:\\orbis\\padtype.txt", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                        NULL, OPEN_EXISTING, 0, NULL );
    if (file == INVALID_HANDLE_VALUE) one = FALSE;
    else
    {
        if (!ReadFile( file, text, sizeof(text) - 1, &got, NULL )) got = 0;
        CloseHandle( file );
        one = got >= 4 && !strncmp( text, "xone", 4 );
    }
    return one;
}
#define PAD_AXES    5
#define PAD_BUTTONS 10
#define PAD_POLL_MS 8

static const struct
{
    const GUID *type;
    DWORD offset;
    USHORT usage;
    const WCHAR *name;
} pad_axes[PAD_AXES] =
{
    {&GUID_XAxis,  DIJOFS_X,  0x30, L"X Axis"},
    {&GUID_YAxis,  DIJOFS_Y,  0x31, L"Y Axis"},
    {&GUID_ZAxis,  DIJOFS_Z,  0x32, L"Z Axis"},
    {&GUID_RxAxis, DIJOFS_RX, 0x33, L"X Rotation"},
    {&GUID_RyAxis, DIJOFS_RY, 0x34, L"Y Rotation"},
};

static const WORD pad_buttons[PAD_BUTTONS] =
{
    XINPUT_GAMEPAD_A, XINPUT_GAMEPAD_B, XINPUT_GAMEPAD_X, XINPUT_GAMEPAD_Y,
    XINPUT_GAMEPAD_LEFT_SHOULDER, XINPUT_GAMEPAD_RIGHT_SHOULDER, XINPUT_GAMEPAD_BACK, XINPUT_GAMEPAD_START,
    XINPUT_GAMEPAD_LEFT_THUMB, XINPUT_GAMEPAD_RIGHT_THUMB,
};

static DWORD (WINAPI *pXInputGetState)( DWORD, XINPUT_STATE * );

static BOOL WINAPI load_xinput( INIT_ONCE *once, void *param, void **context )
{
    HMODULE module = LoadLibraryW( L"xinput1_4.dll" );

    if (module) pXInputGetState = (void *)GetProcAddress( module, "XInputGetState" );
    if (!pXInputGetState) WARN( "no xinput, no pad\n" );
    return TRUE;
}

static BOOL pad_state( XINPUT_STATE *state )
{
    static INIT_ONCE once = INIT_ONCE_STATIC_INIT;

    InitOnceExecuteOnce( &once, load_xinput, NULL, NULL );
    return pXInputGetState && !pXInputGetState( 0, state );
}

struct pad_joystick
{
    struct dinput_device base;
    DWORD packet;
    BOOL have_packet;
};

static inline struct pad_joystick *impl_from_IDirectInputDevice8W( IDirectInputDevice8W *iface )
{
    return CONTAINING_RECORD( CONTAINING_RECORD( iface, struct dinput_device, IDirectInputDevice8W_iface ),
                              struct pad_joystick, base );
}

HRESULT pad_joystick_enum_device( DWORD type, DWORD flags, DIDEVICEINSTANCEW *instance, DWORD version )
{
    XINPUT_STATE state;
    DWORD size;

    TRACE( "type %#lx, flags %#lx, instance %p, version %#lx\n", type, flags, instance, version );

    if (!pad_state( &state )) return DIERR_DEVICENOTREG;

    size = instance->dwSize;
    memset( instance, 0, size );
    instance->dwSize = size;
    instance->guidInstance = pad_instance_guid;
    instance->guidProduct = dinput_pidvid_guid;
    instance->guidProduct.Data1 = MAKELONG( PAD_VENDOR, PAD_PRODUCT );
    if (version >= 0x0800) instance->dwDevType = DI8DEVTYPE_GAMEPAD | (DI8DEVTYPEGAMEPAD_STANDARD << 8);
    else instance->dwDevType = DIDEVTYPE_JOYSTICK | (DIDEVTYPEJOYSTICK_GAMEPAD << 8);
    instance->dwDevType |= DIDEVTYPE_HID;
    lstrcpynW( instance->tszInstanceName, L"Orbis Pad", MAX_PATH );
    lstrcpynW( instance->tszProductName, pad_xbox_one() ? L"Controller (Xbox One For Windows)"
                                                        : L"Controller (XBOX 360 For Windows)", MAX_PATH );
    if (size >= sizeof(DIDEVICEINSTANCEW))
    {
        instance->wUsagePage = 0x01;  /* generic desktop */
        instance->wUsage = 0x05;      /* game pad */
    }
    return DI_OK;
}

static BOOL try_enum_object( struct dinput_device *impl, const DIPROPHEADER *filter, DWORD flags, enum_object_callback callback,
                             UINT index, DIDEVICEOBJECTINSTANCEW *instance, void *data )
{
    if (flags != DIDFT_ALL && !(flags & DIDFT_GETTYPE( instance->dwType ))) return DIENUM_CONTINUE;

    switch (filter->dwHow)
    {
    case DIPH_DEVICE:
        return callback( impl, index, NULL, instance, data );
    case DIPH_BYOFFSET:
        if (filter->dwObj != instance->dwOfs) return DIENUM_CONTINUE;
        return callback( impl, index, NULL, instance, data );
    case DIPH_BYID:
        if ((filter->dwObj & 0x00ffffff) != (instance->dwType & 0x00ffffff)) return DIENUM_CONTINUE;
        return callback( impl, index, NULL, instance, data );
    }

    return DIENUM_CONTINUE;
}

/* in the device format's order: the axes, the POV, then the buttons */
static HRESULT pad_enum_objects( IDirectInputDevice8W *iface, const DIPROPHEADER *filter,
                                 DWORD flags, enum_object_callback callback, void *context )
{
    struct pad_joystick *impl = impl_from_IDirectInputDevice8W( iface );
    DIDEVICEOBJECTINSTANCEW instance;
    UINT index = 0, i;

    for (i = 0; i < PAD_AXES; i++, index++)
    {
        memset( &instance, 0, sizeof(instance) );
        instance.dwSize = sizeof(instance);
        instance.guidType = *pad_axes[i].type;
        instance.dwOfs = pad_axes[i].offset;
        instance.dwType = DIDFT_ABSAXIS | DIDFT_MAKEINSTANCE( i );
        instance.dwFlags = DIDOI_ASPECTPOSITION;
        instance.wUsagePage = 0x01;
        instance.wUsage = pad_axes[i].usage;
        lstrcpynW( instance.tszName, pad_axes[i].name, MAX_PATH );
        if (try_enum_object( &impl->base, filter, flags, callback, index, &instance, context ) != DIENUM_CONTINUE)
            return DIENUM_STOP;
    }

    memset( &instance, 0, sizeof(instance) );
    instance.dwSize = sizeof(instance);
    instance.guidType = GUID_POV;
    instance.dwOfs = DIJOFS_POV( 0 );
    instance.dwType = DIDFT_POV | DIDFT_MAKEINSTANCE( 0 );
    instance.wUsagePage = 0x01;
    instance.wUsage = 0x39;  /* hat switch */
    lstrcpynW( instance.tszName, L"Hat Switch", MAX_PATH );
    if (try_enum_object( &impl->base, filter, flags, callback, index++, &instance, context ) != DIENUM_CONTINUE)
        return DIENUM_STOP;

    for (i = 0; i < PAD_BUTTONS; i++, index++)
    {
        memset( &instance, 0, sizeof(instance) );
        instance.dwSize = sizeof(instance);
        instance.guidType = GUID_Button;
        instance.dwOfs = DIJOFS_BUTTON( i );
        instance.dwType = DIDFT_PSHBUTTON | DIDFT_MAKEINSTANCE( i );
        instance.wUsagePage = 0x09;  /* buttons */
        instance.wUsage = i + 1;
        swprintf( instance.tszName, MAX_PATH, L"Button %u", i );
        if (try_enum_object( &impl->base, filter, flags, callback, index, &instance, context ) != DIENUM_CONTINUE)
            return DIENUM_STOP;
    }

    return DIENUM_CONTINUE;
}

static BOOL init_object_properties( struct dinput_device *device, UINT index, struct hid_value_caps *caps,
                                    const DIDEVICEOBJECTINSTANCEW *instance, void *data )
{
    struct object_properties *properties;

    if (index == -1) return DIENUM_STOP;
    properties = device->object_properties + index;

    properties->bit_size = 16;
    properties->logical_min = properties->physical_min = -32768;
    properties->logical_max = properties->physical_max = 32767;
    properties->range_min = 0;
    properties->range_max = (instance->dwType & DIDFT_AXIS) ? 65535 : 35900;
    properties->saturation = 10000;
    properties->granularity = 1;
    return DIENUM_CONTINUE;
}

/* an XInput axis value (-32768..32767) in the program's range, dead zone and saturation, as
 * joystick_hid.c's scale_axis_value does for a HID axis */
static LONG scale_axis( LONG value, const struct object_properties *properties )
{
    LONG log_min = -32768, log_max = 32767, phy_min = properties->range_min, phy_max = properties->range_max, phy_ctr;

    if (phy_min == 0) phy_ctr = phy_max >> 1;
    else phy_ctr = round( (phy_min + phy_max) / 2.0 );

    if (value <= 0)
    {
        log_max = MulDiv( log_min, properties->deadzone, 10000 );
        log_min = MulDiv( log_min, properties->saturation, 10000 );
        phy_max = phy_ctr;
    }
    else
    {
        log_min = MulDiv( log_max, properties->deadzone, 10000 );
        log_max = MulDiv( log_max, properties->saturation, 10000 );
        phy_min = phy_ctr;
    }

    if (value <= log_min) return phy_min;
    if (value >= log_max) return phy_max;
    return phy_min + MulDiv( value - log_min, phy_max - phy_min, log_max - log_min );
}

static DWORD pad_pov( WORD buttons )
{
    BOOL up = buttons & XINPUT_GAMEPAD_DPAD_UP, down = buttons & XINPUT_GAMEPAD_DPAD_DOWN;
    BOOL left = buttons & XINPUT_GAMEPAD_DPAD_LEFT, right = buttons & XINPUT_GAMEPAD_DPAD_RIGHT;

    if (up && right) return 4500;
    if (down && right) return 13500;
    if (down && left) return 22500;
    if (up && left) return 31500;
    if (up) return 0;
    if (right) return 9000;
    if (down) return 18000;
    if (left) return 27000;
    return -1;
}

static void pad_update( IDirectInputDevice8W *iface, const XINPUT_STATE *state )
{
    struct pad_joystick *impl = impl_from_IDirectInputDevice8W( iface );
    const XINPUT_GAMEPAD *pad = &state->Gamepad;
    /* DirectInput's y grows downwards; the triggers share Z, as Windows' Xbox 360 driver does */
    LONG raw[PAD_AXES] =
    {
        pad->sThumbLX, -1 - pad->sThumbLY, (pad->bLeftTrigger - pad->bRightTrigger) * 128,
        pad->sThumbRX, -1 - pad->sThumbRY,
    };
    DWORD time = GetCurrentTime(), seq, pov;
    BOOL notify = FALSE;
    UINT i, index = 0;

    EnterCriticalSection( &impl->base.crit );
    seq = impl->base.dinput->evsequence++;
    for (i = 0; i < PAD_AXES; i++, index++)
    {
        LONG *value = (LONG *)(impl->base.device_state + pad_axes[i].offset);
        LONG scaled = scale_axis( raw[i], impl->base.object_properties + index );

        if (*value == scaled) continue;
        *value = scaled;
        queue_event( iface, index, scaled, time, seq );
        notify = TRUE;
    }
    pov = pad_pov( pad->wButtons );
    if (*(DWORD *)(impl->base.device_state + DIJOFS_POV( 0 )) != pov)
    {
        *(DWORD *)(impl->base.device_state + DIJOFS_POV( 0 )) = pov;
        queue_event( iface, index, pov, time, seq );
        notify = TRUE;
    }
    index++;
    for (i = 0; i < PAD_BUTTONS; i++, index++)
    {
        BYTE *value = impl->base.device_state + DIJOFS_BUTTON( i );
        BYTE pressed = (pad->wButtons & pad_buttons[i]) ? 0x80 : 0;

        if (*value == pressed) continue;
        *value = pressed;
        queue_event( iface, index, pressed, time, seq );
        notify = TRUE;
    }
    LeaveCriticalSection( &impl->base.crit );

    if (notify && impl->base.hEvent) SetEvent( impl->base.hEvent );
}

/* on dinput's input thread when the poll timer fires, and on Poll() */
static HRESULT pad_read( IDirectInputDevice8W *iface )
{
    struct pad_joystick *impl = impl_from_IDirectInputDevice8W( iface );
    XINPUT_STATE state;

    if (!pad_state( &state )) return DIERR_INPUTLOST;
    if (impl->have_packet && state.dwPacketNumber == impl->packet) return DI_OK;
    impl->packet = state.dwPacketNumber;
    impl->have_packet = TRUE;
    pad_update( iface, &state );
    return DI_OK;
}

static HRESULT pad_acquire( IDirectInputDevice8W *iface )
{
    struct pad_joystick *impl = impl_from_IDirectInputDevice8W( iface );
    LARGE_INTEGER due = {.QuadPart = -PAD_POLL_MS * 10000};

    impl->have_packet = FALSE;
    if (!SetWaitableTimer( impl->base.read_event, &due, PAD_POLL_MS, NULL, NULL, FALSE ))
    {
        ERR( "poll timer failed, error %lu\n", GetLastError() );
        return DIERR_GENERIC;
    }
    return pad_read( iface );
}

static HRESULT pad_unacquire( IDirectInputDevice8W *iface )
{
    struct pad_joystick *impl = impl_from_IDirectInputDevice8W( iface );

    CancelWaitableTimer( impl->base.read_event );
    return DI_OK;
}

static void pad_destroy( IDirectInputDevice8W *iface )
{
    struct pad_joystick *impl = impl_from_IDirectInputDevice8W( iface );

    CloseHandle( impl->base.read_event );
}

/* the present HID interface whose path names the pad (045e:028e) and winexinput's "&IG_" child */
static HRESULT pad_hid_path( WCHAR *path, DWORD length, GUID *class_guid )
{
    GUID hid = {0x4d1e55b2, 0xf16f, 0x11cf, {0x88, 0xcb, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30}};  /* GUID_DEVINTERFACE_HID */
    WCHAR *paths, *entry, *lower;
    HRESULT hr = DIERR_UNSUPPORTED;
    ULONG size = 0;

    if (CM_Get_Device_Interface_List_SizeW( &size, &hid, NULL, CM_GET_DEVICE_INTERFACE_LIST_PRESENT ) || !size)
        return DIERR_UNSUPPORTED;
    if (!(paths = malloc( size * sizeof(WCHAR) ))) return DIERR_OUTOFMEMORY;
    if (!CM_Get_Device_Interface_ListW( &hid, NULL, paths, size, CM_GET_DEVICE_INTERFACE_LIST_PRESENT ))
    {
        for (entry = paths; *entry && hr != DI_OK; entry += wcslen( entry ) + 1)
        {
            if (!(lower = wcsdup( entry ))) break;
            _wcslwr( lower );
            /* W211: or the generic HID gamepad of the C:\\orbis\\padhid-generic.txt experiment */
            if ((((wcsstr( lower, L"vid_045e&pid_028e" ) || wcsstr( lower, L"vid_045e&pid_02ea" )) && wcsstr( lower, L"&ig_" )) ||
                 wcsstr( lower, L"vid_1209&pid_5057" )) && wcslen( lower ) < length)
            {
                wcscpy( path, lower );
                *class_guid = GUID_DEVCLASS_HIDCLASS;
                hr = DI_OK;
            }
            free( lower );
        }
    }
    free( paths );
    if (hr != DI_OK) TRACE( "no HID path for the pad\n" );
    return hr;
}

static HRESULT pad_get_property( IDirectInputDevice8W *iface, DWORD property,
                                 DIPROPHEADER *header, const DIDEVICEOBJECTINSTANCEW *instance )
{
    struct pad_joystick *impl = impl_from_IDirectInputDevice8W( iface );

    switch (property)
    {
    case (DWORD_PTR)DIPROP_PRODUCTNAME:
    {
        DIPROPSTRING *value = (DIPROPSTRING *)header;
        lstrcpynW( value->wsz, impl->base.instance.tszProductName, MAX_PATH );
        return DI_OK;
    }
    case (DWORD_PTR)DIPROP_INSTANCENAME:
    {
        DIPROPSTRING *value = (DIPROPSTRING *)header;
        lstrcpynW( value->wsz, impl->base.instance.tszInstanceName, MAX_PATH );
        return DI_OK;
    }
    case (DWORD_PTR)DIPROP_VIDPID:
    {
        DIPROPDWORD *value = (DIPROPDWORD *)header;
        value->dwData = MAKELONG( PAD_VENDOR, PAD_PRODUCT );
        return DI_OK;
    }
    case (DWORD_PTR)DIPROP_JOYSTICKID:
    {
        DIPROPDWORD *value = (DIPROPDWORD *)header;
        value->dwData = 0;
        return DI_OK;
    }
    case (DWORD_PTR)DIPROP_GUIDANDPATH:
    {
        /* HID stack (tools/build-hidstack-hw.py): the path of winexinput's "&IG_" HID device for
         * the pad, which joy.cpl lists under XInput devices; without that stack there is none */
        DIPROPGUIDANDPATH *value = (DIPROPGUIDANDPATH *)header;
        return pad_hid_path( value->wszPath, MAX_PATH, &value->guidClass );
    }
    }

    /* no force feedback (DIPROP_FFLOAD) */
    return DIERR_UNSUPPORTED;
}

static const struct dinput_device_vtbl pad_vtbl =
{
    pad_destroy,
    pad_read,
    pad_read,
    pad_acquire,
    pad_unacquire,
    pad_enum_objects,
    pad_get_property,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
};

HRESULT pad_joystick_create_device( struct dinput *dinput, const GUID *guid, IDirectInputDevice8W **out )
{
    static const DIPROPHEADER filter =
    {
        .dwSize = sizeof(filter),
        .dwHeaderSize = sizeof(filter),
        .dwHow = DIPH_DEVICE,
    };
    DIDEVICEINSTANCEW instance = {.dwSize = sizeof(instance)};
    struct pad_joystick *impl;
    HRESULT hr;

    TRACE( "dinput %p, guid %s, out %p\n", dinput, debugstr_guid( guid ), out );

    *out = NULL;
    if (FAILED(hr = pad_joystick_enum_device( 0, 0, &instance, dinput->dwVersion ))) return hr;
    if (!IsEqualGUID( guid, &instance.guidInstance ) && !IsEqualGUID( guid, &instance.guidProduct ))
        return DIERR_DEVICENOTREG;

    if (!(impl = calloc( 1, sizeof(*impl) ))) return E_OUTOFMEMORY;
    dinput_device_init( &impl->base, &pad_vtbl, guid, dinput );
    impl->base.crit.DebugInfo->Spare[0] = (DWORD_PTR)(__FILE__ ": struct pad_joystick*->base.crit");
    impl->base.instance = instance;
    impl->base.caps.dwDevType = instance.dwDevType;
    impl->base.caps.dwFirmwareRevision = 100;
    impl->base.caps.dwHardwareRevision = 100;
    impl->base.dwCoopLevel = DISCL_NONEXCLUSIVE | DISCL_BACKGROUND;

    if (!(impl->base.read_event = CreateWaitableTimerW( NULL, FALSE, NULL )))
    {
        hr = HRESULT_FROM_WIN32( GetLastError() );
        goto failed;
    }
    if (FAILED(hr = dinput_device_init_device_format( &impl->base.IDirectInputDevice8W_iface ))) goto failed;
    pad_enum_objects( &impl->base.IDirectInputDevice8W_iface, &filter, DIDFT_AXIS | DIDFT_POV, init_object_properties, NULL );

    *out = &impl->base.IDirectInputDevice8W_iface;
    return DI_OK;

failed:
    IDirectInputDevice_Release( &impl->base.IDirectInputDevice8W_iface );
    return hr;
}
''')

revise('''#include "device_private.h"
''','''#include "device_private.h"

/* OrbisDesk (W179): the console's pad as a gamepad, from XInput (joystick_pad.c) */
extern HRESULT pad_joystick_enum_device( DWORD type, DWORD flags, DIDEVICEINSTANCEW *instance, DWORD version );
extern HRESULT pad_joystick_create_device( struct dinput *dinput, const GUID *guid, IDirectInputDevice8W **out );
''','The pad device\'s entry points.')
revise('''    else
    {
        hr = hid_joystick_create_device( impl, guid, &device );''','''    else if (pad_joystick_create_device( impl, guid, &device ) == DI_OK)
        hr = DI_OK;
    else
    {
        hr = hid_joystick_create_device( impl, guid, &device );''','CreateDevice: the pad by its instance or product GUID.')
revise('''    if (device_class == DI8DEVCLASS_ALL || device_class == DI8DEVCLASS_GAMECTRL)
    {
        hr = hid_joystick_refresh_devices();''','''    if (device_class == DI8DEVCLASS_ALL || device_class == DI8DEVCLASS_GAMECTRL)
    {
        hr = pad_joystick_enum_device( type, flags, &instance, impl->dwVersion );
        if (hr == DI_OK && try_enum_device( device_type, callback, &instance, context, flags ) == DIENUM_STOP)
            return DI_OK;

        hr = hid_joystick_refresh_devices();''','EnumDevices: the pad first among the game controllers.')
# HID stack (tools/build-hidstack-hw.py): winebus also shows the pad as an HID gamepad. joystick_pad.c
# already lists it, so joystick_hid.c skips winexinput's "&IG_" HID device for 045e:028e (a PS4 has
# no other way to attach such a controller). W202: only "&IG_"; the "&XI_" one is not in the HID
# enumeration and Windows.Gaming.Input opens it by path through dinput.
hid_source=overlay/'joystick_hid.c';hid_text=hid_source.read_text()
hid_old='''    if (!HidD_GetAttributes( device_file, attrs )) goto failed;
'''
if hid_text.count(hid_old)!=1:raise SystemExit('Unexpected context in joystick_hid.c')
hid_source.write_text(hid_text.replace(hid_old,hid_old+'''    /* OrbisDesk (HID stack): the console's pad is joystick_pad.c's device already */
    if ((attrs->VendorID == 0x045e && (attrs->ProductID == 0x028e || attrs->ProductID == 0x02ea) &&
         (wcsstr( path, L"&IG_" ) || wcsstr( path, L"&ig_" ))) ||
        (attrs->VendorID == 0x1209 && attrs->ProductID == 0x5057) ||  /* W211: generic HID experiment */
        (attrs->VendorID == 0x054c && attrs->ProductID == 0x0ce6))  /* W236: the overlay's DualSense; DirectInput keeps joystick_pad.c */
        goto failed;
'''))
revisions.append('joystick_hid.c: skip the pad\'s HID gamepad from winebus, listed by joystick_pad.c.')

# the pinned build's commands: dinput.c changed, and joystick_pad.c compiled like joystick_hid.c
targets=['dlls/%s/%s-windows/%s.dll'%(m,a,m) for m in MODULES for a in ARCHES]
dry=subprocess.run(['make','-n','-W','../../source/dlls/dinput/dinput.c','-W','../../source/dlls/dinput/joystick_hid.c',*targets],
                   cwd=BUILD,capture_output=True,text=True,check=True).stdout.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'dlls/dinput' not in line or line.startswith('make'):continue
    for name in ('dinput.c','joystick_hid.c'):
        line=line.replace('../../source/dlls/dinput/'+name,str(overlay/name))
    # only what is compiled here moves to build/: the other objects are the pinned build's own
    for m in MODULES:
        for a in ARCHES:
            for name in ('dinput.o','joystick_hid.o','%s.dll'%m):
                line=line.replace('dlls/%s/%s-windows/%s'%(m,a,name),str(work/m/a/name))
    if 'joystick_hid.c' in line and ' -c ' in line:
        commands.append(line)
        commands.append(line.replace(str(overlay/'joystick_hid.c'),str(overlay/'joystick_pad.c')).replace('/joystick_hid.o','/joystick_pad.o'))
        continue
    if 'winegcc' in line:
        line=line.replace('/joystick_hid.o ','/joystick_hid.o '+line.split('/joystick_hid.o ')[0].split()[-1]+'/joystick_pad.o ',1)
    commands.append(line)
links=[c for c in commands if 'winegcc' in c]
if len(links)!=len(targets) or not all('joystick_pad.o' in c for c in links) or sum('joystick_pad.c' in c for c in commands)!=len(targets):
    raise SystemExit('make -n did not give the dinput commands as expected:\n'+dry[-3000:])
for m in MODULES:
    for a in ARCHES:(work/m/a).mkdir(parents=True,exist_ok=True)
warnings=[]
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    warnings+=[l for l in (run.stdout+run.stderr).splitlines() if 'warning' in l]
modules={}
for a in ARCHES:
    (out/(a+'-windows')).mkdir(parents=True)
    for m in MODULES:
        target=out/(a+'-windows')/(m+'.dll');shutil.copyfile(work/m/a/(m+'.dll'),target)
        modules['%s/%s.dll'%(a,m)]={'path':'%s-windows/%s.dll'%(a,m),'sha256':sha(target)}
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(__file__),'modules':modules,
          'revisions':revisions,'new_sources':['joystick_pad.c'],'compile_warnings':warnings,'commands':commands}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'modules':len(modules),'revisions':len(revisions),'warnings':len(warnings)}))
