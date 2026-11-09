#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build WFM (Winlator File Manager, https://github.com/brunodev85/wfm, MIT) as PE64.

W058. The sources are a clone in .deps/wfm at a recorded commit; they are compiled with
the flags of WFM's own Makefile (CFLAGS, include dirs, libraries, windows subsystem),
using the mingw-w64 cross compiler instead of w64devkit. Output: out/wfm/wfm.exe, LICENSE,
manifest.json.

alpha-1 licences (docs/RELEASE_LICENSES.md, the user's decision): WFM's "Load ISO image" extracted an
ISO/BIN/CUE image to X: through the repository's prebuilt libcdio.dll (GPL-3.0-or-later, no known
corresponding source). The DLL is no longer linked or shipped; the item shows an error and extracts nothing.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Keep the checkout and $HOME out of __FILE__ strings and debug info.
PREFIX_MAP=['-ffile-prefix-map=%s=.'%ROOT,'-ffile-prefix-map=%s=vk-h0'%(pathlib.Path.home()/'vk-h0')]
SOURCE=ROOT/'.deps/wfm';work=ROOT/'build/wfm';out=ROOT/'out/wfm'
COMMIT='6b1860895885a6d65c37815308260293341acb5f'
CC='x86_64-w64-mingw32-gcc';RC='x86_64-w64-mingw32-windres'
CFLAGS=['-O2','-std=c99','-DUNICODE','-D_UNICODE','-DCOBJMACROS','-DWINVER=0x0600','-Wall',
        '-include',str(ROOT/'tools/wfm-debug.h'),*PREFIX_MAP]
# the headers are compiled from a copy too (main.h without libcdio's); include/libcdio is not used
INCLUDE=['-I'+str(work/'include'),'-I'+str(ROOT/'platform/ps4')]
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=COMMIT:raise SystemExit('WFM clone is at %s, expected %s'%(commit,COMMIT))
for folder in (work,out):folder.mkdir(parents=True,exist_ok=True)
# Sources are compiled from a copy, with these changes (the clone stays as fetched).
REVISIONS=[('main.c','''            if (MessageBox(NULL, lc_str.msg_confirm_exit_app, lc_str.confirm_exit, MB_YESNO | MB_ICONQUESTION) == IDYES) {
                PostQuitMessage(0);
            }''','''            /* PS4 hardware build (W060): closing does not ask for confirmation */
            PostQuitMessage(0);''',"Close without the exit confirmation, at the user's request."),
# W293 (user, W292: in WFM's Desktop folder the shortcuts other than File Manager, Open Steam Client and
# Portal 2 showed no icon of their own, though the desktop shows them): Wine's shell32 takes a .lnk's icon
# only from its IconLocation, never from the target; the desktop falls back to the target's icon.
('content_view.c','''static void fillFileInfo(struct FileNode* node, struct ListItem* item) {''','''/* OrbisDesk W293: a shortcut's icon as the desktop shows it. Wine's shell32 takes a .lnk file's icon only
 * from its IconLocation; without one it is the generic file icon. Here: the IconLocation when there is one
 * (shell32 resolves it from the .lnk), else the target's icon, else the .lnk's own; with the shortcut arrow
 * in every view. */
static void orbisShortcutIcon(wchar_t* path, bool largeIcon, int* icon) {
    SHFILEINFO sfi = {0};
    wchar_t iconPath[MAX_PATH] = L"", target[MAX_PATH] = L"", expanded[MAX_PATH], message[3 * MAX_PATH];
    const wchar_t* source = path;
    const wchar_t* how = L"unread";
    int iconIndex = 0;
    IShellLinkW* link = NULL;
    IPersistFile* file = NULL;
    HRESULT init = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);

    if (SUCCEEDED(CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLinkW, (LPVOID*)&link))) {
        if (SUCCEEDED(IShellLinkW_QueryInterface(link, &IID_IPersistFile, (void**)&file))) {
            if (SUCCEEDED(IPersistFile_Load(file, path, STGM_READ))) {
                how = L"lnk";
                IShellLinkW_GetIconLocation(link, iconPath, MAX_PATH, &iconIndex);
                if (!iconPath[0]) IShellLinkW_GetPath(link, target, MAX_PATH, NULL, SLGP_RAWPATH);
            }
            IPersistFile_Release(file);
        }
        IShellLinkW_Release(link);
    }
    if (SUCCEEDED(init)) CoUninitialize();
    if (!iconPath[0] && target[0]) {
        if (ExpandEnvironmentStringsW(target, expanded, MAX_PATH) && expanded[0]) wcscpy_s(target, MAX_PATH, expanded);
        if (GetFileAttributesW(target) != INVALID_FILE_ATTRIBUTES) {
            source = target;
            how = L"target";
        }
        else how = L"target-missing";
    }
    /* W295: no SHGFI_LINKOVERLAY. On the console shell32's composed shortcut icon (iconcache.c,
     * SIC_OverlayShortcutImage) loses the base icon's colour and only the arrow shows; the arrow is drawn
     * as the list's overlay 1 instead (orbisShortcutOverlay). */
    if (SHGetFileInfo(source, 0, &sfi, sizeof(SHFILEINFO), SHGFI_SYSICONINDEX |
                      (largeIcon ? SHGFI_LARGEICON : SHGFI_SMALLICON))) {
        *icon = sfi.iIcon;
    }
    swprintf_s(message, 3 * MAX_PATH, L"PWFM shortcut_icon source=%ls path=%ls target=%ls icon=%d",
               how, path, target[0] ? target : iconPath, *icon);
    OutputDebugStringW(message);
}

/* W294: every list item in a Desktop folder (the user's or the public one) logs the icon it gets, once
 * per listing, whatever its type or the view */
static void orbisTraceDesktopIcon(wchar_t* path, enum FileType type, int style, int icon) {
    wchar_t folder[MAX_PATH] = L"", message[2 * MAX_PATH];
    size_t length;
    int csidl[2] = { CSIDL_DESKTOPDIRECTORY, CSIDL_COMMON_DESKTOPDIRECTORY }, i;

    for (i = 0; i < 2; i++) {
        if (SHGetFolderPath(NULL, csidl[i], NULL, SHGFP_TYPE_CURRENT, folder) != S_OK) continue;
        length = wcslen(folder);
        if (length && !_wcsnicmp(path, folder, length) && path[length] == L'\\\\') {
            swprintf_s(message, 2 * MAX_PATH, L"PWFM desktop_item_icon path=%ls type=%d view=%d icon=%d", path, (int)type, style, icon);
            OutputDebugStringW(message);
            return;
        }
    }
}

/* W295: the shortcut arrow (shell32 icon resource 30, IDI_SHELL_SHORTCUT) as overlay image 1 of the
 * system image lists, added once through shell32's own icon cache so the lists stay in step; a failure
 * is logged and the shortcuts then show without the arrow. */
static void orbisShortcutOverlay(HIMAGELIST big, HIMAGELIST small) {
    static int done = 0;
    wchar_t shell32[MAX_PATH], message[MAX_PATH + 64];
    int (WINAPI *cachedIndex)(const WCHAR*, int, UINT) = NULL;
    HMODULE module = GetModuleHandleW(L"shell32.dll");
    int index = -1;
    BOOL setBig = FALSE, setSmall = FALSE;

    if (done) return;
    done = 1;
    if (module) cachedIndex = (void*)GetProcAddress(module, "Shell_GetCachedImageIndexW");
    if (cachedIndex && GetSystemDirectoryW(shell32, MAX_PATH)) {
        wcscat_s(shell32, MAX_PATH, L"\\\\shell32.dll");
        index = cachedIndex(shell32, -30, 0);
    }
    if (index >= 0) {
        setBig = ImageList_SetOverlayImage(big, index, 1);
        setSmall = ImageList_SetOverlayImage(small, index, 1);
    }
    swprintf_s(message, MAX_PATH + 64, L"PWFM shortcut_overlay export=%d index=%d big=%d small=%d",
               cachedIndex != NULL, index, setBig, setSmall);
    OutputDebugStringW(message);
}

static void fillFileInfo(struct FileNode* node, struct ListItem* item) {''','W293: a shortcut shows its IconLocation or the icon of its target, with the arrow, as on the desktop.'),
('content_view.c','''            if (mask & LVIF_STATE) {
                nmlvdi->item.state = 0;
            }''','''            if (mask & LVIF_STATE) {
                /* W295: a shortcut gets the arrow as overlay 1 */
                nmlvdi->item.state = item->node->type == TYPE_FILE && hasFileExtension(item->node->name, L"lnk") ?
                                     INDEXTOOVERLAYMASK(1) : 0;
            }''','W295: shortcuts carry the arrow as the list overlay, over their own icon.'),
('content_view.c','''    else ListView_SetImageList(hwndContentView, himlSmall, LVSIL_SMALL);
''','''    else ListView_SetImageList(hwndContentView, himlSmall, LVSIL_SMALL);
    /* W295: the list asks for the overlay bits of each item (the shortcut arrow) */
    orbisShortcutOverlay(himlBig, himlSmall);
    ListView_SetCallbackMask(hwndContentView, LVIS_OVERLAYMASK);
''','W295: the shortcut arrow is registered as overlay 1 and asked per item.'),
('content_view.c','''                getFileInfo(path, item->node->type, viewStyle == STYLE_LARGE_ICON, &fi);
''','''                getFileInfo(path, item->node->type, viewStyle == STYLE_LARGE_ICON, &fi);
                /* W293/W294: getFileExtension gives the extension without its dot */
                if (item->node->type == TYPE_FILE && hasFileExtension(path, L"lnk"))
                    orbisShortcutIcon(path, viewStyle == STYLE_LARGE_ICON, &fi.icon);
                orbisTraceDesktopIcon(path, item->node->type, viewStyle, fi.icon);
''','W293: the list asks for the icon of a shortcut; each Desktop item logs the icon it gets.'),
# alpha-1 licences: no libcdio. The extraction code goes; "Load ISO image" says it is unavailable before it
# clears X: or records the image as the current one.
('file_actions.c','''static void extractSingleISOFile(void* handle, bool isCDImage, iso9660_stat_t* isoStat, wchar_t* dstPath) {''',
'''#if 0 /* OrbisDesk alpha-1: ISO extraction needed libcdio, which is not shipped */
static void extractSingleISOFile(void* handle, bool isCDImage, iso9660_stat_t* isoStat, wchar_t* dstPath) {''',
'alpha-1: the libcdio ISO extraction is not compiled (libcdio.dll is not shipped).'),
('file_actions.c','''    iso9660_filelist_free(isoFileList);
}
''','''    iso9660_filelist_free(isoFileList);
}
#endif
''','alpha-1: end of the code left out.'),
('file_actions.c','''        wchar_t* srcPath = actionData->srcPaths[0];
        bool isCDImage = !hasFileExtension(srcPath, L"iso");
''','','alpha-1: the ISO branch has no source image.'),
('file_actions.c','''        char filename[MAX_PATH] = {0};
        WideCharToMultiByte(CP_ACP, 0, srcPath, -1, filename, MAX_PATH, NULL, NULL);

        if (isCDImage) {
            CdIo_t* cdio = cdio_open(filename, DRIVER_UNKNOWN);
            cdio_set_arg(cdio, "joliet-level", "1");
            extractAllISOFiles(cdio, true, "/", actionData->dstPath);
            cdio_destroy(cdio);
        }
        else {
            iso9660_t* iso = iso9660_open_ext(filename, ISO_EXTENSION_JOLIET);
            extractAllISOFiles(iso, false, "/", actionData->dstPath);
            iso9660_close(iso);
        }
''','''        /* OrbisDesk alpha-1: never started (extractFilesFromISOImage refuses) */
''','alpha-1: the file action task has no ISO branch.'),
('file_actions.c','''void extractFilesFromISOImage(wchar_t* isoPath, wchar_t* dstPath) {
    actionData = calloc(1, sizeof(struct ActionData));''','''void extractFilesFromISOImage(wchar_t* isoPath, wchar_t* dstPath) {
    /* OrbisDesk alpha-1: ISO extraction used libcdio (GPL-3.0, a prebuilt DLL with no known source),
     * which OrbisDesk does not ship. It is an error, never an empty success. */
    wchar_t message[MAX_PATH + 64];
    swprintf_s(message, MAX_PATH + 64, L"PWFM iso_extract unavailable path=%ls", isoPath ? isoPath : L"");
    OutputDebugStringW(message);
    MessageBox(hwndMain, L"Loading ISO images is not available in OrbisDesk.", lc_str.alert, MB_OK | MB_ICONERROR);
}

/* WFM's original body, kept unreachable so the rest of the file stays as it is */
static __attribute__((unused)) void orbisUnusedISOExtract(wchar_t* isoPath, wchar_t* dstPath) {
    actionData = calloc(1, sizeof(struct ActionData));''','alpha-1: extracting an ISO image reports that it is unavailable.'),
('content_view.c','''static void onMenuItemLoadISOImageClick() {
    if (numSelectedItems != 1) {''','''static void onMenuItemLoadISOImageClick() {
    /* OrbisDesk alpha-1: no ISO extraction (libcdio is not shipped); say so before X: is cleared or the
     * image recorded as the current one */
    if (numSelectedItems == 1) {
        wchar_t isoPath[MAX_PATH] = {0};
        getFileNodePath(selectedItems[0], isoPath);
        extractFilesFromISOImage(isoPath, NULL);
        return;
    }
    if (numSelectedItems != 1) {''','alpha-1: Load ISO image reports that it is unavailable and changes nothing.')]
# main.h without libcdio's headers
INCLUDE_REVISIONS=[('main.h','''#include <cdio/cdio.h>
#include <cdio/iso9660.h>
''','','alpha-1: no libcdio headers (libcdio is not used).')]
if (work/'src').exists():shutil.rmtree(work/'src')
shutil.copytree(SOURCE/'src',work/'src')
for name,old,new,why in REVISIONS:
    text=(work/'src'/name).read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in %s: %s'%(name,old[:60]))
    (work/'src'/name).write_text(text.replace(old,new))
if (work/'include').exists():shutil.rmtree(work/'include')
shutil.copytree(SOURCE/'include',work/'include',ignore=shutil.ignore_patterns('libcdio'))
for name,old,new,why in INCLUDE_REVISIONS:
    text=(work/'include'/name).read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in include/%s: %s'%(name,old[:60]))
    (work/'include'/name).write_text(text.replace(old,new))
subprocess.run(['python3',str(ROOT/'tools/patch-wfm-files.py'),str(work/'src')],check=True)
objects=[]
for source in sorted((work/'src').glob('*.c')):
    obj=work/(source.stem+'.o')
    subprocess.run([CC,*CFLAGS,*INCLUDE,'-c',str(source),'-o',str(obj)],check=True)
    objects.append(obj)
resource=work/'resource.o'
subprocess.run([RC,*INCLUDE,'-I'+str(SOURCE/'res'),'-i',str(SOURCE/'res/resource.rc'),'-o',str(resource)],check=True,cwd=SOURCE/'res')
objects.append(resource)
exe=out/'wfm.exe'
subprocess.run([CC,'-o',str(exe),*map(str,objects),'-s','-lcomctl32','-lgdi32','-lole32','-luuid',
                '-Wl,--subsystem,windows','-Wl,--no-insert-timestamp'],check=True)
# a libcdio.dll from an earlier run must not stay in out/wfm (build-wine-hardware.py stages the manifest's files)
(out/'libcdio.dll').unlink(missing_ok=True)
shutil.copyfile(SOURCE/'LICENSE',out/'LICENSE')
manifest={'schema_version':1,'source':'https://github.com/brunodev85/wfm','commit':commit,'license':'MIT',
          'files':{name:{'path':name,'sha256':sha(out/name)} for name in ('wfm.exe','LICENSE')},
          'iso_images':'unavailable: libcdio is not shipped (docs/RELEASE_LICENSES.md)',
          'revisions':[{'path':'src/'+n,'why':w} for n,_,_,w in REVISIONS]+[{'path':'include/'+n,'why':w} for n,_,_,w in INCLUDE_REVISIONS]+[{'path':'src/file_node.c, src/content_view.c','why':'W105: validate enumeration handles, list regular files regardless of archive flag, log real errors.'}],
          'patch_sha256':sha(ROOT/'tools/patch-wfm-files.py'),
          'operations_sha256':sha(ROOT/'tools/wfm-operations.h'),
          'debug_header_sha256':sha(ROOT/'tools/wfm-debug.h'),
          'open_protocol_sha256':sha(ROOT/'platform/ps4/pw_shell_open.h'),
          'source_hashes':{p.name:sha(p) for p in sorted((work/'src').glob('*.c'))},
          'cflags':CFLAGS,'libraries':['comctl32','gdi32','ole32','uuid']}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({name:e['sha256'] for name,e in manifest['files'].items()}))
