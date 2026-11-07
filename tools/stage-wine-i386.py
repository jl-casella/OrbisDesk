#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Stage the i386 (WoW64) Wine DLLs that 32-bit games need beyond the sealed prefix.

W119, phase 2 of the PE32 plan. The DLLs are built as PE32 in the pinned host Wine tree
(make dlls/<name>/i386-windows/<name>.dll). Their import closure is taken from the same
tree; modules the sealed prefix already has in syswow64 are left out. Nothing is patched.
Output: out/wine-i386/i386-windows/*.dll and manifest.json; tools/build-wine-hardware.py
copies them to C:\\windows\\syswow64 and wine/lib/wine/i386-windows.
"""
import hashlib,json,pathlib,re,struct,subprocess,tarfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build';out=ROOT/'out/wine-i386'
(out/'i386-windows').mkdir(parents=True,exist_ok=True);(out/'x86_64-windows').mkdir(parents=True,exist_ok=True)
# SuperMarioKart.exe (Blitz3D) imports ddraw, dinput, d3dxof, dplayx, wsock32; FMOD loads
# dsound at run time; DXVK/wined3d later need dxgi, d3d8/d3d9 and winevulkan/vulkan-1.
TARGETS=('ddraw','wined3d','dinput','d3dxof','dplayx','wsock32','dsound','mmdevapi','dxgi',
         'winevulkan','vulkan-1','opengl32','d3d8','d3d9',
         # W120: in the sealed syswow64 already, but ntdll gives a 32-bit builtin its Unix library
         # only when it loads from wine/lib/wine/i386-windows. From syswow64 alone, ws2_32's
         # initialisation failed (W119: SuperMarioKart.exe ended with c0000142 through wsock32).
         'ws2_32',
         # W176 (phase 8): the same for dnsapi, whose Unix side is now in the ELF (dnsapi.so,
         # platform/ps4/pw_wine_netctl.c). Loaded from syswow64, it had none ("No libresolv
         # support"), and iphlpapi's first DnsQueryConfig called a null Unix handle: W174's
         # nettest32.exe GetAdaptersAddresses ended in c0000005 (read of address 8).
         'dnsapi',
         # W123: advapi32 forwards SystemFunction036 (RtlGenRandom) to cryptbase, missing in the
         # sealed syswow64: sound32.exe and SuperMarioKart.exe ended in "Unimplemented function" (W122).
         'cryptbase',
         # W138: DirectMusic: SuperMarioKart.exe (Blitz3D) plays its MIDI music through
         # CLSID_DirectMusicPerformance (dmime), not registered before (W137). dmsynth, Wine's
         # software synthesizer, is not built in this tree: tools/build-dmsynth-i386.py builds it.
         'dmime','dmusic','dmloader','dmstyle','dmband','dmcompos','dswave','dmscript',
         # W260 (W259: Portal): Portal.exe imports shfolder ("Failed to load module SHFOLDER.dll", c0000135) and
         # hl2.exe's bin\valve_avi.dll imports avifil32 ("Library AVIFIL32.dll ... not found"): the engine gave up.
         'avifil32','shfolder')
# W120: Windows audio (phase 3) also for 64-bit programs: mmdevapi loads the wineps4 driver,
# dsound and msacm32 sit on it. winmm x64 is already staged.
# W260: avifil32 and shfolder for 64-bit programs too (their closure adds msvfw32, absent from system32).
X64_TARGETS=('mmdevapi','dsound','msacm32','avifil32','shfolder')

# W261 (W259/W260: games found Wine's DLLs missing one at a time): every other module of the pinned tree a Windows
# program could import, absent from both views, for each view. Left out, with the reason: W261_LEFT_OUT.
W261_I386=(
    'acledit.dll', 'aclui.dll', 'activeds.dll', 'actxprxy.dll', 'adsldp.dll', 'adsldpc.dll', 'amsi.dll',
    'amstream.dll', 'apphelp.dll', 'atl.dll', 'atl100.dll', 'atl110.dll', 'atl80.dll', 'atl90.dll', 'atlthunk.dll',
    'atmlib.dll', 'authz.dll', 'avrt.dll', 'bcryptprimitives.dll', 'bluetoothapis.dll', 'browseui.dll', 'cards.dll',
    'cdosys.dll', 'chakra.dll', 'cldapi.dll', 'colorcnv.dll', 'comcat.dll', 'comsvcs.dll', 'concrt140.dll',
    'connect.dll', 'credui.dll', 'crtdll.dll', 'cryptdlg.dll', 'cryptdll.dll', 'cryptext.dll', 'cryptnet.dll',
    'cryptxml.dll', 'ctl3d32.dll', 'd2d1.dll', 'd3d10.dll', 'd3d10_1.dll', 'd3d12.dll', 'd3d12core.dll',
    'd3d8thk.dll', 'd3dcompiler_33.dll', 'd3dcompiler_34.dll', 'd3dcompiler_35.dll', 'd3dcompiler_36.dll',
    'd3dcompiler_37.dll', 'd3dcompiler_38.dll', 'd3dcompiler_39.dll', 'd3dcompiler_40.dll', 'd3dcompiler_41.dll',
    'd3dcompiler_42.dll', 'd3dcompiler_43.dll', 'd3dcompiler_46.dll', 'd3dim.dll', 'd3dim700.dll', 'd3drm.dll',
    'd3dx10_33.dll', 'd3dx10_34.dll', 'd3dx10_35.dll', 'd3dx10_36.dll', 'd3dx10_37.dll', 'd3dx10_38.dll',
    'd3dx10_39.dll', 'd3dx10_40.dll', 'd3dx10_41.dll', 'd3dx10_42.dll', 'd3dx10_43.dll', 'd3dx11_42.dll',
    'd3dx11_43.dll', 'davclnt.dll', 'dbgeng.dll', 'dciman32.dll', 'dcomp.dll', 'ddrawex.dll', 'dhcpcsvc6.dll',
    'dhtmled.ocx', 'diasymreader.dll', 'directmanipulation.dll', 'dispex.dll', 'dmusic32.dll', 'dplay.dll',
    'dpnaddr.dll', 'dpnet.dll', 'dpnhupnp.dll', 'dpnlobby.dll', 'dpvoice.dll', 'dpwsockx.dll', 'drmclien.dll',
    'dsdmo.dll', 'dsquery.dll', 'dsrole.dll', 'dssenh.dll', 'dsuiext.dll', 'dx8vb.dll', 'dxcore.dll', 'dxdiagn.dll',
    'dxtrans.dll', 'dxva2.dll', 'esent.dll', 'evr.dll', 'explorerframe.dll', 'faultrep.dll', 'feclient.dll',
    'fntcache.dll', 'fontsub.dll', 'fusion.dll', 'fwpuclnt.dll', 'gameinput.dll', 'gameux.dll', 'glu32.dll',
    'gpkcsp.dll', 'hhctrl.ocx', 'hlink.dll', 'hnetcfg.dll', 'hrtfapo.dll', 'ia2comproxy.dll', 'iccvid.dll',
    'icmp.dll', 'icmui.dll', 'icuin.dll', 'icuuc.dll', 'ieproxy.dll', 'imagehlp.dll', 'inetcomm.dll',
    'inetmib1.dll', 'infosoft.dll', 'initpki.dll', 'inkobj.dll', 'inseng.dll', 'iprop.dll', 'itircl.dll',
    'itss.dll', 'iyuv_32.dll', 'jsproxy.dll', 'ksproxy.ax', 'ksuser.dll', 'ktmw32.dll', 'l3codeca.acm',
    'l3codecx.ax', 'loadperf.dll', 'lz32.dll', 'magnification.dll', 'mapi32.dll', 'mapistub.dll', 'mciavi32.dll',
    'mcicda.dll', 'mciqtz32.dll', 'mciseq.dll', 'mciwave.dll', 'mf.dll', 'mf3216.dll', 'mferror.dll',
    'mfh264enc.dll', 'mfmediaengine.dll', 'mfplat.dll', 'mfplay.dll', 'mfreadwrite.dll', 'mgmtapi.dll',
    'mmcndmgr.dll', 'mp3dmod.dll', 'mprapi.dll', 'msado15.dll', 'msasn1.dll', 'msauddecmft.dll', 'mscat32.dll',
    'msctf.dll', 'msctfmonitor.dll', 'msctfp.dll', 'msdaps.dll', 'msdelta.dll', 'msdrm.dll', 'msftedit.dll',
    'msgsm32.acm', 'msi.dll', 'msident.dll', 'msimsg.dll', 'msimtf.dll', 'msisip.dll', 'msisys.ocx', 'msls31.dll',
    'msmpeg2vdec.dll', 'msnet32.dll', 'mspatcha.dll', 'msrle32.dll', 'msscript.ocx', 'mssign32.dll', 'mssip32.dll',
    'msttsengine.dll', 'msvcirt.dll', 'msvcm80.dll', 'msvcm90.dll', 'msvcp100.dll', 'msvcp110.dll', 'msvcp120.dll',
    'msvcp120_app.dll', 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_atomic_wait.dll',
    'msvcp140_codecvt_ids.dll', 'msvcp60.dll', 'msvcp70.dll', 'msvcp71.dll', 'msvcp80.dll', 'msvcp90.dll',
    'msvcp_win.dll', 'msvcr100.dll', 'msvcr110.dll', 'msvcr120.dll', 'msvcr120_app.dll', 'msvcr70.dll',
    'msvcr71.dll', 'msvcr80.dll', 'msvcr90.dll', 'msvcrt20.dll', 'msvcrt40.dll', 'msvcrtd.dll', 'msvdsp.dll',
    'msvidc32.dll', 'msvproc.dll', 'mswsock.dll', 'msxml.dll', 'msxml2.dll', 'msxml4.dll', 'msxml6.dll',
    'mtxdm.dll', 'nddeapi.dll', 'ndfapi.dll', 'netcfgx.dll', 'netprofm.dll', 'ninput.dll', 'normaliz.dll',
    'npmshtml.dll', 'npptools.dll', 'ntdsapi.dll', 'objsel.dll', 'odbcbcp.dll', 'odbccp32.dll', 'odbccu32.dll',
    'olecli32.dll', 'oledb32.dll', 'oledlg.dll', 'olepro32.dll', 'olesvr32.dll', 'opcservices.dll', 'packager.dll',
    'pdh.dll', 'photometadatahandler.dll', 'pidgen.dll', 'powrprof.dll', 'profapi.dll', 'pstorec.dll',
    'pwrshplugin.dll', 'qasf.dll', 'qdvd.dll', 'qedit.dll', 'query.dll', 'qwave.dll', 'regapi.dll',
    'resampledmo.dll', 'riched20.dll', 'riched32.dll', 'rsabase.dll', 'rsaenh.dll', 'rstrtmgr.dll', 'rtscom.dll',
    'rtutils.dll', 'rtworkq.dll', 'samlib.dll', 'sapi.dll', 'sas.dll', 'scarddlg.dll', 'sccbase.dll',
    'schannel.dll', 'scrobj.dll', 'scrrun.dll', 'security.dll', 'sensapi.dll', 'serialui.dll', 'shdoclc.dll',
    'slbcsp.dll', 'slc.dll', 'snmpapi.dll', 'softpub.dll', 'sppc.dll', 'srvcli.dll', 'sspicli.dll', 'sti.dll',
    'strmdll.dll', 'svrapi.dll', 'sxs.dll', 't2embed.dll', 'tapi32.dll', 'tbs.dll', 'tdh.dll', 'thumbcache.dll',
    'tiptsf.dll', 'traffic.dll', 'twain_32.dll', 'twaindsm.dll', 'tzres.dll', 'uianimation.dll',
    'uiautomationcore.dll', 'uiribbon.dll', 'unicows.dll', 'url.dll', 'utildll.dll', 'vbscript.dll',
    'vccorlib140.dll', 'vcomp.dll', 'vcomp100.dll', 'vcomp110.dll', 'vcomp120.dll', 'vcomp140.dll', 'vcomp90.dll',
    'vcruntime140.dll', 'vga.dll', 'vidreszr.dll', 'wbemdisp.dll', 'wbemprox.dll', 'webservices.dll',
    'websocket.dll', 'wer.dll', 'wevtapi.dll', 'winbio.dll', 'winbrand.dll', 'windowscodecsext.dll', 'winemapi.dll',
    'wing32.dll', 'winhttp.dll', 'winnls32.dll', 'winsqlite3.dll', 'winsta.dll', 'wintab32.dll', 'wintypes.dll',
    'winusb.dll', 'wkscli.dll', 'wlanapi.dll', 'wlanui.dll', 'wldap32.dll', 'wldp.dll', 'wmasf.dll', 'wmi.dll',
    'wminet_utils.dll', 'wmiutils.dll', 'wmp.dll', 'wmphoto.dll', 'wmvcore.dll', 'wmvdecod.dll', 'wnaspi32.dll',
    'wpc.dll', 'wsdapi.dll', 'wshom.ocx', 'wsnmp32.dll', 'x3daudio1_0.dll', 'x3daudio1_1.dll', 'x3daudio1_2.dll',
    'x3daudio1_3.dll', 'x3daudio1_4.dll', 'x3daudio1_5.dll', 'x3daudio1_6.dll', 'x3daudio1_7.dll',
    'xactengine2_0.dll', 'xactengine2_4.dll', 'xactengine2_7.dll', 'xactengine2_9.dll', 'xactengine3_0.dll',
    'xactengine3_1.dll', 'xactengine3_2.dll', 'xactengine3_3.dll', 'xactengine3_4.dll', 'xactengine3_5.dll',
    'xactengine3_6.dll', 'xactengine3_7.dll', 'xapofx1_1.dll', 'xapofx1_2.dll', 'xapofx1_3.dll', 'xapofx1_4.dll',
    'xapofx1_5.dll', 'xaudio2_0.dll', 'xaudio2_1.dll', 'xaudio2_2.dll', 'xaudio2_3.dll', 'xaudio2_4.dll',
    'xaudio2_5.dll', 'xaudio2_6.dll', 'xaudio2_7.dll', 'xaudio2_8.dll', 'xaudio2_9.dll', 'xinputuap.dll',
    'xmllite.dll', 'xolehlp.dll', 'xpssvcs.dll',)
W261_X64=(
    'acledit.dll', 'aclui.dll', 'activeds.dll', 'actxprxy.dll', 'adsldp.dll', 'adsldpc.dll', 'amsi.dll',
    'amstream.dll', 'apphelp.dll', 'atl.dll', 'atl110.dll', 'atl80.dll', 'atl90.dll', 'atlthunk.dll', 'atmlib.dll',
    'authz.dll', 'avicap32.dll', 'bcryptprimitives.dll', 'bluetoothapis.dll', 'browseui.dll', 'cdosys.dll',
    'chakra.dll', 'cldapi.dll', 'colorcnv.dll', 'comcat.dll', 'comsvcs.dll', 'concrt140.dll', 'connect.dll',
    'credui.dll', 'crtdll.dll', 'cryptdlg.dll', 'cryptdll.dll', 'cryptext.dll', 'cryptxml.dll', 'ctl3d32.dll',
    'd2d1.dll', 'd3d10.dll', 'd3d10_1.dll', 'd3d12.dll', 'd3d12core.dll', 'd3d8thk.dll', 'd3dcompiler_33.dll',
    'd3dcompiler_34.dll', 'd3dcompiler_35.dll', 'd3dcompiler_36.dll', 'd3dcompiler_37.dll', 'd3dcompiler_38.dll',
    'd3dcompiler_39.dll', 'd3dcompiler_40.dll', 'd3dcompiler_41.dll', 'd3dcompiler_42.dll', 'd3dcompiler_43.dll',
    'd3dcompiler_46.dll', 'd3dim.dll', 'd3dim700.dll', 'd3drm.dll', 'd3dx10_33.dll', 'd3dx10_34.dll',
    'd3dx10_35.dll', 'd3dx10_36.dll', 'd3dx10_37.dll', 'd3dx10_38.dll', 'd3dx10_39.dll', 'd3dx10_40.dll',
    'd3dx10_41.dll', 'd3dx10_42.dll', 'd3dx10_43.dll', 'd3dx11_42.dll', 'd3dx11_43.dll', 'd3dxof.dll',
    'davclnt.dll', 'dbgeng.dll', 'dciman32.dll', 'dcomp.dll', 'ddraw.dll', 'ddrawex.dll', 'dhcpcsvc6.dll',
    'dhtmled.ocx', 'diasymreader.dll', 'directmanipulation.dll', 'dispex.dll', 'dmusic32.dll', 'dplay.dll',
    'dplayx.dll', 'dpnaddr.dll', 'dpnet.dll', 'dpnhupnp.dll', 'dpnlobby.dll', 'dpvoice.dll', 'dpwsockx.dll',
    'drmclien.dll', 'dsdmo.dll', 'dsquery.dll', 'dsrole.dll', 'dsuiext.dll', 'dx8vb.dll', 'dxcore.dll',
    'dxdiagn.dll', 'dxtrans.dll', 'dxva2.dll', 'esent.dll', 'evr.dll', 'explorerframe.dll', 'faultrep.dll',
    'feclient.dll', 'fntcache.dll', 'fontsub.dll', 'fusion.dll', 'fwpuclnt.dll', 'gameinput.dll', 'gameux.dll',
    'glu32.dll', 'gpkcsp.dll', 'hhctrl.ocx', 'hlink.dll', 'hnetcfg.dll', 'hrtfapo.dll', 'ia2comproxy.dll',
    'iccvid.dll', 'icmp.dll', 'icmui.dll', 'icuin.dll', 'icuuc.dll', 'ieproxy.dll', 'inetcomm.dll',
    'inetmib1.dll', 'infosoft.dll', 'initpki.dll', 'inkobj.dll', 'inseng.dll', 'iprop.dll', 'itircl.dll',
    'itss.dll', 'iyuv_32.dll', 'ksproxy.ax', 'ksuser.dll', 'ktmw32.dll', 'l3codeca.acm', 'l3codecx.ax',
    'loadperf.dll', 'lz32.dll', 'magnification.dll', 'mapi32.dll', 'mapistub.dll', 'mciavi32.dll', 'mcicda.dll',
    'mciqtz32.dll', 'mciseq.dll', 'mciwave.dll', 'mf.dll', 'mf3216.dll', 'mferror.dll', 'mfh264enc.dll',
    'mfmediaengine.dll', 'mfplat.dll', 'mfplay.dll', 'mfreadwrite.dll', 'mgmtapi.dll', 'mmcndmgr.dll',
    'mp3dmod.dll', 'mprapi.dll', 'msado15.dll', 'msasn1.dll', 'msauddecmft.dll', 'mscat32.dll', 'msctf.dll',
    'msctfmonitor.dll', 'msctfp.dll', 'msdaps.dll', 'msdelta.dll', 'msdmo.dll', 'msdrm.dll', 'msftedit.dll',
    'msgsm32.acm', 'msi.dll', 'msident.dll', 'msimsg.dll', 'msimtf.dll', 'msisip.dll', 'msisys.ocx', 'msls31.dll',
    'msmpeg2vdec.dll', 'msnet32.dll', 'mspatcha.dll', 'msrle32.dll', 'msscript.ocx', 'mssign32.dll', 'mssip32.dll',
    'msttsengine.dll', 'msvcirt.dll', 'msvcm80.dll', 'msvcm90.dll', 'msvcp100.dll', 'msvcp110.dll', 'msvcp120.dll',
    'msvcp120_app.dll', 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_atomic_wait.dll',
    'msvcp140_codecvt_ids.dll', 'msvcp60.dll', 'msvcp70.dll', 'msvcp71.dll', 'msvcp80.dll', 'msvcp90.dll',
    'msvcp_win.dll', 'msvcr100.dll', 'msvcr110.dll', 'msvcr120.dll', 'msvcr120_app.dll', 'msvcr70.dll',
    'msvcr71.dll', 'msvcr80.dll', 'msvcr90.dll', 'msvcrt20.dll', 'msvcrt40.dll', 'msvcrtd.dll', 'msvdsp.dll',
    'msvidc32.dll', 'msvproc.dll', 'mswsock.dll', 'msxml.dll', 'msxml2.dll', 'msxml4.dll', 'msxml6.dll',
    'mtxdm.dll', 'nddeapi.dll', 'ndfapi.dll', 'netcfgx.dll', 'netprofm.dll', 'ninput.dll', 'normaliz.dll',
    'npmshtml.dll', 'npptools.dll', 'ntdsapi.dll', 'objsel.dll', 'odbcbcp.dll', 'odbccp32.dll', 'odbccu32.dll',
    'olecli32.dll', 'oledb32.dll', 'oledlg.dll', 'olepro32.dll', 'olesvr32.dll', 'opcservices.dll', 'packager.dll',
    'pdh.dll', 'photometadatahandler.dll', 'pidgen.dll', 'powrprof.dll', 'profapi.dll', 'pstorec.dll',
    'pwrshplugin.dll', 'qasf.dll', 'qdvd.dll', 'qedit.dll', 'query.dll', 'qwave.dll', 'regapi.dll',
    'resampledmo.dll', 'riched20.dll', 'riched32.dll', 'rsabase.dll', 'rstrtmgr.dll', 'rtscom.dll', 'rtutils.dll',
    'rtworkq.dll', 'samlib.dll', 'sapi.dll', 'sas.dll', 'scarddlg.dll', 'sccbase.dll', 'schannel.dll', 'scrobj.dll',
    'scrrun.dll', 'security.dll', 'sensapi.dll', 'serialui.dll', 'shdoclc.dll', 'slbcsp.dll', 'slc.dll',
    'snmpapi.dll', 'softpub.dll', 'sppc.dll', 'srvcli.dll', 'sspicli.dll', 'sti.dll', 'strmdll.dll', 'svrapi.dll',
    'sxs.dll', 't2embed.dll', 'tapi32.dll', 'tbs.dll', 'tdh.dll', 'thumbcache.dll', 'tiptsf.dll', 'traffic.dll',
    'twaindsm.dll', 'tzres.dll', 'uianimation.dll', 'uiautomationcore.dll', 'uiribbon.dll', 'unicows.dll',
    'url.dll', 'utildll.dll', 'vbscript.dll', 'vccorlib140.dll', 'vcomp.dll', 'vcomp100.dll', 'vcomp110.dll',
    'vcomp120.dll', 'vcomp140.dll', 'vcomp90.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'vga.dll',
    'vidreszr.dll', 'wbemdisp.dll', 'wbemprox.dll', 'webservices.dll', 'websocket.dll', 'wer.dll', 'wevtapi.dll',
    'winbio.dll', 'winbrand.dll', 'windowscodecsext.dll', 'winemapi.dll', 'wing32.dll', 'winnls32.dll',
    'winsqlite3.dll', 'winsta.dll', 'wintab32.dll', 'wintypes.dll', 'winusb.dll', 'wlanapi.dll',
    'wlanui.dll', 'wldap32.dll', 'wldp.dll', 'wmasf.dll', 'wmi.dll', 'wminet_utils.dll', 'wmiutils.dll', 'wmp.dll',
    'wmphoto.dll', 'wmvcore.dll', 'wmvdecod.dll', 'wnaspi32.dll', 'wpc.dll', 'wsdapi.dll', 'wshom.ocx',
    'wsnmp32.dll', 'x3daudio1_0.dll', 'x3daudio1_1.dll', 'x3daudio1_2.dll', 'x3daudio1_3.dll', 'x3daudio1_4.dll',
    'x3daudio1_5.dll', 'x3daudio1_6.dll', 'x3daudio1_7.dll', 'xactengine2_0.dll', 'xactengine2_4.dll',
    'xactengine2_7.dll', 'xactengine2_9.dll', 'xactengine3_0.dll', 'xactengine3_1.dll', 'xactengine3_2.dll',
    'xactengine3_3.dll', 'xactengine3_4.dll', 'xactengine3_5.dll', 'xactengine3_6.dll', 'xactengine3_7.dll',
    'xapofx1_1.dll', 'xapofx1_2.dll', 'xapofx1_3.dll', 'xapofx1_4.dll', 'xapofx1_5.dll', 'xaudio2_0.dll',
    'xaudio2_1.dll', 'xaudio2_2.dll', 'xaudio2_3.dll', 'xaudio2_4.dll', 'xaudio2_5.dll', 'xaudio2_6.dll',
    'xaudio2_7.dll', 'xaudio2_8.dll', 'xaudio2_9.dll', 'xinputuap.dll', 'xmllite.dll', 'xolehlp.dll', 'xpssvcs.dll',)
W261_LEFT_OUT={
    'kernel driver (.sys): runs in winedevice, not in a program':
        ('cng.sys', 'fltmgr.sys', 'hidclass.sys', 'hidparse.sys', 'http.sys', 'ksecdd.sys', 'mouhid.sys',
         'mountmgr.sys', 'ndis.sys', 'netio.sys', 'nsiproxy.sys', 'scsiport.sys', 'tdi.sys', 'usbd.sys',
         'winebth.sys', 'winebus.sys', 'winehid.sys', 'wineusb.sys', 'winexinput.sys', 'wmilib.sys',),
    'Control Panel applet: control.exe opens it; no program imports it':
        ('appwiz.cpl', 'bthprops.cpl', 'desk.cpl', 'inetcpl.cpl', 'irprops.cpl', 'joy.cpl',),
    'needs a Windows service (Task Scheduler, Event Log, WIA, Smart Card, Windows Update, Server, BITS, HTTP.sys) that does not run here':
        ('httpapi.dll', 'mstask.dll', 'qmgr.dll', 'qmgrprxy.dll', 'scardsvr.dll', 'schedsvc.dll', 'srvsvc.dll',
         'taskschd.dll', 'wevtsvc.dll', 'wiaservc.dll', 'wuapi.dll', 'wuaueng.dll',),
    'printing: the spooler service and its Unix side (CUPS) are absent':
        ('localspl.dll', 'localui.dll', 'ntprint.dll', 'printui.dll', 'prntvpt.dll', 'spoolss.dll',
         'wineps.drv', 'winprint.dll', 'xpsprint.dll',),
    'its Unix side (.so) is not in the Orbis ELF (platform/ps4/pw_wine_unixlibs.c)':
        ('ctapi32.dll', 'dwrite.dll', 'kerberos.dll', 'msv1_0.dll', 'odbc32.dll', 'qcap.dll', 'winedmo.dll',),
    'needs Wine Mono, not staged':
        ('mscoree.dll', 'mscorwks.dll',),
    '16-bit Windows support; no 16-bit layer here':
        ('olethk32.dll', 'vdmdbg.dll', 'w32skrnl.dll', 'wow32.dll',),
    'API set schema: the 64-bit one comes from out/wine-pe64; not loaded as a DLL by programs':
        ('apisetschema.dll',),
    'system administration (volumes, Hyper-V, clusters, restore points, driver install)':
        ('clusapi.dll', 'difxapi.dll', 'fltlib.dll', 'hvsimanagementapi.dll', 'msports.dll', 'newdev.dll',
         'resutils.dll', 'sfc.dll', 'sfc_os.dll', 'srclient.dll', 'updspapi.dll', 'virtdisk.dll', 'vssapi.dll',
         'wdscore.dll', 'wimgapi.dll', 'wofutil.dll',),
    'WinRT (UWP) API: needs the WindowsRuntime activation registry; no classic Win32 game imports it':
        ('appxdeploymentclient.dll', 'bcp47langs.dll', 'coremessaging.dll', 'cryptowinrt.dll',
         'dataexchange.dll', 'gamingtcui.dll', 'geolocation.dll', 'graphicscapture.dll', 'rometadata.dll',
         'threadpoolwinrt.dll', 'twinapi.appcore.dll', 'windows.applicationmodel.dll',
         'windows.devices.bluetooth.dll', 'windows.devices.enumeration.dll', 'windows.devices.radios.dll',
         'windows.devices.usb.dll', 'windows.gaming.input.dll', 'windows.gaming.ui.gamebar.dll',
         'windows.globalization.dll', 'windows.graphics.dll', 'windows.media.devices.dll', 'windows.media.dll',
         'windows.media.mediacontrol.dll', 'windows.media.playback.backgroundmediaplayer.dll',
         'windows.media.playback.mediaplayer.dll', 'windows.media.speech.dll',
         'windows.networking.connectivity.dll', 'windows.networking.dll', 'windows.networking.hostname.dll',
         'windows.perception.stub.dll', 'windows.security.authentication.onlineid.dll',
         'windows.security.credentials.ui.userconsentverifier.dll', 'windows.storage.applicationdata.dll',
         'windows.storage.dll', 'windows.system.profile.systemid.dll',
         'windows.system.profile.systemmanufacturers.dll', 'windows.ui.core.textinput.dll', 'windows.ui.dll',
         'windows.ui.xaml.dll', 'windows.web.dll',),
    'imports winegstreamer, whose GStreamer side does not exist here (W225)':
        ('ir50_32.dll', 'wmadmod.dll',),
    'imports winedmo, whose Unix side is not in the Orbis ELF':
        ('mfasfsrcsnk.dll', 'mfmp4srcsnk.dll', 'mfsrcsnk.dll',),
    'imports odbc32, whose Unix side is not in the Orbis ELF':
        ('msdasql.dll',),
    "x86_64 only: x64 DirectShow: its filter registration is stage-dshow-i386.py's work, i386 only so far":
        ('devenum.dll', 'quartz.dll',),
    'x86_64 only: kernel-mode support (hal), not for programs':
        ('hal.dll',),
    'x86_64 only: part of the WoW64 layer, which this build provides itself (wow64native)':
        ('wow64cpu.dll',),
    'x86_64 only: x64 DirectMusic: its PS4 fixes (dmsynth, dmband, dmime; build-dmsynth-i386.py) are i386 only':
        ('dmband.dll', 'dmcompos.dll', 'dmime.dll', 'dmloader.dll', 'dmscript.dll', 'dmstyle.dll', 'dmusic.dll',
         'dswave.dll',),
}
# staged by other stagers as of W260 (DXVK, Vulkan, MangoHud, HID, W225 DirectShow, W138 dmsynth, W174 extras,
# W177 MSHTML, the console's own programs): part of the view, never staged here
W261_OTHERS={'i386-windows':{
        'avicap32.dll', 'bcrypt.dll', 'compstui.dll', 'd3d10core.dll', 'd3d11.dll', 'd3dcompiler_47.dll',
        'dbghelp.dll', 'devenum.dll', 'dmsynth.dll', 'dpnhpast.dll', 'dwmapi.dll', 'iexplore.exe',
        'imaadp32.acm', 'jscript.dll', 'libmangohud.dll', 'midimap.dll', 'msacm32.drv', 'msadp32.acm',
        'msdmo.dll', 'msg711.acm', 'mshtml.dll', 'msimg32.dll', 'msvfw32.dll', 'msxml3.dll', 'netapi32.dll',
        'netutils.dll', 'orbis32host.exe', 'psapi.dll', 'pwmpeg1.ax', 'quartz.dll', 'rasapi32.dll',
        'rasdlg.dll', 'usp10.dll', 'uxtheme.dll', 'winspool.drv', 'wtsapi32.dll', 'xinput1_1.dll',
        'xinput1_2.dll', 'xinput1_3.dll', 'xinput1_4.dll', 'xinput9_1_0.dll',},
    'x86_64-windows':{
        'avrt.dll', 'bcrypt.dll', 'cards.dll', 'compstui.dll', 'd3d10core.dll', 'd3d11.dll', 'd3d8.dll',
        'd3d9.dll', 'd3dcompiler_47.dll', 'dbghelp.dll', 'dinput.dll', 'dosbox_pure_libretro.dll',
        'doshost.exe', 'dpnhpast.dll', 'dwmapi.dll', 'dxgi.dll', 'dxvk_dxgi.dll', 'hid.dll', 'iexplore.exe',
        'imaadp32.acm', 'jscript.dll', 'jsproxy.dll', 'libcdio.dll', 'libgallium_wgl.dll', 'libmangohud.dll',
        'midimap.dll', 'msacm32.drv', 'msadp32.acm', 'msg711.acm', 'mshtml.dll', 'msxml3.dll', 'netapi32.dll',
        'netutils.dll', 'opengl32.dll', 'psapi.dll', 'pwhidhost.dll', 'rasapi32.dll', 'rasdlg.dll', 'sol.exe',
        'spider.exe', 'usp10.dll', 'vulkan-1.dll', 'wfm.exe', 'winecfg.cpl', 'wined3d.dll', 'winevulkan.dll',
        'winhttp.dll', 'winspool.drv', 'wow64native.dll', 'wowprospero.dll', 'wsock32.dll', 'wtsapi32.dll',
        'xinput1_1.dll', 'xinput1_2.dll', 'xinput1_3.dll', 'xinput1_4.dll', 'xinput9_1_0.dll',}}
wine_commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if wine_commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('i386 DLLs require the pinned Wine revision')
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def locate(name,arch='i386-windows'):
    stem=name[:-4]
    candidate=BUILD/'dlls'/stem/arch/name
    return candidate if candidate.is_file() else None
def imports(path):
    """Import and delay-import names of a PE32 image (directories 1 and 13)."""
    data=path.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
    machine=struct.unpack_from('<H',data,pe+4)[0]
    if machine not in (0x14c,0x8664):raise SystemExit('Not a PE for i386 or x86-64: '+str(path))
    directories=96 if machine==0x14c else 112
    sections_count=struct.unpack_from('<H',data,pe+6)[0];optional=pe+24
    optional_size=struct.unpack_from('<H',data,pe+20)[0]
    sections=[struct.unpack_from('<IIII',data,optional+optional_size+40*i+8) for i in range(sections_count)]
    def offset(rva):
        for size,address,raw_size,raw in sections:
            if address<=rva<address+max(size,raw_size):return raw+rva-address
        return None
    def name_at(rva):
        at=offset(rva);return data[at:data.index(b'\0',at)].decode().lower() if at is not None else None
    names=set()
    for directory,entry_size,name_field in ((1,20,12),(13,32,4)):
        rva=struct.unpack_from('<I',data,optional+directories+8*directory)[0]
        at=offset(rva) if rva else None
        while at is not None:
            entry=data[at:at+entry_size]
            if entry==bytes(entry_size):break
            name=name_at(struct.unpack_from('<I',entry,name_field)[0])
            if name:names.add(name)
            at+=entry_size
    return sorted(names)
with tarfile.open(ROOT/'reports/increment15/prefix-package/prefix.tar.gz') as archive:
    present={pathlib.PurePosixPath(m.name).name.lower() for m in archive
             if m.isfile() and '/syswow64/' in m.name}
# W260: the i386 msvfw32.dll (avifil32's import) is tools/stage-dshow-i386.py's (W225), which refuses a module
# already staged elsewhere
present.add('msvfw32.dll')
targets={}
missing_targets=[]
for stem in TARGETS:
    found=locate(stem+'.dll')
    if not found:missing_targets.append(stem);continue
    targets[stem+'.dll']=found
if missing_targets:raise SystemExit('Not built (make dlls/<name>/i386-windows/<name>.dll): '+', '.join(missing_targets))
closure={};unresolved=set();edges={}
pending=list(targets.values())
while pending:
    module=pending.pop()
    for name in imports(module):
        edges.setdefault(module.name,[]).append(name)
        if name in present or name in closure or name in targets or re.match(r'^(api|ext)-ms-',name):continue
        found=locate(name)
        if not found:unresolved.add(name);continue
        closure[name]=found;pending.append(found)
staged={}
for name,path in sorted({**closure,**targets}.items()):
    target=out/'i386-windows'/name;target.write_bytes(path.read_bytes())
    staged[name]={'path':'i386-windows/'+name,'sha256':sha(target),'source':str(path.relative_to(ROOT))}
present64={name.lower() for path in ('out/wine-pe64/manifest.json','out/wine-gui/manifest.json','out/wine-programs/manifest.json')
           for name in json.loads((ROOT/path).read_text())['modules']}
targets64={}
for stem in X64_TARGETS:
    found=locate(stem+'.dll','x86_64-windows')
    if not found:raise SystemExit('Not built: dlls/%s/x86_64-windows/%s.dll'%(stem,stem))
    targets64[stem+'.dll']=found
closure64={};pending=list(targets64.values())
while pending:
    module=pending.pop()
    for name in imports(module):
        edges.setdefault('x64:'+module.name,[]).append(name)
        if name in present64 or name in closure64 or name in targets64 or re.match(r'^(api|ext)-ms-',name):continue
        found=locate(name,'x86_64-windows')
        if not found:unresolved.add('x64:'+name);continue
        closure64[name]=found;pending.append(found)
staged64={}
for name,path in sorted({**closure64,**targets64}.items()):
    target=out/'x86_64-windows'/name;target.write_bytes(path.read_bytes())
    staged64[name]={'path':'x86_64-windows/'+name,'sha256':sha(target),'source':str(path.relative_to(ROOT))}
# ---- W261: stage, strip, register ----
def w261_pe(path):
    data=path.read_bytes();at=struct.unpack_from('<I',data,0x3c)[0]
    directories=96 if struct.unpack_from('<H',data,at+4)[0]==0x14c else 112
    count=struct.unpack_from('<H',data,at+6)[0];optional=at+24;size=struct.unpack_from('<H',data,at+20)[0]
    sections=[struct.unpack_from('<IIII',data,optional+size+40*i+8) for i in range(count)]
    def offset(rva):
        for vsize,address,raw_size,raw in sections:
            if address<=rva<address+max(vsize,raw_size):return raw+rva-address
        return None
    return data,offset,lambda index:struct.unpack_from('<II',data,optional+directories+8*index)
def w261_registry_scripts(path):
    """Text of each WINE_REGISTRY resource (as stage-dshow-i386.py)."""
    data,offset,directory=w261_pe(path);rva=directory(2)[0]
    if not rva:return []
    base=offset(rva)
    def entries(at):
        named,ids=struct.unpack_from('<HH',data,at+12)
        return [struct.unpack_from('<II',data,at+16+8*i) for i in range(named+ids)]
    def name(value):
        if not value&0x80000000:return value
        at=base+(value&0x7fffffff);length=struct.unpack_from('<H',data,at)[0]
        return data[at+2:at+2+2*length].decode('utf-16-le')
    found=[]
    for type_name,type_at in entries(base):
        if name(type_name)!='WINE_REGISTRY':continue
        for _,name_at in entries(base+(type_at&0x7fffffff)):
            for _,leaf in entries(base+(name_at&0x7fffffff)):
                data_rva,length=struct.unpack_from('<II',data,base+leaf)
                found.append(data[offset(data_rva):offset(data_rva)+length].decode('utf-8').rstrip('\0'))
    return found
class W261Registrar:
    """dlls/atl/registrar.c for registration (as stage-dshow-i386.py): words, quoted strings, nested keys, val, s/d/b."""
    def __init__(self,text,replacements):
        def replace(match):
            word=match.group(1)
            if word=='':return '%'
            for key,value in replacements.items():
                if key.lower()==word.lower():return value
            raise SystemExit('No replacement for %'+word+'%')
        self.text=re.sub(r'%([^%]*)%',replace,text);self.at=0
    def word(self):
        t=self.text;i=self.at
        while i<len(t) and t[i].isspace():i+=1
        if i>=len(t):self.at=i;return ''
        if t[i] in '}=':word=t[i];i+=1
        elif t[i]=="'":
            parts=[];i+=1
            while True:
                end=t.index("'",i)
                if end+1<len(t) and t[end+1]=="'":parts.append(t[i:end+1]);i=end+2;continue
                parts.append(t[i:end]);i=end+1;break
            word=''.join(parts)
        else:
            j=i
            while j<len(t) and not t[j].isspace():j+=1
            word=t[i:j];i=j
        while i<len(t) and t[i].isspace():i+=1
        self.at=i;return word
    def peek(self):return self.text[self.at:self.at+2]
    def run(self,emit):
        roots={'HKCR':'HKCR','HKEY_CLASSES_ROOT':'HKCR','HKLM':'HKLM','HKEY_LOCAL_MACHINE':'HKLM'}
        word=self.word()
        while word:
            if word.upper() not in roots:raise SystemExit('Unsupported root key: '+word)
            if self.word()!='{':raise SystemExit('Expected {')
            self.keys([roots[word.upper()]],emit)
            word=self.word()
    def keys(self,path,emit):
        word=self.word()
        while word!='}':
            kind='key'
            if word.lower() in ('noremove','forceremove','val','delete'):
                kind={'val':'val','delete':'delete'}.get(word.lower(),'key');word=self.word()
            if kind=='delete':raise SystemExit('Delete in a registration script: '+word)
            if kind=='key':emit(path+[word],None,None)
            if self.peek()[:1]=='=':
                self.at+=1;typ=self.word();value=self.word()
                if typ=='s':data=('sz',value)
                elif typ=='d':data=('dword',int(value,10))
                elif typ=='b':data=('binary',bytes.fromhex(value))
                else:raise SystemExit('Unsupported value type: '+typ)
                if kind=='val':emit(path,word,data)
                else:emit(path+[word],'',data)
            elif kind=='val':raise SystemExit('val without a value: '+word)
            if kind=='key' and self.peek()[:1]=='{' and self.peek()[1:2].isspace():
                self.word();self.keys(path+[word],emit)
            word=self.word()
def w261_views(arch,path):
    """HKCR/HKLM path -> the key relative to HKLM the program of that view reads."""
    root,rest=path[0],path[1:]
    if arch=='x86_64-windows':return ['Software','Classes']+rest if root=='HKCR' else rest
    if root=='HKCR':
        if rest and rest[0].lower() in ('clsid','interface','typelib'):return ['Software','Classes','Wow6432Node']+rest
        return ['Software','Classes']+rest
    if rest and rest[0].lower()=='software':return ['Software','Wow6432Node']+rest[1:]
    return rest
def w261_escape(text):
    return ''.join('\\\\' if c=='\\' else '\\"' if c=='"' else c if 32<=ord(c)<127 else '\\x%04x'%ord(c) for c in text)
def w261_reg_data(data):
    kind,value=data
    if kind=='sz':return '"'+w261_escape(value)+'"'
    if kind=='dword':return 'dword:%08x'%value
    return 'hex:'+','.join('%02x'%b for b in value)
with tarfile.open(ROOT/'reports/increment15/prefix-package/prefix.tar.gz') as archive:
    w261_sealed={'i386-windows':set(),'x86_64-windows':set()};w261_sealed_keys=set()
    for member in archive:
        if not member.isfile():continue
        name=pathlib.PurePosixPath(member.name).name
        if '/syswow64/' in member.name:w261_sealed['i386-windows'].add(name.lower())
        elif '/system32/' in member.name:w261_sealed['x86_64-windows'].add(name.lower())
        if name=='system.reg':
            sealed_text=archive.extractfile(member).read().decode('utf-8','replace')
            w261_sealed_keys={m.group(1).lower() for m in re.finditer(r'^\[(.*)\](?: \d+)?$',sealed_text,re.M)}
            w261_sealed_values={};key=None
            for line in sealed_text.splitlines():
                found=re.match(r'^\[(.*)\](?: \d+)?$',line)
                if found:key=w261_sealed_values.setdefault(found.group(1).lower(),set())
                elif key is not None and '=' in line and line[:1] in '@"':key.add(line.split('=',1)[0].lower())
w261_left={name for names in W261_LEFT_OUT.values() for name in names}
w261={};w261_writes={};w261_order=[];w261_registered={};w261_problems=[]
def w261_emit(key,name,data):
    key=tuple(key)
    if (key,None) not in w261_writes:w261_writes[(key,None)]=None;w261_order.append((key,None))
    if name is None:return
    if (key,name) not in w261_writes:w261_order.append((key,name))
    w261_writes[(key,name)]=data
for arch,names,view in (('i386-windows',W261_I386,w261_sealed['i386-windows']|present|set(staged)),
                        ('x86_64-windows',W261_X64,w261_sealed['x86_64-windows']|present64|set(staged64))):
    folder=out/'w261'/arch;folder.mkdir(parents=True,exist_ok=True)
    for old in folder.iterdir():old.unlink()
    listed=set(names);view=view|W261_OTHERS[arch];w261[arch]={}
    clash=sorted(listed&(view|w261_left))
    if clash:raise SystemExit('W261 '+arch+': listed and also in the view or left out: '+', '.join(clash))
    for name in names:
        source=next((p for p in (BUILD/'dlls'/name.rsplit('.',1)[0]/arch/name,BUILD/'dlls'/name/arch/name) if p.is_file()),None)
        if not source:raise SystemExit('Not built: dlls/%s/%s/%s'%(name.rsplit('.',1)[0],arch,name))
        for imported in imports(source):
            if imported in view or imported in listed or re.match(r'^(api|ext)-ms-',imported):continue
            w261_problems.append('%s %s imports %s (%s)'%(arch,name,imported,'left out' if imported in w261_left else 'not in the view'))
        if w261_problems:continue
        target=folder/name
        subprocess.run([{'i386-windows':'i686-w64-mingw32-strip','x86_64-windows':'x86_64-w64-mingw32-strip'}[arch],
                        '--strip-debug','-o',str(target),str(source)],check=True)
        w261[arch][name]={'path':'w261/'+arch+'/'+name,'sha256':sha(target),'source':str(source.relative_to(ROOT)),
                          'source_sha256':sha(source),'stripped':'--strip-debug'}
    if w261_problems:continue
    for name in sorted(set(names)|{'avifil32.dll'}):
        source=folder/name if name in listed else locate(name,arch)
        texts=w261_registry_scripts(source)
        for text in texts:
            W261Registrar(text,{'MODULE':'C:\\windows\\system32\\'+name,'SystemRoot':'C:\\windows'}).run(
                lambda key,value_name,data:w261_emit(w261_views(arch,key),value_name,data))
        if texts:w261_registered.setdefault(arch,[]).append(name)
if w261_problems:raise SystemExit('W261 lists are incomplete:\n  '+'\n  '.join(w261_problems))
w261_text='';w261_keys=0;w261_kept=0
for key,name in w261_order:
    if name is not None:continue
    path='\\\\'.join(w261_escape(part) for part in key)
    # a value the sealed registry already has stays as it is (atl90 over atl100, oleaut32's and ole2disp's typelibs)
    names=[n for k,n in w261_order if k==key and n is not None]
    kept=[n for n in names if ('@' if n=='' else '"'+w261_escape(n)+'"').lower() in w261_sealed_values.get(path.lower(),())]
    w261_kept+=len(kept)
    lines=[('@' if n=='' else '"'+w261_escape(n)+'"')+'='+w261_reg_data(w261_writes[(key,n)]) for n in names if n not in kept]
    if not lines and path.lower() in w261_sealed_keys:continue
    w261_text+='\n['+path+'] 1793390636\n#time=1dd68a9cb52bf36\n'+''.join(line+'\n' for line in lines);w261_keys+=1
(out/'system.reg.add').write_text(w261_text)
manifest={'schema_version':1,'modules_x64':staged64,'wine_commit':wine_commit,'targets':sorted(targets),'modules':staged,
          'import_edges':edges,'unresolved_imports':sorted(unresolved),
          'excluded':'modules already in the sealed prefix syswow64 and api-set names','source_patches':False,
          # winevulkan.so and ws2_32.so have WoW64 tables in the ELF (pw_wine_unixlibs.c);
          # these Unix sides are not linked yet, so their 32-bit callers get Wine's own error.
          'unix_sides_missing':['wined3d.so','opengl32.so'],
          'builder_sha256':sha(pathlib.Path(__file__)),
          # W261: syswow64/system32 only (tools/build-wine-hardware.py), their registration, what is left out
          'w261':w261,'w261_left_out':W261_LEFT_OUT,'w261_registered':w261_registered,
          'registry':{'path':'system.reg.add','sha256':sha(out/'system.reg.add'),'keys':w261_keys,'sealed_values_kept':w261_kept}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'w261':{arch:len(m) for arch,m in w261.items()},'w261_registry_keys':w261_keys,
                  'w261_bytes':{arch:sum((out/e['path']).stat().st_size for e in m.values()) for arch,m in w261.items()}}))
print(json.dumps({'modules_x64':sorted(staged64),'modules':len(staged),'targets':sorted(targets),'unresolved':sorted(unresolved)}))
