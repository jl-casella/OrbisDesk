// SPDX-License-Identifier: GPL-3.0-or-later
// Steam Big Picture's screens from made-up views (no Steam, no console), as PNG snapshots to compare with the
// approved mockups, and checks that each frame says what it must. tests/test_steam_bigpicture_host.py builds it.
// Usage: steam_bp_gallery <out-dir> <fonts-dir|-> [width height]
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#include "qrcodegen.h"
#include "steam_bp.h"
#include "steam_covers.h"

using namespace bp;

static std::string out_dir;
static int width = 1280, height = 720;
static std::vector<uint32_t> pixels;
static int failures;

static void expect(const std::string& summary, const std::string& name, const char* what) {
  if (summary.find(what) == std::string::npos) {
    std::cerr << "FAIL " << name << ": no \"" << what << "\" in the frame\n" << summary << "\n";
    ++failures;
  }
}

template <typename F>
static std::string shot(const std::string& name, F draw, std::vector<const char*> wanted = {}) {
  pixels.assign(static_cast<std::size_t>(width) * height, 0);
  sd_canvas c;
  sd_begin(&c, pixels.data(), width, height, width);
  Painter p(&c);
  draw(p);
  const std::string path = out_dir + "/" + name + ".png";
  if (sd_write_png(&c, path.c_str())) {
    std::cerr << "FAIL cannot write " << path << "\n";
    ++failures;
  }
  for (auto w : wanted) expect(p.summary(), name, w);
  std::cout << "SHOT " << name << "\n";
  return p.summary();
}

static std::vector<uint32_t> art_pixels;
static sd_image art;

static Cover cover(std::uint32_t app, const char* name, bool installed = false, const char* drive = "", int progress = -1,
                   bool offline = false, bool with_art = false) {
  Cover c;
  c.app = app;
  c.name = name;
  c.installed = installed;
  c.drive = drive;
  c.progress = progress;
  c.offline = offline;
  if (with_art) c.art = &art;
  return c;
}

static Frame frame(int tab) {
  Frame f;
  f.tab = tab;
  f.clock = "21:47";
  f.download_name = "Portal 2";
  f.download_permille = 620;
  return f;
}

static GameView game_installed() {
  GameView g;
  g.frame = frame(kLibrary);
  g.cover = cover(220, "Half-Life 2", true, "E:", -1, false, true);
  g.state = kInstalled;
  g.status = "INSTALLED ON E: USB 1  \xc2\xb7  CROSS TO PLAY";
  g.buttons = {"PLAY", "VERIFY & UPDATE", "MOVE", "LANGUAGE", "UNINSTALL"};
  g.facts = {{"SIZE", "6.2 GB"}, {"LOCATION", "E:\\Steam Games\\220"}, {"STARTS", "hl2.exe \xc2\xb7 32-bit"},
             {"LANGUAGE", "English"}, {"STEAM API EMULATOR", "On  \xc2\xb7  TRIANGLE TURNS IT OFF"}};
  g.chip = "USB 1";
  g.note = "Play opens hl2.exe through the desktop, the same as its Desktop shortcut. The game takes the screen; "
           "Big Picture comes back when it closes.";
  g.hints = {{kCross, "", "PLAY"}, {kNoButton, kLeftRight, "ACTIONS"}, {kNoButton, "R1", "MOVE"},
             {kSquare, "", "LANGUAGE"}, {kTriangle, "", "EMULATOR"}, {kNoButton, "OPTIONS", "UNINSTALL"},
             {kCircle, "", "BACK"}};
  return g;
}

int main(int argc, char** argv) {
  if (argc < 3) {
    std::cerr << "usage: steam_bp_gallery <out-dir> <fonts-dir|-> [width height]\n";
    return 2;
  }
  out_dir = argv[1];
  if (argc >= 5) width = atoi(argv[3]), height = atoi(argv[4]);
  if (strcmp(argv[2], "-")) {
    const std::string fonts = argv[2];
    const int loaded = sd_fonts_load((fonts + "/tahoma.ttf").c_str(), (fonts + "/tahomabd.ttf").c_str());
    std::cout << "fonts=" << loaded << "\n";
    if (loaded) ++failures;
  }
  // a made-up "cover": diagonal stripes, so scaling and rounding show
  art_pixels.resize(160 * 240);
  for (int y = 0; y < 240; ++y)
    for (int x = 0; x < 160; ++x)
      art_pixels[static_cast<std::size_t>(y * 160 + x)] =
          0xff000000u | static_cast<uint32_t>((x * 255 / 159)) << 16 | static_cast<uint32_t>(((x + y) / 20 % 2) ? 0x60 : 0x20) << 8 |
          static_cast<uint32_t>(y * 255 / 239);
  art = {160, 240, art_pixels.data()};

  std::vector<Cover> recent = {cover(220, "Half-Life 2", true, "", -1, false, true), cover(550, "Left 4 Dead 2", true, "E:"),
                               cover(12210, "Grand Theft Auto IV", true), cover(108710, "Alan Wake", true, "E:"),
                               cover(208200, "DOOM 3", true), cover(620, "Portal 2", false, "", 620)};
  std::vector<Cover> installed = recent;
  installed.pop_back();
  installed.push_back(cover(233610, "Pro Evolution Soccer 2014", true));
  installed.push_back(cover(19980, "Prince of Persia", true, "E:"));
  installed.push_back(cover(2550, "Tony Hawk's Pro Skater", true));
  installed.push_back(cover(380, "Half-Life 2: Episode One", true));

  {
    HomeView h;
    h.frame = frame(kHome);
    h.first = recent;
    h.second = installed;
    shot("01-home", [&](Painter& p) { DrawHome(p, h); }, {"HOME", "CONTINUE PLAYING", "INSTALLED ON THIS CONSOLE", "Portal 2", "62%", "21:47"});
  }
  {
    LibraryView l;
    l.frame = frame(kLibrary);
    l.subtitle = "DUALSHOCK 4 CONNECTED \xc2\xb7 42 GAMES WITH WINDOWS CONTENT";
    l.views = {{"Installed", 6}, {"All games", 42}, {"Not installed", 36}, {"Favorites", 3}, {"Z: Internal", 4}, {"E: USB 1", 2}};
    l.separator = 4;
    l.view = 1;
    l.sort = "NAME A\xe2\x80\x93Z";
    const char* names[] = {"Alan Wake", "Borderlands 2", "Counter-Strike: Source", "DOOM 3", "Dishonored", "Fallout: New Vegas",
                           "Grand Theft Auto IV", "Half-Life 2", "Left 4 Dead 2", "Mirror's Edge", "Portal 2",
                           "Pro Evolution Soccer 2014", "Quake", "Rayman Origins"};
    for (int i = 0; i < 14; ++i) {
      Cover c = cover(1000 + i * 37, names[i], i % 3 == 0, i == 8 ? "E:" : "", i == 10 ? 620 : -1, i == 0, i == 7);
      if (i == 0) c.installed = true;
      l.games.push_back(c);
    }
    l.games[3].favorite = true;
    l.index = 7;
    shot("02-library", [&](Painter& p) { DrawLibrary(p, l); }, {"LIBRARY", "GAMES 1", "OF 14", "All games", "DRIVE OFFLINE", "SORT"});
    l.views_focus = true;
    l.view = 4;
    shot("02b-library-views", [&](Painter& p) { DrawLibrary(p, l); }, {"Z: Internal"});
  }
  {
    GameView g = game_installed();
    shot("03-game-installed", [&](Painter& p) { DrawGame(p, g); }, {"Half-Life 2", "PLAY", "VERIFY & UPDATE", "USB 1", "hl2.exe"});
    GameView n;
    n.frame = frame(kLibrary);
    n.cover = cover(620, "Portal 2");
    n.state = kNotInstalled;
    n.status = "NOT INSTALLED  \xc2\xb7  NEEDS 12.3 GB  \xc2\xb7  CROSS TO INSTALL";
    n.buttons = {"INSTALL", "LANGUAGE"};
    n.facts = {{"INSTALL SIZE", "12.3 GB"}, {"INSTALL TO", "Asks every time  \xc2\xb7  SETTINGS CHANGES IT"},
               {"LANGUAGE", "English"}, {"WINDOWS", "Windows depots found for this account"}};
    n.note = "Play opens the game through the desktop once it is installed.";
    n.hints = {{kCross, "", "INSTALL"}, {kSquare, "", "LANGUAGE"}, {kCircle, "", "BACK"}};
    shot("03b-game-not-installed", [&](Painter& p) { DrawGame(p, n); }, {"NOT INSTALLED", "INSTALL"});
    GameView r = game_installed();
    r.state = kRunning;
    r.status = "RUNNING  \xc2\xb7  STARTED FROM STEAM";
    r.buttons = {"RESUME GAME", "VERIFY & UPDATE", "MOVE", "UNINSTALL"};
    r.disabled = {false, true, true, true};
    r.note = "Close the game before verifying, moving or uninstalling it.";
    r.hints = {{kCross, "", "RESUME GAME"}, {kCircle, "", "BACK"}};
    shot("03c-game-running", [&](Painter& p) { DrawGame(p, r); }, {"RUNNING", "RESUME GAME"});
    GameView o = game_installed();
    o.state = kOffline;
    o.cover.offline = true;
    o.status = "RECONNECT E: USB 1 TO PLAY, MOVE OR UPDATE THIS GAME";
    o.buttons = {"CHECK DRIVES AGAIN"};
    o.note = "The game's files stay on the drive. Its shortcuts point to E:, so they work again once the drive is back.";
    o.note_warn = true;
    o.hints = {{kCross, "", "CHECK AGAIN"}, {kCircle, "", "BACK"}};
    shot("03d-game-offline", [&](Painter& p) { DrawGame(p, o); }, {"DRIVE OFFLINE", "CHECK DRIVES AGAIN"});
    GameView d = n;
    d.state = kDownloading;
    d.status = "DOWNLOADING  \xc2\xb7  62%  \xc2\xb7  4.1 MB/S";
    d.buttons = {"PAUSE DOWNLOAD"};
    d.progress = 620;
    shot("03e-game-downloading", [&](Painter& p) { DrawGame(p, d); }, {"DOWNLOADING", "PAUSE DOWNLOAD"});
  }
  {
    PickerView v;
    v.backdrop = game_installed();
    v.backdrop.cover = cover(620, "Portal 2");
    v.label = "INSTALL";
    v.title = "Portal 2";
    v.subtitle = "NEEDS 12.3 GB \xc2\xb7 CHOOSE WHERE THE GAME LIVES";
    Drive z{"Z:", "Internal storage", "Z:\\orbisdesk\\steam-games", "182.4 GB free", "170.1 GB AFTER INSTALL", "", false, false, false, 790, -1};
    Drive e{"E:", "USB 1", "E:\\Steam Games", "1.21 TB free", "1.20 TB AFTER INSTALL", "DEFAULT", false, false, false, 330, 20};
    Drive d{"D:", "USB 0", "D:\\Steam Games", "3.2 GB free", "CROSS INSTALLS ANYWAY", "NOT ENOUGH SPACE", true, true, false, 970, -1};
    v.drives = {z, e, d};
    v.selected = 1;
    v.show_default = true;
    v.make_default = true;
    v.note = "A USB drive gets a \"Steam Games\" folder the first time it is chosen. Shortcuts point to the drive letter shown here.";
    v.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "INSTALL HERE"}, {kSquare, "", "DEFAULT ON / OFF"},
               {kTriangle, "", "REFRESH DRIVES"}, {kCircle, "", "BACK"}};
    shot("04-install-location", [&](Painter& p) { DrawPicker(p, v); }, {"Internal storage", "USB 1", "NOT ENOUGH SPACE", "Install here every time"});
  }
  {
    MoveView m;
    m.backdrop = game_installed();
    m.title = "Half-Life 2";
    m.from = {"E:", "USB 1", "E:\\Steam Games\\220", "", "", "FROM", false, false, false, -1, -1};
    m.to = {"Z:", "Internal storage", "Z:\\orbisdesk\\steam-games\\220", "", "", "TO", false, false, false, -1, -1};
    m.facts = {{"GAME SIZE", "6.2 GB"}, {"FREE ON Z: AFTER THE MOVE", "176.2 GB"}};
    m.note = "Files are copied, then checked, before the original is removed. The Desktop and Start shortcuts are updated to the new place. Close the game first.";
    m.buttons = {"MOVE GAME", "CANCEL"};
    m.hints = {{kCross, "", "MOVE"}, {kCircle, "", "BACK"}};
    shot("05-move-confirm", [&](Painter& p) { DrawMove(p, m); }, {"MOVE GAME", "FREE ON Z: AFTER THE MOVE"});
    m.step = 1;
    m.stage = 1;
    m.permille = 480;
    m.percent = "48%";
    m.route = "E: USB 1  \xc2\xbb  Z: INTERNAL STORAGE";
    m.detail = "3.0 GB OF 6.2 GB  \xc2\xb7  38.4 MB/S AVERAGE  \xc2\xb7  3.2 GB LEFT";
    m.note = "Circle stops the move. The original stays where it was, and the game page offers to resume.";
    m.hints = {{kCircle, "", "STOP MOVE"}};
    shot("05b-move-progress", [&](Painter& p) { DrawMove(p, m); }, {"48%", "COPY"});
    m.step = 2;
    m.headline = "Game moved";
    m.headline_sub = "NOW ON Z: INTERNAL STORAGE \xc2\xb7 6.2 GB CHECKED";
    m.facts = {{"LOCATION", "Z:\\orbisdesk\\steam-games\\220"}, {"SHORTCUTS", "Desktop and Start updated"}, {"OLD COPY", "Removed from E: USB 1"}};
    m.note = "";
    m.buttons = {"PLAY", "BACK TO GAME"};
    m.hints = {{kCross, "", "PLAY"}, {kCircle, "", "BACK TO GAME"}};
    shot("05c-move-done", [&](Painter& p) { DrawMove(p, m); }, {"Game moved", "Desktop and Start updated"});
  }
  {
    DownloadsView d;
    d.frame = frame(kDownloads);
    d.subtitle = "1 ACTIVE \xc2\xb7 1 PAUSED";
    d.active = true;
    d.current.cover = cover(620, "Portal 2");
    d.current.name = "Portal 2";
    d.current.detail = "TO E: USB 1 \xc2\xb7 E:\\Steam Games\\620";
    d.permille = 620;
    d.percent_line = "62%  \xc2\xb7  7.6 GB OF 12.3 GB";
    d.speed_line = "4.1 MB/S  \xc2\xb7  ABOUT 19 MIN LEFT";
    d.paused = {{cover(208200, "DOOM 3"), "DOOM 3", "1.2 GB OF 4.4 GB \xc2\xb7 Z: INTERNAL", "CROSS RESUMES WHERE IT STOPPED"}};
    d.finished = {{cover(220, "Half-Life 2"), "Half-Life 2", "INSTALLED ON E: USB 1 \xc2\xb7 SHORTCUTS ON THE DESKTOP AND IN START", ""}};
    shot("06-downloads", [&](Painter& p) { DrawDownloads(p, d); }, {"DOWNLOADING", "PAUSED", "FINISHED THIS SESSION", "4.1 MB/S"});
  }
  {
    StorageView s;
    s.frame = frame(kStorage);
    s.subtitle = "3 DRIVES \xc2\xb7 6 GAMES INSTALLED";
    s.drives = {{"Z: Internal", 4}, {"E: USB 1", 2}, {"D: USB 0", 0}};
    s.drive = 1;
    s.name = "USB 1";
    s.chip = "DEFAULT INSTALL LOCATION";
    s.paths = "E:\\Steam Games \xc2\xb7 /mnt/usb1/Steam Games";
    s.steam_permille = 12;
    s.other_permille = 310;
    s.steam_label = "STEAM GAMES 21.5 GB";
    s.other_label = "OTHER FILES 590 GB";
    s.free_label = "1.21 TB FREE OF 1.82 TB";
    s.games = {{"Half-Life 2", "6.2 GB"}, {"Left 4 Dead 2", "15.3 GB"}};
    s.games_focus = true;
    s.note = "Unplugging this drive marks its games DRIVE OFFLINE until it is back. Nothing is forgotten.";
    shot("07-storage", [&](Painter& p) { DrawStorage(p, s); }, {"STORAGE", "DEFAULT INSTALL LOCATION", "GAMES ON THIS DRIVE", "Left 4 Dead 2"});
  }
  {
    SettingsView s;
    s.frame = frame(kSettings);
    s.subtitle = "SIGNED IN AS orbis_player";
    s.rows = {{"Start OrbisDesk in", "STEAM BIG PICTURE", true, false}, {"Install location", "E: USB 1", true, false},
              {"Steam language", "English", false, false}, {"Exit to desktop", "CROSS", false, true},
              {"Steam account", "orbis_player", false, false}};
    s.lead = "OrbisDesk opens Steam Big Picture when it starts.";
    s.detail = "The desktop is one step away under Exit to desktop. If Big Picture can't open, OrbisDesk starts the desktop instead.";
    s.saved = "Applies from the next start. Saved on the console in /data/orbisdesk/startup.ini.";
    shot("08-settings", [&](Painter& p) { DrawSettings(p, s); }, {"Start OrbisDesk in", "STEAM BIG PICTURE", "startup.ini"});
  }
  {
    MenuView m;
    m.home.frame = frame(kHome);
    m.home.frame.power_focus = true;
    m.home.first = recent;
    m.home.second = installed;
    m.home.shelf = -1;
    m.label = "POWER";
    m.rows = {"Exit to desktop", "Close OrbisDesk", "Cancel"};
    m.icons = {SD_ICON_MONITOR, SD_ICON_POWER, -1};
    m.note = "Close OrbisDesk goes back to the PS4 home screen.";
    m.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "SELECT"}, {kCircle, "", "CLOSE"}};
    shot("09-power", [&](Painter& p) { DrawMenu(p, m); }, {"POWER", "Exit to desktop", "Close OrbisDesk"});
    m.right_panel = false;
    m.label = "EXIT TO DESKTOP";
    m.title = "Left 4 Dead 2 is still running";
    m.text = "OrbisDesk restarts into the desktop, which closes the game. Progress the game hasn't saved is lost.";
    m.rows = {"CLOSE THE GAME AND EXIT TO DESKTOP", "RETURN TO THE GAME", "CANCEL"};
    m.selected = 1;
    m.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "CONFIRM"}, {kCircle, "", "CANCEL"}};
    shot("09b-exit-game-running", [&](Painter& p) { DrawMenu(p, m); }, {"is still running", "RETURN TO THE GAME"});
  }
  {
    MessageView m;
    m.has_backdrop = true;
    m.backdrop = game_installed();
    m.label = "UNINSTALL";
    m.title = "Half-Life 2";
    m.text = "This deletes the whole folder and the shortcuts of the game on the Desktop and in Start. It cannot be undone.";
    m.warn = true;
    m.buttons = {"UNINSTALL", "KEEP IT"};
    m.focus = 1;
    m.hints = {{kCross, "", "UNINSTALL"}, {kCircle, "", "KEEP IT"}};
    shot("10-message", [&](Painter& p) { DrawMessage(p, m); }, {"UNINSTALL", "KEEP IT"});
  }
  shot("11-splash", [&](Painter& p) { DrawSplash(p, "OPENING STEAM BIG PICTURE"); }, {"ORBISDESK", "OPENING STEAM BIG PICTURE"});
  {
    const char* page =
        "INSTALL\nPortal 2\nINSTALLED SIZE: 12.3 GB\nDOWNLOAD: UP TO 11.0 GB\nFREE ON SELECTED STORAGE: 1.2 TB\n"
        "FOLDER: /mnt/usb1/Steam Games/620\n\x03THE EXECUTABLE COULD NOT BE CHECKED FOR STEAMSTUB BEFORE THE DOWNLOAD: "
        "NETWORK.\nLANGUAGE: ESPA\xc3\x91OL - ESPA\xc3\x91" "A\n\x02X: INSTALL     O: BACK";
    shot("12-text-page", [&](Painter&) {}, {});
    pixels.assign(static_cast<std::size_t>(width) * height, 0);
    sd_canvas c;
    sd_begin(&c, pixels.data(), width, height, width);
    steam_bp_draw_page(&c, page, nullptr, 0);
    sd_write_png(&c, (out_dir + "/12-text-page.png").c_str());
    const char* list =
        "LANGUAGE\nPortal 2\nINSTALLED NOW: ENGLISH\n\nENGLISH - NOW\n\x01" "ESPA\xc3\x91OL - ESPA\xc3\x91" "A\nFRAN\xc3\x87" "AIS\n"
        "\x02" "2 OF 3\nUP AND DOWN: CHOOSE   X: INSTALL THIS LANGUAGE   O: BACK";
    steam_bp_draw_page(&c, list, nullptr, 0);
    sd_write_png(&c, (out_dir + "/12b-text-list.png").c_str());
    uint8_t temp[qrcodegen_BUFFER_LEN_MAX], code[qrcodegen_BUFFER_LEN_MAX];
    assert(qrcodegen_encodeText("https://s.team/q/1/1234567890123456789", temp, code, qrcodegen_Ecc_MEDIUM,
                                qrcodegen_VERSION_MIN, qrcodegen_VERSION_MAX, qrcodegen_Mask_AUTO, 1));
    const int size = qrcodegen_getSize(code);
    std::vector<uint8_t> modules(static_cast<std::size_t>(size * size));
    for (int y = 0; y < size; ++y)
      for (int x = 0; x < size; ++x) modules[static_cast<std::size_t>(y * size + x)] = qrcodegen_getModule(code, x, y);
    steam_bp_draw_page(&c,
                       "SIGN IN TO STEAM\nON YOUR PHONE OPEN THE STEAM APP: STEAM GUARD - SCAN A QR CODE.\n"
                       "SCAN THIS CODE AND CONFIRM THE SIGN-IN ON THE PHONE.\nTHE CODE RENEWS ITSELF WHILE THIS SCREEN IS OPEN."
                       "\n\x02O: CANCEL",
                       modules.data(), size);
    sd_write_png(&c, (out_dir + "/12c-qr.png").c_str());
  }
  {
    // non-Steam games: the library's add tile and chip, then the add flow's screens
    LibraryView l;
    l.frame = frame(kLibrary);
    l.subtitle = "48 GAMES WITH WINDOWS CONTENT \xc2\xb7 48 OWNED \xc2\xb7 3 NON-STEAM";
    l.views = {{"Installed", 11}, {"All games", 51}, {"Not installed", 40}, {"Favorites", 0}, {"Non-Steam", 3}, {"E: USB 1", 8}};
    l.separator = 5;
    l.view = 4;
    l.sort = "NAME A\xe2\x80\x93Z";
    const char* names[] = {"Grand Theft Auto IV", "Need for Speed\xe2\x84\xa2 Most Wanted", "Worms Armageddon"};
    for (int i = 0; i < 3; ++i) {
      Cover c = cover(0x80000010u + static_cast<std::uint32_t>(i) * 77, names[i], true, i == 1 ? "E:" : "");
      c.non_steam = true;
      l.games.push_back(c);
    }
    l.add_tile = true;
    l.index = 3;
    shot("15-nonsteam-library", [&](Painter& p) { DrawLibrary(p, l); },
         {"Non-Steam", "ADD A", "NON-STEAM", "GAME", "ADD A GAME", "GAMES 1"});
    l.index = 1;
    shot("15b-nonsteam-library-game", [&](Painter& p) { DrawLibrary(p, l); }, {"DETAILS", "Worms Armageddon"});

    FoundView f;
    f.subtitle = "FROM DESKTOP AND START SHORTCUTS, AND GAME FOLDERS ON C: AND THE USB DRIVES \xc2\xb7 STEAM GAMES LEFT OUT";
    f.rows = {{"Grand Theft Auto IV", "C:\\Program Files (x86)\\Rockstar Games\\GTAIV\\LaunchGTAIV.exe", "x86", true, true},
              {"Need for Speed\xe2\x84\xa2 Most Wanted", "E:\\Games\\NFS Most Wanted\\speed.exe", "x86", false, true},
              {"Worms Armageddon", "E:\\Games\\Worms Armageddon\\WA.exe", "x86", false, false},
              {"Doom 3 BFG", "C:\\Games\\Doom3BFG\\Doom3BFG.exe", "x64", true, false},
              {"Fifth", "C:\\Games\\Fifth\\fifth.exe", "x86", false, false}};
    f.selected = 4;
    f.note = "Setup, uninstall, update and crash-report programs are left out. A game already in the library is not listed again.";
    f.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "TICK"}, {kSquare, "", "BROWSE"},
               {kNoButton, "OPTIONS", "ADD TICKED"}, {kCircle, "", "CANCEL"}};
    shot("16-nonsteam-found", [&](Painter& p) { DrawFound(p, f); },
         {"Found on this console", "Fifth", "ADD 2 GAMES", "BROWSE FOR AN EXE", "SHORTCUT", "64-BIT"});
    f.rows.clear();
    f.empty = "NO GAMES WERE FOUND IN SHORTCUTS OR GAME FOLDERS. SQUARE BROWSES FOR AN EXE.";
    shot("16b-nonsteam-found-empty", [&](Painter& p) { DrawFound(p, f); }, {"NO GAMES WERE FOUND", "ADD 0 GAMES"});

    BrowseView b;
    b.places = {"C: Windows", "Z: Internal", "D: USB 0", "E: USB 1", "Desktop"};
    b.place = 3;
    b.path = "E:\\Games\\NFS Most Wanted";
    b.entries = {{"..", "UP ONE FOLDER", 0}, {"CARS", "", 1}, {"TRACKS", "", 1},
                 {"speed.exe", "Need for Speed\xe2\x84\xa2 Most Wanted \xc2\xb7 32-BIT \xc2\xb7 5.8 MB", 2},
                 {"NFSMWConfig.exe", "32-BIT \xc2\xb7 1.1 MB", 2}};
    b.selected = 3;
    b.note = "Only folders and .exe files are shown. The name on the right is the one the exe carries.";
    b.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "OPEN / SELECT"}, {kNoButton, kLeftRight, "DRIVES"},
               {kTriangle, "", "UP ONE FOLDER"}, {kCircle, "", "BACK"}};
    shot("17-nonsteam-browse", [&](Painter& p) { DrawBrowse(p, b); },
         {"BROWSE FOR AN EXE", "E:\\Games\\NFS Most Wanted", "speed.exe", "UP ONE FOLDER", "E: USB 1"});

    DetailsView d;
    d.cover = cover(0x80000011u, "Need for Speed Most Wanted");
    d.cover.non_steam = true;
    d.title = "Need for Speed\xe2\x84\xa2 Most Wanted";
    d.rows = {{"Name", "Need for Speed\xe2\x84\xa2 Most Wanted", false, false},
              {"Program", "E:\\Games\\NFS Most Wanted\\speed.exe", false, true},
              {"Start in", "E:\\Games\\NFS Most Wanted", false, true},
              {"Launch options", "NONE", false, true},
              {"Cover", "FROM STEAM'S STORE", false, false}};
    d.buttons = {"ADD TO LIBRARY", "CANCEL"};
    d.selected = 0;
    d.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "CHANGE"}, {kNoButton, "OPTIONS", "ADD TO LIBRARY"},
               {kCircle, "", "BACK"}};
    shot("18-nonsteam-details", [&](Painter& p) { DrawDetails(p, d); },
         {"Program", "Launch options", "ADD TO LIBRARY", "FROM STEAM'S STORE"});

    KeyboardView k;
    k.cover = d.cover;
    k.field = "NAME";
    k.text = "Need for Speed Most Wanted";
    k.row = 2;
    k.col = 2;
    k.hints = {{kCross, "", "TYPE"}, {kSquare, "", "DELETE"}, {kTriangle, "", "SPACE"}, {kNoButton, "OPTIONS", "DONE"},
               {kCircle, "", "CANCEL"}};
    shot("19-nonsteam-keyboard", [&](Painter& p) { DrawKeyboard(p, k); }, {"NAME", "SHIFT", "SPACE", "DELETE", "DONE"});
    k.shift = true;
    k.row = 4;
    k.col = 8;
    shot("19b-nonsteam-keyboard-shift", [&](Painter& p) { DrawKeyboard(p, k); }, {"Q", "DONE"});
    std::string ch;
    const bool keys = KeyAt(1, 0, false, &ch) == kKeyChar && ch == "q" && KeyAt(1, 0, true, &ch) == kKeyChar && ch == "Q" &&
                      KeyAt(4, 1, false, &ch) == kKeyShift && KeyAt(4, 3, false, &ch) == kKeySpace &&
                      KeyAt(4, 6, false, &ch) == kKeyDelete && KeyAt(4, 9, false, &ch) == kKeyDone;
    std::cout << (keys ? "PASS" : "FAIL") << " keyboard keys\n";
    if (!keys) ++failures;

    CoverChoiceView v;
    v.title = "Need for Speed\xe2\x84\xa2 Most Wanted";
    CoverChoice store1{cover(1262560, "Need for Speed Most Wanted", false, "", -1, false, true), "FROM STEAM'S STORE",
                       "BEST MATCH FOR THE NAME"};
    CoverChoice store2{cover(17430, "Need for Speed Undercover"), "OTHER MATCH", "2 OF 3"};
    CoverChoice file{cover(0x80000011u, "Need for Speed Most Wanted"), "IMAGE ON THE CONSOLE", "A .JPG OR .PNG YOU CHOOSE"};
    CoverChoice plain{cover(0x80000011u, "Need for Speed Most Wanted"), "PLAIN TILE", "COLOUR AND INITIALS"};
    v.choices = {store1, store2, file, plain};
    v.note = "The store's art is fetched as Steam games' covers are and kept on the console. Only the picture comes from the store.";
    v.hints = {{kNoButton, kLeftRight, "CHOOSE"}, {kCross, "", "USE THIS COVER"}, {kCircle, "", "BACK"}};
    shot("20-nonsteam-cover", [&](Painter& p) { DrawCoverChoice(p, v); },
         {"COVER", "FROM STEAM'S STORE", "IMAGE ON THE CONSOLE", "PLAIN TILE", "USE THIS COVER"});
  }
  {
    // full emulation for a SteamStub game: the page with it on, and Triangle's menu
    GameView g = game_installed();
    g.cover = cover(33230, "Assassin's Creed II", true, "E:");
    g.status = "INSTALLED ON USB 1  \xc2\xb7  CROSS TO PLAY";
    g.status_chip = "COLDCLIENT \xc2\xb7 EXPERIMENTAL";
    g.facts = {{"SIZE", "7.9 GB"}, {"LOCATION", "E:\\Steam Games\\33230"},
               {"STARTS", "AssassinsCreedIIGame.exe \xc2\xb7 32-bit \xc2\xb7 through the ColdClient loader"},
               {"STEAM EMULATION", "Full (ColdClient)  \xc2\xb7  TRIANGLE CHANGES IT"}, {"LAST RUN", "Closed after 6 s"}};
    g.note = "Play starts the game through gbe_fork's ColdClient loader, so SteamStub finds a Steam client. "
             "Experimental: it may not start, and other launchers this game needs are not provided.";
    g.hints = {{kCross, "", "PLAY"}, {kNoButton, kLeftRight, "ACTIONS"}, {kTriangle, "", "STEAM EMULATION"}, {kCircle, "", "BACK"}};
    shot("21-coldclient-page", [&](Painter& p) { DrawGame(p, g); },
         {"Assassin's Creed II", "COLDCLIENT", "EXPERIMENTAL", "STEAM EMULATION", "LAST RUN"});
    ChoiceView m;
    m.backdrop = g;
    m.label = "STEAM EMULATION";
    m.title = "Assassin's Creed II";
    m.rows = {{"Off", "PLAY STAYS OFF", false, false, {}},
              {"Steam API emulator", "NOT USED BY THIS GAME", true, false, {}},
              {"Full emulation (ColdClient)", "EXPERIMENTAL", false, true, {}}};
    m.selected = 2;
    m.text = "Full emulation starts the game through gbe_fork's ColdClient loader with its own steamclient.dll, so "
             "SteamStub finds a Steam client. It is not Steam: online features, achievements and other launchers "
             "(Ubisoft, Rockstar, EA) are not provided. The game's files are not changed.";
    m.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "USE"}, {kCircle, "", "BACK"}};
    shot("22-coldclient-menu", [&](Painter& p) { DrawChoice(p, m); },
         {"STEAM EMULATION", "Off", "Steam API emulator", "Full emulation (ColdClient)", "EXPERIMENTAL", "It is not Steam"});
    // launch modes (the approved review of 2026-11-26): marks at the row's end, a dim reason on a mode that can't apply
    ChoiceView lm;
    lm.backdrop = g;
    lm.label = "LAUNCH MODE";
    lm.title = "Portal 2";
    lm.rows = {{"Direct", "THE GAME'S OWN STEAM FILES", false, false, {}},
               {"Steam API emulator", "", false, false, {{"RECOMMENDED", 0}, {"CURRENT", 1}}},
               {"Full emulation (ColdClient)", "", false, false, {{"EXPERIMENTAL", 2}}},
               {"ColdClient + SteamStub compatibility", "ONLY FOR STEAMSTUB GAMES", true, false, {}}};
    lm.selected = 1;
    lm.text = "Steam API emulator: gbe_fork's steam_api.dll in place of the game's, so it starts without a Steam client. "
              "Recommended for this game. Play, its Desktop and Start shortcuts and Steam links use the mode chosen here.";
    lm.hints = {{kNoButton, kUpDown, "CHOOSE"}, {kCross, "", "USE"}, {kCircle, "", "BACK"}};
    shot("23-launch-mode-menu", [&](Painter& p) { DrawChoice(p, lm); },
         {"LAUNCH MODE", "Direct", "RECOMMENDED", "CURRENT", "EXPERIMENTAL", "ONLY FOR STEAMSTUB GAMES"});
    ChoiceView ls = lm;
    ls.title = "Alice: Madness Returns";
    ls.rows = {{"Direct", "STEAMSTUB: PLAY STAYS OFF", false, true, {}},
               {"Steam API emulator", "THE GAME HAS NO STEAM_API.DLL", true, false, {}},
               {"Full emulation (ColdClient)", "", false, false, {{"EXPERIMENTAL", 2}}},
               {"ColdClient + SteamStub compatibility", "", false, false, {{"RECOMMENDED", 0}, {"CURRENT", 1}, {"EXPERIMENTAL", 2}}}};
    ls.selected = 3;
    shot("24-launch-mode-steamstub", [&](Painter& p) { DrawChoice(p, ls); },
         {"STEAMSTUB: PLAY STAYS OFF", "THE GAME HAS NO STEAM_API.DLL", "RECOMMENDED"});
  }
  {
    // covers: a PNG written here, decoded and box-filtered to 144x216, saved and read back as Big Picture does
    std::vector<uint32_t> source(300 * 450);
    for (int y = 0; y < 450; ++y)
      for (int x = 0; x < 300; ++x) source[static_cast<std::size_t>(y * 300 + x)] = y < 225 ? 0xffff0000u : 0xff0000ffu;
    sd_canvas c;
    sd_begin(&c, source.data(), 300, 450, 300);
    const std::string png = out_dir + "/cover-source.png";
    std::vector<uint32_t> pixels, loaded;
    FILE* f = nullptr;
    std::vector<uint8_t> bytes;
    if (!sd_write_png(&c, png.c_str()) && (f = fopen(png.c_str(), "rb"))) {
      int ch;
      while ((ch = fgetc(f)) != EOF) bytes.push_back(static_cast<uint8_t>(ch));
      fclose(f);
    }
    const bool decoded = orbisdesk::Covers::Decode(bytes.data(), bytes.size(), &pixels);
    const bool saved = decoded && orbisdesk::Covers::Save(out_dir + "/42.cov", pixels);
    const bool read = saved && orbisdesk::Covers::Load(out_dir + "/42.cov", &loaded);
    const bool ok = read && loaded == pixels && pixels.size() == 144u * 216u && pixels[10 * 144 + 10] == 0xffff0000u &&
                    pixels[200 * 144 + 10] == 0xff0000ffu;
    const bool garbage = !orbisdesk::Covers::Decode(reinterpret_cast<const uint8_t*>("not an image"), 12, &pixels);
    std::cout << (ok && garbage ? "PASS" : "FAIL") << " cover decode/save/load\n";
    if (!ok || !garbage) ++failures;

    // a landscape header (2.14:1, red over blue halves left/right) letterboxed into the portrait tile: the
    // image across the full width a little above the middle, a darker fill above and below
    std::vector<uint32_t> wide(460 * 215);
    for (int y = 0; y < 215; ++y)
      for (int x = 0; x < 460; ++x) wide[static_cast<std::size_t>(y * 460 + x)] = x < 230 ? 0xffff0000u : 0xff0000ffu;
    sd_begin(&c, wide.data(), 460, 215, 460);
    const std::string header = out_dir + "/cover-header.png";
    bytes.clear();
    if (!sd_write_png(&c, header.c_str()) && (f = fopen(header.c_str(), "rb"))) {
      int ch;
      while ((ch = fgetc(f)) != EOF) bytes.push_back(static_cast<uint8_t>(ch));
      fclose(f);
    }
    std::vector<uint32_t> tile;
    const bool boxed = orbisdesk::Covers::DecodeLandscape(bytes.data(), bytes.size(), &tile) && tile.size() == 144u * 216u;
    const int top = (216 - 144 * 215 / 460) * 2 / 5;
    auto red = [](uint32_t p) { return (p >> 16) & 255; };
    const bool middle = boxed && tile[static_cast<std::size_t>((top + 30) * 144 + 10)] == 0xffff0000u &&
                        tile[static_cast<std::size_t>((top + 30) * 144 + 130)] == 0xff0000ffu;
    const bool dark = boxed && red(tile[5 * 144 + 10]) < 140 && red(tile[210 * 144 + 10]) < 140 && (tile[5 * 144 + 10] >> 24) == 255;
    if (boxed) {
      sd_begin(&c, tile.data(), 144, 216, 144);
      sd_write_png(&c, (out_dir + "/cover-header-tile.png").c_str());
    }
    std::cout << (boxed && middle && dark ? "PASS" : "FAIL") << " landscape cover letterbox\n";
    if (!boxed || !middle || !dark) ++failures;

    // the store's answer: a renamed cover, a hashed folder, an app without a library cover, an unknown app,
    // and a path that tries to leave Steam's asset host
    const std::string reply =
        "{\"response\":{\"store_items\":["
        "{\"item_type\":0,\"id\":13600,\"success\":1,\"appid\":13600,\"assets\":{\"asset_url_format\":"
        "\"steam/apps/13600/${FILENAME}?t=1720535333\",\"header\":\"header.jpg\",\"library_capsule\":\"portrait.png\"}},"
        "{\"id\":32430,\"success\":1,\"type\":0,\"name\":\"STAR WARS - The Force Unleashed\",\"assets\":{\"asset_url_format\":\"steam/apps/32430/${FILENAME}?t=1\","
        "\"library_capsule\":\"819e/library_600x900.jpg\",\"header\":\"header.jpg\"}},"
        "{\"id\":500,\"success\":1,\"type\":4,\"assets\":{\"asset_url_format\":\"steam/apps/500/${FILENAME}\",\"header\":\"header.jpg\"}},"
        "{\"id\":1,\"success\":15},"
        "{\"id\":7,\"success\":1,\"assets\":{\"asset_url_format\":\"https://evil.example/${FILENAME}\",\"library_capsule\":\"a.jpg\"}},"
        "{\"id\":8,\"success\":1,\"assets\":{\"asset_url_format\":\"steam/apps/8/${FILENAME}\",\"library_capsule\":\"../../x.jpg\"}}]}}";
    const auto art = orbisdesk::Covers::ParseStoreItems(reply);
    const std::string host = "https://shared.akamai.steamstatic.com/store_item_assets/";
    const bool parsed =
        art.size() == 4 && art.count(13600) &&
        art.at(13600).library == host + "steam/apps/13600/portrait.png?t=1720535333" &&
        art.at(13600).header == host + "steam/apps/13600/header.jpg?t=1720535333" &&
        art.at(32430).library == host + "steam/apps/32430/819e/library_600x900.jpg?t=1" && art.count(500) &&
        art.at(500).library.empty() && art.at(500).header == host + "steam/apps/500/header.jpg" && !art.count(1) &&
        !art.count(7) && art.count(8) && art.at(8).library.empty() && art.at(32430).type == 0 &&
        art.at(32430).name == "STAR WARS - The Force Unleashed" && art.at(500).type == 4 && art.at(13600).type == -1 && orbisdesk::Covers::ParseStoreItems("not json").empty();
    const std::string items = orbisdesk::Covers::StoreItemsUrl({13600, 32430});
    const bool url = items.rfind("https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json=", 0) == 0 &&
                     items.find("%7B%22appid%22%3A13600%7D%2C%7B%22appid%22%3A32430%7D") != std::string::npos &&
                     items.find("include_assets%22%3Atrue") != std::string::npos;
    std::cout << (parsed && url ? "PASS" : "FAIL") << " store art lookup\n";
    if (!parsed || !url) ++failures;
  }
  std::cout << (failures ? "FAIL" : "PASS") << " gallery " << width << "x" << height << "\n";
  return failures ? 1 : 0;
}
