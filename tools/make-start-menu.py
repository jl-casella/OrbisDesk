#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Write the hardware Start menu: folders of shortcuts (.lnk) to Wine's programs.

W045. Each shortcut is a Shell Link ([MS-SHLLINK]) with a LinkInfo local base path, a
description and an icon location (the program itself, icon 0); Wine's shell32 loads
those fields, and explorer's Start menu shows the folders and the programs' icons.
Output: out/start-menu/<folders>/<name>.lnk, copied by build-wine-hardware.py to
C:\\ProgramData\\Microsoft\\Windows\\Start Menu.
"""
import hashlib,json,pathlib,shutil,struct
ROOT=pathlib.Path(__file__).resolve().parents[1]
out=ROOT/'out/start-menu'
SYS='C:\\windows\\system32\\'
MENU={
    'Programs/Accessories':[('Notepad','notepad.exe','Text editor'),('Command Prompt','cmd.exe','Command line'),
                            ('File Manager','wfm.exe','Browse drives and folders (WFM)')],
    'Programs/Games':[('Minesweeper','winemine.exe','Find the mines'),
                      # W114: tools/build-games.py (ReactOS), icon from each exe
                      ('Solitaire','sol.exe','Klondike solitaire'),('Spider Solitaire','spider.exe','Spider solitaire')],
    'System Tools':[('Command Prompt','cmd.exe','Command line'),('File Manager','wfm.exe','Browse drives and folders (WFM)'),
                    ('Registry Editor','regedit.exe','Edit the registry'),('Task Manager','taskmgr.exe','Running programs and performance'),
                    # W172: phase 7, Wine Configuration was here; W179 moved it to the Start menu's Control
                    # Panel as an applet (fixtures/win32/winecfgcpl.c, built by build-wine-hardware.py).
                    # W178: phase 7, the controller as XInput sees it (an item's fourth field is its
                    # arguments). W179: its fifth is the icon location, joy.cpl's own icon.
                    ('Game Controllers','control.exe','Test the controller (XInput)','joy.cpl',SYS+'joy.cpl')],
}
# W090: the GPU test programs in C:\orbis, each with its icon from tools/make-icons.py (copied
# to C:\orbis\icons by build-wine-hardware.py), and the MangoHud configuration in Notepad.
# Items: name, full target path, description, arguments, icon.
ORBIS='C:\\orbis\\'
GRAPHICS=[('glxgears',ORBIS+'glxgears.exe','OpenGL gears through Zink and Vulkan','',ORBIS+'icons\\glxgears.ico'),
          ('vkcube',ORBIS+'vkcube.exe','Vulkan cube (Vulkan-Tools)','',ORBIS+'icons\\vkcube.ico'),
          ('vkspin',ORBIS+'vkspin64.exe','Vulkan spinning triangle','',ORBIS+'icons\\vkspin64.ico'),
          ('MangoHud Config',SYS+'notepad.exe','Edit the MangoHud overlay settings',
           # W092: %APPDATA% follows the registry's shell folders, C:\users\orbis since alpha-1 (build-wine-hardware.py)
           'C:\\users\\orbis\\AppData\\Roaming\\MangoHud\\MangoHud.conf',ORBIS+'icons\\mangohud.ico')]
# W177 (phase 9): Programs/Internet. SeaMonkey 2.53 is the browser (the user's choice; it replaced
# Pale Moon, W177-W215, whose shortcuts build-wine-hardware.py deletes on the console). It is not in
# the package: the shortcut expects the user's own copy in C:\Program Files\SeaMonkey and passes a
# profile of ours (fixtures/browser, staged by build-wine-hardware.py); -no-remote, so it does not
# look for another instance's window.
SEAMONKEY='C:\\Program Files\\SeaMonkey\\seamonkey.exe'
SEAMONKEY_PROFILE='C:\\users\\orbis\\AppData\\Roaming\\Mozilla\\SeaMonkey\\Profiles\\orbis'
# W179: each with an icon of tools/make-icons.py (the user's copy may not be there yet, and the test
# programs have no icon resource).
INTERNET=[('SeaMonkey',SEAMONKEY,'Web browser (your own copy of SeaMonkey 2.53)',
           '-no-remote -profile "'+SEAMONKEY_PROFILE+'"',ORBIS+'icons\\web.ico'),
          # W179: no Internet Explorer shortcut. iexplore registers its class as a local COM server,
          # which needs marshaling and rpcss, neither of which a single-process title has (W177).
          ('WebView test (64-bit)',ORBIS+'webview64.exe','IE control embedded in a program, 64-bit','',ORBIS+'icons\\webview.ico'),
          ('WebView test (32-bit)',ORBIS+'webview32.exe','IE control embedded in a program, 32-bit','',ORBIS+'icons\\webview.ico')]
# DVD (dvd-plan.md): Programs/Multimedia, VLC 3.0.24 x64 (tools/stage-vlc.py, copied by
# build-wine-hardware.py to C:\Program Files\VLC). The DVD is drive L: in ROOT (/mnt/disc,
# pw_wine_fs.c). Video through Direct3D 9 (DXVK, as the games), or GDI as the fallback; audio through
# DirectSound; no DXVA2 (--avcodec-hw=none), no first-run privacy or update questions. VLC has no
# plugins.dat in its archive: "VLC plugin cache" makes it on the console (optional since W243, when
# stage-vlc.py keeps only about 100 plugins; it makes VLC start faster). W252: VLC logs errors and
# warnings to C:\orbis\vlc-log.txt (W250's --verbose=2 made playback slow, see VLC_OPTIONS).
VLC_DIR='C:\\Program Files\\VLC\\'
VLC=VLC_DIR+'vlc.exe'
# W243: the DVD as a folder (dvd:///L:/VIDEO_TS/), not as a drive. W241/W242: "unable to open MRL
# dvd:///L:/". On Windows libdvdread first opens the path itself as a disc image, and libdvdcss opens
# a bare drive (L: or L:\) as the device \\.\L:, which Wine opens as the root folder; that reader is
# kept and its UDF reads fail. A folder path cannot be opened as a file, so libdvdread reads the
# VIDEO_TS files instead (DVDOpenPath). No raw device: /dev/cd0 is EACCES at the app's uid (J002).
DVD_MRL='dvd:///L:/VIDEO_TS/'
# W245 (W243: first pictures late by up to 154 ms, "pts_delay increased to 300 ms"): one second of
# disc buffering instead of VLC's 300 ms, for the DVD shortcuts only
DVD_OPTIONS=' --disc-caching=1000'
# W246: the DVD in full screen, and VLC closes when the disc stops playing (its end, a stop, or
# the disc ejected: the read errors end the input) instead of staying on an error
DVD_OPTIONS+=' --fullscreen --play-and-exit'
VLC_OPTIONS=('--no-qt-privacy-ask --no-qt-updates-notif --avcodec-hw=none --aout=directsound '
             # W252 (W251 run-0005.log: playback under 10 fps): with --verbose=2 (W250) VLC also sent every
             # debug line through OutputDebugString, a DBG_PRINTEXCEPTION each, which the title traces
             # (+seh: ten lines and the handlers per message, about 2580 between 38918 and 101074, on the
             # playback threads). Back to the file log, errors and warnings only (--log-verbose=1), and
             # VLC's own verbosity left at its default, as in W243-W248 where the DVD played smoothly.
             # The file log is lost if VLC aborts (fully buffered on Windows, W248)
             '--file-logging --logfile=C:\\orbis\\vlc-log.txt --log-verbose=1 '
             # W245 (W243 vlc-log.txt: "allowing 1 thread(s) for decoding", VLC counts the CPUs of the
             # process affinity): MPEG-2 decoding in 4 threads
             '--avcodec-threads=4 '
             # W246: the pad profile (fixtures/padmaps/vlc.exe.ini) sends single keys; VLC's disc menu
             # and chapter keys are Shift combinations (Shift+m, Shift+p, Shift+n), so they get keys of
             # their own that VLC leaves free
             '--key-disc-menu=Home --key-chapter-prev=Insert --key-chapter-next=End')
MULTIMEDIA=[('DVD Player',VLC,'Play the DVD in drive L: (VLC, Direct3D 9 video)',
             # W250 (W248 run-0004.log: 'Failed to load module L"D3D9.DLL"; status=c0000017', no free
             # address range for DXVK's d3d9.dll after other programs in the same session): if Direct3D 9
             # cannot start, GDI. With Direct3D 9 alone, VLC made its video window again and again, and Qt
             # went in and out of full screen 28 times (PWSINK fullscreen on/off) until VLC ended
             VLC_OPTIONS+DVD_OPTIONS+' --vout=direct3d9,wingdi '+DVD_MRL,VLC),
            ('DVD Player (GDI video)',VLC,'Play the DVD in drive L: (VLC, GDI video)',
             VLC_OPTIONS+DVD_OPTIONS+' --vout=wingdi '+DVD_MRL,VLC),
            ('VLC media player',VLC,'Play video and music files (VLC)',VLC_OPTIONS+' --vout=direct3d9,wingdi',VLC),
            ('VLC plugin cache',VLC_DIR+'vlc-cache-gen.exe','Optional, once after each update: VLC then starts faster',
             '"'+VLC_DIR+'plugins"',VLC)]
# W114: 3D Pinball only when tools/build-games.py --pinball staged it (game data not included).
games=ROOT/'out/games/manifest.json'
if games.is_file() and 'SpaceCadetPinball.exe' in json.loads(games.read_text())['system32']:
    MENU['Programs/Games'].append(('3D Pinball','SpaceCadetPinball.exe','Space Cadet pinball (needs PINBALL.DAT)'))
LINK_CLSID=bytes.fromhex('0114020000000000c000000000000046')  # {00021401-0000-0000-C000-000000000046}
HAS_LINK_INFO,HAS_NAME,HAS_WORKING_DIR,HAS_ARGUMENTS,HAS_ICON_LOCATION,IS_UNICODE=0x2,0x4,0x10,0x20,0x40,0x80
def string(text):return struct.pack('<H',len(text))+text.encode('utf-16-le')
def link_info(path):
    """LinkInfo with VolumeIDAndLocalBasePath: a fixed-disk volume and the ANSI target path."""
    volume=struct.pack('<IIII',17,3,0,16)+b'\0'           # size, DRIVE_FIXED, serial, label offset, empty label
    base=path.encode('ascii')+b'\0';suffix=b'\0'
    header=0x1c;volume_at=header;base_at=volume_at+len(volume);suffix_at=base_at+len(base)
    size=suffix_at+len(suffix)
    return struct.pack('<IIIIIII',size,header,1,volume_at,base_at,0,suffix_at)+volume+base+suffix
def shortcut(target,description,arguments='',icon=None,directory=SYS):
    """StringData in [MS-SHLLINK] order: name, working directory, arguments, icon location"""
    flags=HAS_LINK_INFO|HAS_NAME|HAS_WORKING_DIR|HAS_ICON_LOCATION|IS_UNICODE|(HAS_ARGUMENTS if arguments else 0)
    header=struct.pack('<I16sII',0x4c,LINK_CLSID,flags,0x20)+bytes(24)+struct.pack('<IiIHHII',0,0,1,0,0,0,0)
    assert len(header)==0x4c
    return (header+link_info(target)+string(description)+string(directory.rstrip('\\'))+
            (string(arguments) if arguments else b'')+string(icon or target)+
            b'\0\0\0\0')  # terminal extra-data block
if out.exists():shutil.rmtree(out)
entries={}
for folder,items in MENU.items():
    for name,program,description,*extra in items:
        target=out/folder/(name+'.lnk');target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(shortcut(SYS+program,description,extra[0] if extra else '',extra[1] if len(extra)>1 else None))
        entries[folder+'/'+name+'.lnk']={'target':SYS+program,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
for name,program,description,arguments,icon in GRAPHICS:
    target=out/'Graphics Tools'/(name+'.lnk');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(shortcut(program,description,arguments,icon,program.rsplit('\\',1)[0]+'\\'))
    entries['Graphics Tools/'+name+'.lnk']={'target':program,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
for name,program,description,arguments,icon in INTERNET:
    target=out/'Programs/Internet'/(name+'.lnk');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(shortcut(program,description,arguments,icon,program.rsplit('\\',1)[0]+'\\'))
    entries['Programs/Internet/'+name+'.lnk']={'target':program,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
for name,program,description,arguments,icon in MULTIMEDIA:
    target=out/'Programs/Multimedia'/(name+'.lnk');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(shortcut(program,description,arguments,icon,program.rsplit('\\',1)[0]+'\\'))
    entries['Programs/Multimedia/'+name+'.lnk']={'target':program,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(out/'manifest.json').write_text(json.dumps({'schema_version':1,'generator':'tools/make-start-menu.py','shortcuts':entries},indent=2)+'\n')
print(json.dumps({'shortcuts':len(entries)}))
