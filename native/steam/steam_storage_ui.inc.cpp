// SPDX-License-Identifier: GPL-3.0-or-later
// Included inside steam_client.cpp's namespace; uses its page, game and size helpers. The install location
// picker and the move between drives, drawn as Big Picture's modals (steam_bp.h, docs/STEAM_BIG_PICTURE.md).

// A Big Picture frame: the caller draws with a bp::Painter, the frame is published (steam_ui.h)
template <typename F>
void Present(F draw) {
  sd_canvas canvas;
  steam_ui_begin(&canvas);
  bp::Painter painter(&canvas);
  draw(painter);
  steam_ui_end(painter.summary().c_str());
}

// the game page the pickers draw behind them (set by Big Picture's game page)
bp::GameView picker_backdrop;
bool has_picker_backdrop = false;
// the default install drive's id, for its chip (Big Picture sets it; empty: none)
std::string (*picker_default_id)() = nullptr;

// A drive as the screens name it: "Internal storage" / "USB 1", its letter, and "Z: Internal" / "E: USB 1"
std::string DriveLetter(const orbisdesk::GameStorage& s) { return s.external ? s.name.substr(0, 2) : "Z:"; }
std::string DriveName(const orbisdesk::GameStorage& s) {
  return s.external ? (s.name.size() > 3 ? s.name.substr(3) : s.name) : "Internal storage";  // "E: USB 1"
}
std::string DriveShort(const orbisdesk::GameStorage& s) { return s.external ? s.name : "Z: Internal"; }

bp::Drive DriveView(const orbisdesk::GameStorage& v, std::uint64_t needed, const char* after, bool current,
                    const std::string& default_id) {
  bp::Drive d;
  d.letter = DriveLetter(v);
  d.name = DriveName(v);
  d.path = orbisdesk::StorageWindowsPath(v.library, "");
  if (d.path.empty()) d.path = v.library;
  d.side_big = v.free.ok ? Size(v.free.bytes) + " free" : "FREE SPACE UNKNOWN";
  if (v.free.ok && needed && v.free.bytes >= needed) d.side_small = Size(v.free.bytes - needed) + " " + after;
  else if (v.free.ok && needed) d.side_small = "CROSS GOES AHEAD ANYWAY", d.side_warn = true;
  else if (v.free.total_bytes) d.side_small = "OF " + Size(v.free.total_bytes) + " TOTAL";
  if (v.free.ok && v.free.total_bytes)
    d.used_permille = static_cast<int>((v.free.total_bytes - std::min(v.free.bytes, v.free.total_bytes)) * 1000 / v.free.total_bytes);
  if (current) d.chip = "CURRENT LOCATION", d.disabled = true;
  else if (v.free.ok && needed && v.free.bytes < needed) d.chip = "NOT ENOUGH SPACE", d.chip_warn = true;
  else if (!default_id.empty() && v.id == default_id) d.chip = "DEFAULT";
  return d;
}

// The drives, up and down, X picks one (prepared: a USB drive gets its "Steam Games" folder). `heading`: the
// label and the game's name; `exclude`: the library the game is on now (a move); `needed`: the bytes the game
// takes. With `install` the user can make the drive the default (*make_default).
bool ChooseStorage(const std::string& heading,const std::string& exclude,orbisdesk::GameStorage* chosen,
                   std::uint64_t needed=0,bool install=false,bool* make_default=nullptr) {
  trace_note("PWSTEAM storage menu phase=enumerate_begin");
  auto volumes=orbisdesk::GameStorages();std::size_t selected=0;bool make=false;
  trace_note("PWSTEAM storage menu phase=enumerate_done drives=%zu",volumes.size());
  const auto newline=heading.find('\n');
  const std::string label=heading.substr(0,newline),title=newline==std::string::npos?"":heading.substr(newline+1);
  const std::string default_id=picker_default_id?picker_default_id():"";
  for(;;){
    Present([&](bp::Painter& p){
      bp::PickerView view;
      view.has_backdrop=has_picker_backdrop;view.backdrop=picker_backdrop;
      view.label=label;view.title=title;
      view.subtitle=(needed?"NEEDS "+Size(needed)+" \xc2\xb7 ":std::string())+(install?"CHOOSE WHERE THE GAME LIVES":"CHOOSE THE NEW DRIVE");
      for(const auto& v:volumes)view.drives.push_back(DriveView(v,needed,install?"AFTER INSTALL":"AFTER MOVE",!exclude.empty()&&v.library==exclude,default_id));
      view.selected=static_cast<int>(selected);
      view.show_default=install;view.make_default=make;
      view.note="A USB drive gets a \"Steam Games\" folder the first time it is chosen. Shortcuts point to the drive letter shown here.";
      view.hints={{bp::kNoButton,bp::kUpDown,"CHOOSE"},{bp::kCross,"",install?"INSTALL HERE":"NEXT"}};
      if(install)view.hints.push_back({bp::kSquare,"","DEFAULT ON / OFF"});
      view.hints.push_back({bp::kTriangle,"","REFRESH DRIVES"});view.hints.push_back({bp::kCircle,"","BACK"});
      bp::DrawPicker(p,view);
    });
    unsigned key=steam_ui_wait(STEAM_UI_UP|STEAM_UI_DOWN|STEAM_UI_CROSS|STEAM_UI_CIRCLE|STEAM_UI_TRIANGLE|(install?STEAM_UI_SQUARE:0u));
    if(key==STEAM_UI_CIRCLE)return false;
    if(key==STEAM_UI_UP&&selected)--selected;
    if(key==STEAM_UI_DOWN&&selected+1<volumes.size())++selected;
    if(key==STEAM_UI_SQUARE)make=!make;
    if(key==STEAM_UI_TRIANGLE){volumes=orbisdesk::GameStorages();if(selected>=volumes.size())selected=0;}
    if(key==STEAM_UI_CROSS&&!volumes.empty()){
      if(!exclude.empty()&&volumes[selected].library==exclude)continue;
      trace_note("PWSTEAM storage menu phase=select index=%zu external=%d default=%d",selected,volumes[selected].external,make);
      *chosen=volumes[selected];std::string error;trace_note("PWSTEAM storage menu phase=prepare_begin");
      const bool prepared=orbisdesk::PrepareGameStorage(chosen,&error);trace_note("PWSTEAM storage menu phase=prepare_done ok=%d",prepared);
      if(prepared){if(make_default)*make_default=make;return true;}
      steam_ui_show(("STORAGE\n"+error+PAGE_FOOTER "O: BACK").c_str(),nullptr);steam_ui_wait(STEAM_UI_CIRCLE);volumes=orbisdesk::GameStorages();selected=0;
    }
  }
}
extern "C" int pw_hw_steam_exe_running(const char*) __attribute__((weak));
bool GameRunning(const orbisdesk::InstalledRecord& record) {
#ifndef STEAM_HOST
  if(!pw_hw_steam_exe_running)return true;
#endif
  if(!pw_hw_steam_exe_running)return false;
  for(const auto& launch:record.launches){auto slash=launch.executable.find_last_of("/\\");auto name=launch.executable.substr(slash==std::string::npos?0:slash+1);if(pw_hw_steam_exe_running(name.c_str()))return true;}
  return false;
}
void StorageMessage(const std::string& text){steam_ui_show((text+PAGE_FOOTER "O: BACK").c_str(),nullptr);steam_ui_wait(STEAM_UI_CIRCLE);}

// the source and destination as the move's modal shows them
bp::Drive MoveEnd(const std::string& root,const char* chip){
  bp::Drive d;orbisdesk::GameStorage s;
  if(orbisdesk::StorageForGame(root,&s))d.letter=DriveLetter(s),d.name=DriveName(s);
  else{auto w=orbisdesk::StorageWindowsPath(root,"");d.letter=w.size()>=2?w.substr(0,2):"?";d.name="Drive";}
  d.path=orbisdesk::StorageWindowsPath(root,"");d.chip=chip;return d;
}

// Moves an installed game to another drive. True when it moved and the user asked to play it.
bool MoveGame(const Game& game) {
  trace_note("PWSTEAM storage menu phase=move_requested");
  std::string source=GameRoot(game.app),error;orbisdesk::GameStorage target;orbisdesk::MoveProgress progress;
  const bool pending=orbisdesk::PendingGameMove(game.app);
  orbisdesk::InstalledRecord running_record;
  if(orbisdesk::ReadInstallRecord(source,&running_record)&&GameRunning(running_record)){StorageMessage("MOVE GAME\nCLOSE THIS GAME BEFORE MOVING ITS FILES.");return false;}
  if(pending){
    if(orbisdesk::FinishGameMove(game.app,&progress,&error,note)){StorageMessage("MOVE COMPLETE\n"+game.name);return false;}
    if(!orbisdesk::PendingMoveRoute(game.app,&source,&target)){StorageMessage("MOVE PENDING\nRECONNECT THE ORIGINAL AND DESTINATION DRIVES.\n"+error);return false;}
  }
  orbisdesk::InstalledRecord record;
  if(!orbisdesk::ReadInstallRecord(source,&record)||record.app!=game.app||record.format<2){StorageMessage("MOVE GAME\nVERIFY THE GAME WITH X FIRST, THEN RETRY THE MOVE.");return false;}
  if(GameRunning(record)){StorageMessage("MOVE GAME\nCLOSE THIS GAME BEFORE MOVING ITS FILES.");return false;}
  trace_note("PWSTEAM storage menu phase=source_ready pending=%d",pending);
  if(!pending&&!ChooseStorage("MOVE GAME\n"+game.name,source.substr(0,source.rfind('/')),&target,record.bytes,false))return false;
  trace_note("PWSTEAM storage menu phase=target_ready");
  trace_note("PWSTEAM storage menu phase=measure_begin");
  target.free=orbisdesk::MeasureFreeSpace(target.external?target.mount:target.library);
  trace_note("PWSTEAM storage menu phase=measure_done ok=%d",target.free.ok);
  const std::string destination=orbisdesk::StorageGameRoot(target,game.app);
  bp::MoveView move;
  move.has_backdrop=has_picker_backdrop;move.backdrop=picker_backdrop;move.title=game.name;
  move.from=MoveEnd(source,"FROM");
  move.to.letter=DriveLetter(target);move.to.name=DriveName(target);move.to.chip="TO";
  move.to.path=orbisdesk::StorageWindowsPath(destination,"");
  move.facts={{"GAME SIZE",Size(record.bytes)},
              {"FREE ON "+move.to.letter+" AFTER THE MOVE",target.free.ok?(target.free.bytes>=record.bytes?Size(target.free.bytes-record.bytes):"NOT ENOUGH SPACE"):"UNKNOWN"}};
  move.note="Files are copied, then checked, before the original is removed. The Desktop and Start shortcuts are updated to the new place. Close the game first.";
  move.buttons={target.free.ok?"MOVE GAME":"MOVE ANYWAY","CANCEL"};
  move.hints={{bp::kCross,"","MOVE"},{bp::kNoButton,bp::kLeftRight,"CHOOSE"},{bp::kCircle,"","BACK"}};
  trace_note("PWSTEAM storage menu phase=confirm_begin");
  for(;;){
    Present([&](bp::Painter& p){bp::DrawMove(p,move);});
    if(move.focus==0)trace_note("PWSTEAM storage menu phase=confirm_shown");
    const unsigned key=steam_ui_wait(STEAM_UI_CROSS|STEAM_UI_CIRCLE|STEAM_UI_LEFT|STEAM_UI_RIGHT);
    if(key==STEAM_UI_LEFT||key==STEAM_UI_RIGHT){move.focus=1-move.focus;continue;}
    if(key==STEAM_UI_CIRCLE||move.focus==1)return false;
    break;
  }
  trace_note("PWSTEAM storage menu phase=confirmed");
  std::atomic<bool> cancel{false},done{false};orbisdesk::MoveResult result;
  std::thread runner([&]{result=orbisdesk::MoveInstalledGame(game.app,source,target,cancel,!target.free.ok,&progress,[&](const std::string& dest){
    if(GameRunning(record))return false;
    orbisdesk::InstallResult installed;installed.ok=true;installed.launches=record.launches;installed.checks=record.checks;
    auto links=orbisdesk::WriteGameShortcuts(game.app,game.name,installed,dest,record.language,source,ColdClientOn(dest));return links.prefix&&!links.failed;
  },note);done=true;});
  steam_ui_take();const auto began=std::chrono::steady_clock::now();
  move.step=1;move.route=Upper(move.from.letter+" "+move.from.name)+"  \xc2\xbb  "+Upper(move.to.letter+" "+move.to.name);
  while(!done.load()){
    int phase=progress.phase.load();if((steam_ui_take()&STEAM_UI_CIRCLE)&&phase<3)cancel=true;
    auto total=progress.total.load(),copied=progress.copied.load(),verified=progress.verified.load();
    auto count=phase==2?verified:copied;auto permille=total?static_cast<int>(std::min(count,total)*1000/total):0;
    move.stage=phase;move.permille=phase>=3?1000:permille;move.percent=std::to_string(move.permille/10)+"%";
    move.detail=Size(count)+" OF "+Size(total);
    auto seconds=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now()-began).count();
    if(phase==1&&seconds>0)move.detail+="  \xc2\xb7  "+Size(copied/static_cast<std::uint64_t>(seconds))+"/S AVERAGE";
    if(phase==1||phase==2)move.detail+="  \xc2\xb7  "+Size(total>count?total-count:0)+" LEFT";
    if(phase==2)move.detail+="  \xc2\xb7  FILES "+std::to_string(progress.files_done.load())+" OF "+std::to_string(progress.files.load());
    if(phase>=3)move.detail=phase==3?"UPDATING THE GAME LOCATION...":"REMOVING THE OLD COPY...";
    move.note=cancel.load()?"Stopping. The original files are kept.":"Circle stops the move. The original stays where it was, and the game page offers to resume.";
    move.hints=phase<3?std::vector<bp::Hint>{{bp::kCircle,"","STOP MOVE"}}:std::vector<bp::Hint>{};
    Present([&](bp::Painter& p){bp::DrawMove(p,move);});std::this_thread::sleep_for(std::chrono::milliseconds(500));
  }
  runner.join();
  move.step=2;move.ok=result.ok;move.focus=0;
  if(result.ok){
    RefreshLaunchPlan(game.app);  // a SteamStub game's plan names the program in its new folder
    move.headline=result.cleanup_pending?"Game moved - cleanup pending":"Game moved";
    move.headline_sub="NOW ON "+Upper(move.to.letter+" "+move.to.name)+" \xc2\xb7 "+Size(record.bytes)+" CHECKED";
    move.facts={{"LOCATION",orbisdesk::StorageWindowsPath(result.destination,"")},{"SHORTCUTS","Desktop and Start updated"},
                {"OLD COPY",result.cleanup_pending?"Still on "+move.from.letter+": the game page finishes the cleanup":"Removed from "+move.from.letter+" "+move.from.name}};
    move.buttons={"BACK TO GAME"};
#ifdef STEAM_UI_HOSTED
    move.buttons={"PLAY","BACK TO GAME"};
#endif
  }else{
    move.headline="Move not finished";move.headline_sub=Upper(result.failure);
    move.facts={{"LOCATION",orbisdesk::StorageWindowsPath(source,"")}};
    move.buttons={"BACK TO GAME"};
  }
  move.note=result.ok?"":"The original files were kept. Move on the game page resumes it.";
  move.hints={{bp::kCross,"",move.buttons[0]},{bp::kCircle,"","BACK TO GAME"}};
  for(;;){
    Present([&](bp::Painter& p){bp::DrawMove(p,move);});
    const unsigned key=steam_ui_wait(STEAM_UI_CROSS|STEAM_UI_CIRCLE|STEAM_UI_LEFT|STEAM_UI_RIGHT);
    if(key==STEAM_UI_LEFT||key==STEAM_UI_RIGHT){const int n=static_cast<int>(move.buttons.size());move.focus=(move.focus+1)%n;
      move.hints[0].label=move.buttons[static_cast<std::size_t>(move.focus)];continue;}
    return key==STEAM_UI_CROSS&&move.buttons[static_cast<std::size_t>(move.focus)]=="PLAY";
  }
}
