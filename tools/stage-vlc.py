#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""DVD: VLC 3.0.24 for Windows x64, the DVD player (the user's choice, dvd-plan.md).

The portable archive from VideoLAN (https://download.videolan.org/pub/videolan/vlc/3.0.24/win64/,
GPLv2 and LGPLv2.1), pinned by SHA-256. It brings its own DVD navigation (libdvdnav/libdvdread with
libdvdcss), MPEG-2 and AC3 decoding (libavcodec) and its Qt interface, so it needs neither
DirectShow nor GStreamer. tools/build-wine-hardware.py copies the tree to C:\\Program Files\\VLC;
tools/make-start-menu.py makes its shortcuts (Programs/Multimedia).

Plugins (PLUGINS, W243): only those named, about 100 of 400: DVD (dvdnav, dvdread, ps, MPEG-2
and AC3 through avcodec, DVD subtitles), the usual local files (mp4, mkv, avi, ogg, wav, ts),
the Qt interface, Direct3D 9 and GDI video, DirectSound, MMDevice and waveOut audio, logging.
W241: without plugins/plugins.dat (the archive has none; the installer makes it) VLC loads every
plugin at each start and keeps it loaded, one open file each; with 290 plugins the title ran out
of descriptors (c000011f, STATUS_TOO_MANY_OPENED_FILES, after about 180) and then mmdevapi's
version.dll failed, so DirectSound had no device (dsound get_mmdevenum 80070005). A plugin a file
needs and that is not here shows in VLC's log as a missing module; it is added to PLUGINS.
Also left out (EXCLUDE): the skins, Lua, the ActiveX control, the SDK and the installer's files,
and the translations other than Spanish. The shortcut "VLC plugin cache" (vlc-cache-gen.exe) is
optional: it only makes VLC start faster.

The archive is untrusted input: its listing is checked first (relative paths under vlc-3.0.24/,
no '..', regular files and folders only), 7z extracts it into a new empty folder, and the files
found must be the listed ones. Run with python3 -I.
Output: out/vlc/VLC/... and out/vlc/manifest.json (each file's sha256)."""
import hashlib,json,pathlib,shutil,struct,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
VERSION='3.0.24'
ARCHIVE='.deps/downloads/vlc-3.0.24-win64/vlc-3.0.24-win64.7z'
ARCHIVE_SHA256='1ed59c09152e78aff84663fa76efab26057716576db74332858810e5ef54ae1f'
TOP='vlc-'+VERSION
# folders (with all below) and single files, relative to the VLC folder
EXCLUDE_DIRS=('sdk','msi','lua','skins','languages')
EXCLUDE_FILES=('axvlc.dll','npvlc.dll')
KEEP_LOCALE='es'
# the plugins copied, by folder: plugins/<folder>/lib<name>_plugin.dll; every one must exist
PLUGINS={
    'access':('dvdnav','dvdread','filesystem','idummy'),
    # W245: equalizer, whose options the Qt interface reads ("option equalizer-* does not exist", W243)
    'audio_filter':('audio_format','equalizer','remap','scaletempo','simple_channel_mixer','trivial_channel_mixer',
                    'speex_resampler','ugly_resampler'),
    'audio_mixer':('float_mixer','integer_mixer'),
    'audio_output':('adummy','directsound','mmdevice','wasapi','waveout'),
    'codec':('avcodec','araw','lpcm','mpg123','spudec','cc','subsdec','subsusf','substx3g','rawvideo',
             'ddummy','edummy','flac','vorbis','opus'),
    'control':('hotkeys',),
    'd3d9':('direct3d9_filters',),
    'demux':('ps','es','mpgv','h26x','mp4','mkv','avi','asf','ogg','wav','flacsys','ts','playlist',
             'directory_demux','subtitle','vobsub'),
    'gui':('qt',),
    'logger':('console_logger','file_logger'),
    'misc':('logger',),
    'packetizer':('packetizer_a52','packetizer_copy','packetizer_dts','packetizer_flac','packetizer_h264',
                  'packetizer_hevc','packetizer_mlp','packetizer_mpeg4audio','packetizer_mpeg4video',
                  'packetizer_mpegaudio','packetizer_mpegvideo','packetizer_vc1'),
    'stream_filter':('cache_block','cache_read','prefetch','skiptags'),
    'text_renderer':('freetype','tdummy'),
    'video_chroma':('chain','grey_yuv','i420_10_p010','i420_nv12','i420_rgb','i420_rgb_mmx','i420_rgb_sse2',
                    'i420_yuy2','i420_yuy2_mmx','i420_yuy2_sse2','i422_i420','i422_yuy2','i422_yuy2_mmx',
                    'i422_yuy2_sse2','rv32','swscale','yuvp','yuy2_i420','yuy2_i422'),
    'video_filter':('deinterlace','blend','scale','adjust'),
    'video_output':('direct3d9','wingdi','vdummy','drawable'),
}
PLUGIN_FILES={'plugins/%s/lib%s_plugin.dll'%(folder,name) for folder,names in PLUGINS.items() for name in names}
# what the DVD player needs; a missing one stops the stager
REQUIRED=('vlc.exe','libvlc.dll','libvlccore.dll','vlc-cache-gen.exe',
          'plugins/access/libdvdnav_plugin.dll','plugins/access/libdvdread_plugin.dll',
          'plugins/access/libfilesystem_plugin.dll','plugins/codec/libavcodec_plugin.dll',
          'plugins/demux/libps_plugin.dll','plugins/gui/libqt_plugin.dll',
          'plugins/video_output/libdirect3d9_plugin.dll','plugins/video_output/libwingdi_plugin.dll',
          'plugins/audio_output/libdirectsound_plugin.dll')
out=ROOT/'out/vlc';work=ROOT/'build/vlc-extract'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
archive=ROOT/ARCHIVE
if sha(archive)!=ARCHIVE_SHA256:raise SystemExit('VLC archive differs from the pinned release: '+ARCHIVE)

# the listing: after the "----------" line, one block per entry, "Path = ..." and "Attributes =
# D_ drwxr-xr-x" (Windows attributes, D for a folder, then the Unix mode, l for a link)
listing=subprocess.run(['7z','l','-slt',str(archive)],capture_output=True,text=True,check=True).stdout
if '\n----------\n' not in listing:raise SystemExit('VLC archive: unexpected 7z listing')
entries=[];current={}
for line in listing.split('\n----------\n',1)[1].splitlines()+['']:
    if not line.strip():
        if current:entries.append(current);current={}
        continue
    key,_,value=line.partition(' = ');current[key]=value
listed_files=set()
for entry in entries:
    path=pathlib.PurePosixPath(entry['Path'].replace('\\','/'))
    if path.is_absolute() or '..' in path.parts or path.parts[0]!=TOP:raise SystemExit('Unexpected archive entry: '+entry['Path'])
    windows,_,unix=entry.get('Attributes','').partition(' ')
    if unix.startswith('l') or entry.get('Symbolic Link'):raise SystemExit('Link in the archive: '+entry['Path'])
    if 'D' in windows:continue
    listed_files.add(str(path))
if not listed_files:raise SystemExit('VLC archive: empty listing')

if work.exists():shutil.rmtree(work)
work.mkdir(parents=True)
subprocess.run(['7z','x','-y','-bd','-o'+str(work),str(archive)],stdout=subprocess.DEVNULL,check=True)
found={str(p.relative_to(work)) for p in work.rglob('*') if p.is_file() or p.is_symlink()}
if any(p.is_symlink() for p in work.rglob('*')):raise SystemExit('VLC archive: a link was extracted')
if found!=listed_files:
    raise SystemExit('VLC archive: extracted files differ from the listing: %s'%sorted(found^listed_files)[:10])

def excluded(relative):
    if relative in EXCLUDE_FILES:return True
    if any(relative==d or relative.startswith(d+'/') for d in EXCLUDE_DIRS):return True
    parts=relative.split('/')
    if parts[0]=='plugins':return relative not in PLUGIN_FILES
    return parts[0]=='locale' and len(parts)>1 and parts[1]!=KEEP_LOCALE
absent=sorted(p for p in PLUGIN_FILES if TOP+'/'+p not in listed_files)
if absent:raise SystemExit('VLC: plugins named in PLUGINS are not in the archive: '+', '.join(absent))
if out.exists():shutil.rmtree(out)
files={};left_out={'files':0,'bytes':0}
for name in sorted(listed_files):
    source=work/name;relative=name[len(TOP)+1:]
    if excluded(relative):left_out['files']+=1;left_out['bytes']+=source.stat().st_size;continue
    target=out/'VLC'/relative;target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target);files[relative]=sha(target)
missing=[name for name in REQUIRED if name not in files]
if missing:raise SystemExit('VLC: required files missing: '+', '.join(missing))
# vlc.exe must be a PE32+ for x86-64 (the 64-bit view, the best tested one in OrbisDesk)
exe=(out/'VLC/vlc.exe').read_bytes();pe=struct.unpack_from('<I',exe,0x3c)[0]
if exe[:2]!=b'MZ' or exe[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<H',exe,pe+4)[0]!=0x8664:
    raise SystemExit('vlc.exe is not an x86-64 PE')
shutil.rmtree(work)
manifest={'schema_version':1,'version':VERSION,'source':'https://download.videolan.org/pub/videolan/vlc/'+VERSION+'/win64/',
          'archive':ARCHIVE,'archive_sha256':ARCHIVE_SHA256,'license':'GPL-2.0-or-later (VLC), LGPL-2.1-or-later (libVLC)',
          'directory':'VLC','files':files,'bytes':sum((out/'VLC'/p).stat().st_size for p in files),
          'plugins':len(PLUGIN_FILES),'left_out':left_out,
          # the archive's plugins not copied: build-wine-hardware.py deletes them on the console
          # (W241 shipped 290, and VLC loads whatever is in its plugins folder)
          'left_out_plugins':sorted(n[len(TOP)+1:] for n in listed_files
                                    if n.startswith(TOP+'/plugins/') and n[len(TOP)+1:] not in files),
          'builder_sha256':sha(pathlib.Path(__file__))}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'files':len(files),'plugins':len(PLUGIN_FILES),'mib':manifest['bytes']>>20,'left_out_files':left_out['files'],
                  'left_out_mib':left_out['bytes']>>20}))
