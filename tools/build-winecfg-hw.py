#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build winecfg for the hardware package: Apply does not wait on other threads windows (W183).

W180/W182: winecfg froze applying a visual style. update_window_pos sent SetWindowPos to every
top-level window, and for another thread's window win32u waits for that thread without a timeout;
winecfg runs as a guest in explorer's process, so one thread not reading messages held Apply.
Other threads windows get the change posted (SWP_ASYNCWINDOWPOS). The W182 timing markers
(PWCFG) were removed in W189. W190: Apply ends with RegFlushKey(HKEY_CURRENT_USER), so the
theme reaches disk before the title is killed. W220: the Applications tab has a "Run alone"
checkbox (AppDefaults <exe> "OrbisRunsAlone"), Add application writes the program's key on Apply,
and that Apply writes HKCU to disk too; appdefaults.c is revised along with theme.c.
The overlay is compiled with the pinned build's own commands (make -n).
Output: out/winecfg-hw/winecfg.exe and manifest.json.
"""
import hashlib,json,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'.deps/wine/source';BUILD=ROOT/'.deps/wine/runtime/build'
work=ROOT/'build/winecfg-hw';overlay=work/'overlay';out=ROOT/'out/winecfg-hw'
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
commit=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
if commit!=json.loads((ROOT/'sources.lock.json').read_text())['sources']['wine']['commit']:
    raise SystemExit('Wine source is not the pinned revision')
for folder in (work,out):
    if folder.exists():shutil.rmtree(folder)
shutil.copytree(SOURCE/'programs/winecfg',overlay)
revisions=[]
def revise(old,new,why,unit='theme.c'):
    target=overlay/unit;text=target.read_text()
    if text.count(old)!=1:raise SystemExit('Unexpected context in %s: %s'%(unit,old[:60]))
    target.write_text(text.replace(old,new));revisions.append(why)

revise('''static BOOL CALLBACK update_window_pos_proc(HWND hwnd, LPARAM lp)
{
    RECT rect;

    GetClientRect(hwnd, &rect);
    AdjustWindowRectEx(&rect, GetWindowLongW(hwnd, GWL_STYLE), !!GetMenu(hwnd),
                       GetWindowLongW(hwnd, GWL_EXSTYLE));
    SetWindowPos(hwnd, 0, 0, 0, rect.right - rect.left, rect.bottom - rect.top,
                 SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER);
    return TRUE;
}

/* Adjust the rectangle for top-level windows because the new non-client metrics may be different */
static void update_window_pos(void)
{
    EnumWindows(update_window_pos_proc, 0);
}''','''static BOOL CALLBACK update_window_pos_proc(HWND hwnd, LPARAM lp)
{
    RECT rect;
    UINT flags = SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER;

    GetClientRect(hwnd, &rect);
    AdjustWindowRectEx(&rect, GetWindowLongW(hwnd, GWL_STYLE), !!GetMenu(hwnd),
                       GetWindowLongW(hwnd, GWL_EXSTYLE));
    /* W183: SetWindowPos on another thread's window waits for that thread without a timeout. In
     * W182 winecfg ran as a guest in explorer's process and Apply never returned from here: a
     * top-level window of some thread that was not reading messages held it. Other threads'
     * windows get the change posted (SWP_ASYNCWINDOWPOS) and apply it when they next read. */
    if (GetWindowThreadProcessId(hwnd, NULL) != GetCurrentThreadId())
        flags |= SWP_ASYNCWINDOWPOS;
    SetWindowPos(hwnd, 0, 0, 0, rect.right - rect.left, rect.bottom - rect.top, flags);
    return TRUE;
}

/* Adjust the rectangle for top-level windows because the new non-client metrics may be different */
static void update_window_pos(void)
{
    EnumWindows(update_window_pos_proc, 0);
}''','update_window_pos: other threads windows get the change posted, not sent.')
# W190: the console kills the title, and its registry server saved every 30 s; W189's theme, OK
# about 7 s before the app was quit, was lost. Apply ends by writing HKCU to disk (RegFlushKey;
# the console's server writes on flush_key, tools/build-wine-delete-server.py).
revise('''                    update_mime_types(hDlg);
                    update_window_pos();''','''                    update_mime_types(hDlg);
                    update_window_pos();
                    RegFlushKey(HKEY_CURRENT_USER);  /* W190 */''','Apply: HKCU written to disk at the end.')

# W220 (W217: seamonkey.exe added in the Applications tab to run alone; nothing reached user.reg):
# winecfg had no control for OrbisRunsAlone (kernelbase ps4_runs_alone, tools/build-guest-hw.py),
# and Add application only adds a list row: Wine writes the AppDefaults key when a setting changes.
# A "Run alone" checkbox, made at WM_INITDIALOG under the Windows version (the list gets one row
# shorter and the rows below it move up; no resource change), writes or removes OrbisRunsAlone
# through the settings list; Apply creates the keys of the programs added, applies, and writes
# HKCU to disk.
revise('''/* called when the user selects a different application */''','''/* OrbisDesk W220: a 64-bit program marked here runs alone: the title restarts with it instead of
 * running it as a guest of explorer (kernelbase ps4_runs_alone, AppDefaults <exe> "OrbisRunsAlone"
 * "Y"). W217: the mark had no control, and Add application wrote nothing until a setting changed:
 * the programs added get their AppDefaults key on Apply. */
#define IDC_ORBIS_RUNS_ALONE 1290
static WCHAR *orbis_added[64];
static unsigned int orbis_added_count;

static void orbis_update_runs_alone(HWND dialog)
{
    HWND box = GetDlgItem(dialog, IDC_ORBIS_RUNS_ALONE);
    WCHAR *value;

    if (!box) return;
    EnableWindow(box, current_app != NULL);
    value = current_app ? get_reg_key(config_key, keypath(L""), L"OrbisRunsAlone", L"") : NULL;
    SendMessageW(box, BM_SETCHECK, value && value[0] == 'Y' ? BST_CHECKED : BST_UNCHECKED, 0);
    free(value);
}

static void orbis_on_runs_alone_click(HWND dialog)
{
    if (!current_app) return;
    set_reg_key(config_key, keypath(L""), L"OrbisRunsAlone",
                IsDlgButtonChecked(dialog, IDC_ORBIS_RUNS_ALONE) == BST_CHECKED ? L"Y" : NULL);
    SendMessageW(GetParent(dialog), PSM_CHANGED, (WPARAM) dialog, 0);
}

/* the list gets one row shorter and the rows below it move up; the checkbox takes the last row */
static void orbis_create_runs_alone(HWND dialog)
{
    RECT list, rect, row = { 0, 0, 0, 14 }, place = { 17, 197, 245, 207 };
    HWND listview = GetDlgItem(dialog, IDC_APP_LISTVIEW), child, box;

    if (!listview) return;
    MapDialogRect(dialog, &row);
    MapDialogRect(dialog, &place);
    GetWindowRect(listview, &list);
    MapWindowPoints(NULL, dialog, (POINT *)&list, 2);
    for (child = GetWindow(dialog, GW_CHILD); child; child = GetWindow(child, GW_HWNDNEXT))
    {
        if (child == listview) continue;
        GetWindowRect(child, &rect);
        MapWindowPoints(NULL, dialog, (POINT *)&rect, 2);
        if (rect.top >= list.bottom)
            SetWindowPos(child, 0, rect.left, rect.top - row.bottom, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE);
    }
    SetWindowPos(listview, 0, 0, 0, list.right - list.left, list.bottom - list.top - row.bottom,
                 SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
    box = CreateWindowExW(0, L"Button", L"Run a&lone (the title restarts with this program)",
                          WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_DISABLED | BS_AUTOCHECKBOX,
                          place.left, place.top, place.right - place.left, place.bottom - place.top,
                          dialog, (HMENU)(INT_PTR)IDC_ORBIS_RUNS_ALONE, GetModuleHandleW(NULL), NULL);
    if (box) SendMessageW(box, WM_SETFONT, SendMessageW(dialog, WM_GETFONT, 0, 0), FALSE);
}

/* Apply: the AppDefaults key of each program added (a removal queued after it still applies) */
static void orbis_create_added_keys(void)
{
    HKEY appdefaults, key;
    unsigned int i;

    if (!RegCreateKeyExW(config_key, L"AppDefaults", 0, NULL, 0, MAXIMUM_ALLOWED, NULL, &appdefaults, NULL))
    {
        for (i = 0; i < orbis_added_count; i++)
            if (!RegCreateKeyExW(appdefaults, orbis_added[i], 0, NULL, 0, MAXIMUM_ALLOWED, NULL, &key, NULL))
                RegCloseKey(key);
        RegCloseKey(appdefaults);
    }
    for (i = 0; i < orbis_added_count; i++) free(orbis_added[i]);
    orbis_added_count = 0;
}

/* called when the user selects a different application */''','Applications tab: run-alone checkbox and its helpers (W220).','appdefaults.c')
revise('''  set_window_title(dialog);
}

static BOOL list_contains_file''','''  set_window_title(dialog);
  orbis_update_runs_alone(dialog);  /* W220 */
}

static BOOL list_contains_file''','The checkbox follows the selected program (W220).','appdefaults.c')
revise('''      add_listview_item(listview, new_app, new_app);
''','''      add_listview_item(listview, new_app, new_app);
      /* W220: its AppDefaults key is created on Apply */
      if (orbis_added_count < ARRAY_SIZE(orbis_added)) orbis_added[orbis_added_count++] = wcsdup(new_app);
      SendMessageW(GetParent(dialog), PSM_CHANGED, (WPARAM) dialog, 0);
''','Add application: the key is created on Apply (W220).','appdefaults.c')
revise('''    case WM_INITDIALOG:
        init_appsheet(hDlg);''','''    case WM_INITDIALOG:
        orbis_create_runs_alone(hDlg);  /* W220: before the first selection */
        init_appsheet(hDlg);''','The checkbox is made with the tab (W220).','appdefaults.c')
revise('''        case PSN_APPLY:
            apply();''','''        case PSN_APPLY:
            orbis_create_added_keys();  /* W220 */
            apply();
            RegFlushKey(HKEY_CURRENT_USER);  /* W220, as W190 for the theme */''','Apply: added keys, settings, then HKCU to disk (W220).','appdefaults.c')
revise('''            case IDC_APP_REMOVEAPP:
              on_remove_app_click(hDlg);
              break;''','''            case IDC_APP_REMOVEAPP:
              on_remove_app_click(hDlg);
              break;
            case IDC_ORBIS_RUNS_ALONE:  /* W220 */
              orbis_on_runs_alone_click(hDlg);
              break;''','The checkbox click (W220).','appdefaults.c')

UNITS=('theme.c','appdefaults.c')
dry=subprocess.run(['make','-n']+[arg for unit in UNITS for arg in ('-W','../../source/programs/winecfg/'+unit)]+
                   ['programs/winecfg/x86_64-windows/winecfg.exe'],
                   cwd=BUILD,capture_output=True,text=True,check=True).stdout.replace('\\\n',' ')
commands=[]
for line in dry.splitlines():
    if 'programs/winecfg' not in line or line.startswith('make'):continue
    for unit in UNITS:
        line=line.replace('../../source/programs/winecfg/'+unit,str(overlay/unit))
    for name in [unit[:-2]+'.o' for unit in UNITS]+['winecfg.exe']:
        line=line.replace('programs/winecfg/x86_64-windows/'+name,str(work/name))
    commands.append(line)
if len(commands)!=3 or not all(any(str(overlay/unit) in c for c in commands[:2]) for unit in UNITS) or \
   str(work/'winecfg.exe') not in commands[2]:
    raise SystemExit('make -n did not give the winecfg commands:\n'+dry[-2000:])
work.mkdir(parents=True,exist_ok=True)
warnings=[]
for command in commands:
    run=subprocess.run(command,shell=True,cwd=BUILD,capture_output=True,text=True)
    if run.returncode:raise SystemExit(command[:300]+'\n'+run.stdout+run.stderr)
    warnings+=[l for l in (run.stdout+run.stderr).splitlines() if 'warning' in l]
out.mkdir(parents=True);shutil.copyfile(work/'winecfg.exe',out/'winecfg.exe')
manifest={'schema_version':1,'wine_commit':commit,'builder_sha256':sha(__file__),
          'winecfg':{'path':'winecfg.exe','sha256':sha(out/'winecfg.exe')},'revisions':revisions,
          'compile_warnings':warnings,'commands':commands}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'winecfg':manifest['winecfg']['sha256'][:16],'revisions':len(revisions),'warnings':len(warnings)}))
