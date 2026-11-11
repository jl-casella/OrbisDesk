#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""Build winecfg for the hardware package: Apply does not wait on other threads windows (W183).

W180/W182: winecfg froze applying a visual style. update_window_pos sent SetWindowPos to every
top-level window, and for another thread's window win32u waits for that thread without a timeout;
winecfg runs as a guest in explorer's process, so one thread not reading messages held Apply.
Other threads windows get the change posted (SWP_ASYNCWINDOWPOS). The W182 timing markers
(PWCFG) were removed in W189. W190: Apply ends with RegFlushKey(HKEY_CURRENT_USER), so the
theme reaches disk before the title is killed. Applications has a per-path execution selector;
legacy OrbisRunsAlone choices are read as Exclusive. Add application writes its profile on Apply,
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

# Execution modes use their own path-specific namespace; Wine's other options keep AppDefaults.
(overlay/'pw_execution_mode.h').write_bytes((ROOT/'platform/ps4/pw_execution_mode.h').read_bytes())
revise('WINE_DEFAULT_DEBUG_CHANNEL(winecfg);','WINE_DEFAULT_DEBUG_CHANNEL(winecfg);\nstatic void orbis_load_profiles(HWND listview);','Execution profile enumeration declaration.','appdefaults.c')
marker='/* called when the user selects a different application */'
revise(marker,(ROOT/'native/winecfg_execution.h').read_text()+'\n'+marker,'Execution-mode selector, explanations and legacy compatibility.','appdefaults.c')
revise('  init_comboboxes(dialog);\n  \n  /* Select the default settings listview item',
       '  orbis_load_profiles(listview);\n  init_comboboxes(dialog);\n  \n  /* Select the default settings listview item','Load exact-path execution profiles.','appdefaults.c')
revise('  current_app = (WCHAR*) item.lParam;',"  orbis_execution_target = (const WCHAR *)item.lParam;\n  current_app = (WCHAR *)orbis_execution_target;\n  if (current_app && wcsrchr(current_app, L'\\\\')) current_app = wcsrchr(current_app, L'\\\\') + 1;",'Selection keeps full-path execution identity and basename Wine settings.','appdefaults.c')
revise('  set_window_title(dialog);\n}', '  set_window_title(dialog);\n  orbis_update_execution(dialog);\n}','Refresh the execution mode on selection.','appdefaults.c')
revise('''      if (list_contains_file(listview, filetitle))
          return;

      new_app = wcsdup(filetitle);''','''      WCHAR canonical[MAX_PATH], execution_key[MAX_PATH+64];
      if (!pw_execution_key(file,canonical,execution_key)) return;
      if (list_contains_file(listview, canonical)) return;
      new_app = wcsdup(canonical);''','Add application stores a full-path execution profile and retains Wine basename settings.','appdefaults.c')
revise('      add_listview_item(listview, new_app, new_app);', '''      add_listview_item(listview, new_app, new_app);
      set_reg_key(HKEY_CURRENT_USER, execution_key, L"ExecutablePath", canonical);
      if (orbis_added_count < ARRAY_SIZE(orbis_added)) orbis_added[orbis_added_count++] = wcsdup(filetitle);
      SendMessageW(GetParent(dialog), PSM_CHANGED, (WPARAM) dialog, 0);''','Persist newly added paths only on Apply.','appdefaults.c')
revise('    set_reg_key(config_key, keypath(L""), NULL, NULL); /* delete the section  */', '''    if (orbis_path_target())
    {
        WCHAR path[MAX_PATH], key[MAX_PATH+64];
        if (pw_execution_key(orbis_execution_target,path,key)) set_reg_key(HKEY_CURRENT_USER,key,NULL,NULL);
    }
    else set_reg_key(config_key, keypath(L""), NULL, NULL);
    orbis_execution_target = NULL;''','Remove a path profile without deleting other EXEs shared Wine settings.','appdefaults.c')
revise('    case WM_INITDIALOG:\n        init_appsheet(hDlg);', '    case WM_INITDIALOG:\n        orbis_create_execution(hDlg);\n        init_appsheet(hDlg);','Create execution controls before selection.','appdefaults.c')
revise('        case PSN_APPLY:\n            apply();', '        case PSN_APPLY:\n            orbis_create_added_keys();\n            apply();\n            RegFlushKey(HKEY_CURRENT_USER);','Apply and flush selected profiles.','appdefaults.c')
revise('''            case IDC_APP_REMOVEAPP:
              on_remove_app_click(hDlg);
              break;''','''            case IDC_APP_REMOVEAPP:
              on_remove_app_click(hDlg);
              break;
            case IDC_ORBIS_EXECUTION:
              if (HIWORD(wParam) == CBN_SELCHANGE) orbis_on_execution_change(hDlg);
              break;''','Handle execution-mode selection.','appdefaults.c')

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
          'compile_warnings':warnings,'commands':commands,
          'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'native/winecfg_execution.h',ROOT/'platform/ps4/pw_execution_mode.h')}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'winecfg':manifest['winecfg']['sha256'][:16],'revisions':len(revisions),'warnings':len(warnings)}))
