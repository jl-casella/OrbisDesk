// SPDX-License-Identifier: GPL-3.0-or-later
// Steam Big Picture's screens (docs/STEAM_BIG_PICTURE.md): what each one shows, as plain data, and the code
// that draws it on a steam_draw.h canvas. Nothing here talks to Steam or the console: the client
// (steam_client.cpp) fills the views, and tests/test_steam_bigpicture_host.py draws every screen from
// made-up views into PNG snapshots. Layout in design units of a 1920x1080 screen (the approved mockups).
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "steam_draw.h"

namespace bp {

// The palette (accent: OrbisDesk's logo blue)
constexpr std::uint32_t kTop = 0xff141a21, kBottom = 0xff0b0e12, kBg = 0xff0c1015, kPanel = 0xff121821,
                        kRaise = 0xff1f2833, kInk = 0xffeef3f8, kDim = 0xff97a4b2, kAccent = 0xff3a9cf0,
                        kHi = 0xff8fe0ff, kWarn = 0xffffc477, kErr = 0xffff9c84, kOk = 0xff7fd8a6, kDark = 0xff05070a,
                        kMuted = 0xff5d6b7a;

enum Tab { kHome, kLibrary, kDownloads, kStorage, kSettings, kTabs };
enum Button { kNoButton, kCross, kCircle, kTriangle, kSquare };

// Hint keys drawn as arrows (Tahoma has no arrow characters)
inline const char kUpDown[] = "\x01UD";
inline const char kLeftRight[] = "\x01LR";

struct Hint {
  int button = kNoButton;  // a pad glyph, or kNoButton for `key` in a chip
  std::string key;
  std::string label;
};

// Everything drawn as text is also kept, in order, as the frame's summary: what the host prints and the
// tests read (never logged on the console).
class Painter {
 public:
  explicit Painter(sd_canvas* canvas) : c_(canvas) {}
  sd_canvas* canvas() { return c_; }
  const std::string& summary() const { return summary_; }
  void Note(const std::string& text) { summary_ += text + "\n"; }

  void Background();
  float Text(float x, float y, float size, std::uint32_t color, const std::string& text, bool bold = false);
  float TextFit(float x, float y, float size, std::uint32_t color, const std::string& text, float width,
                bool bold = false);
  float TextRight(float right, float y, float size, std::uint32_t color, const std::string& text, bool bold = false);
  int Wrap(float x, float y, float width, float size, float line, std::uint32_t color, const std::string& text,
           int max_lines = 0, bool bold = false);
  float Width(float size, const std::string& text, bool bold = false) const;
  void Panel(float x, float y, float w, float h, float radius = 16) { sd_round(c_, x, y, w, h, radius, kPanel); }
  void Scrim(std::uint32_t color = 0xb8030508) { sd_rect(c_, 0, 0, 1920, 1080, color); }
  void Modal(float x, float y, float w, float h);
  // a row: state 0 plain, 1 selected, 2 soft focus, 3 disabled
  void Row(float x, float y, float w, float h, const std::string& label, const std::string& value, int state,
           std::uint32_t value_color = kAccent, float size = 20);
  // returns the width; focus draws the double ring
  float ButtonAt(float x, float y, const std::string& label, bool primary, bool focus, bool disabled, int icon = -1);
  void Bar(float x, float y, float w, float h, int permille, std::uint32_t color = kAccent, std::uint32_t back = kBg);
  void Chip(float x, float y, const std::string& text, bool warn = false);
  // a mark on a row: kind 0 filled accent (RECOMMENDED), 1 green (CURRENT), 2 warning (EXPERIMENTAL)
  void Badge(float x, float y, const std::string& text, int kind);
  float ChipWidth(const std::string& text) const;
  void Glyph(float x, float y, int button, float size = 30);
  float HintBar(const std::vector<Hint>& hints, float x = 96, float y = 950);
  void TopBar(int tab, bool power_focus, const std::string& download_name, int download_permille,
              const std::string& clock, const std::string& brand);
  void Check(float x, float y, float size);

 private:
  sd_canvas* c_;
  std::string summary_;
};

// a game's cover: art when cached, else the placeholder (a gradient from the app id, initials, the name)
struct Cover {
  std::uint32_t app = 0;
  std::string name;
  const sd_image* art = nullptr;
  bool installed = false;
  bool offline = false;
  std::string drive;       // "E:" for a game on a USB drive
  int progress = -1;       // permille of a running download
  bool favorite = false;
  bool non_steam = false;  // a game added from the console: the NON-STEAM chip
};
void DrawCover(Painter& p, const Cover& cover, float x, float y, float w, float h, bool focus, bool foot = true);

struct Frame {  // what every tab shows above and below its own content
  int tab = kHome;
  bool power_focus = false;
  std::string download_name;
  int download_permille = -1;
  std::string clock;
  std::string brand = "ORBISDESK \xc2\xb7 STEAM";
};

struct HomeView {
  Frame frame;
  std::string first_title = "CONTINUE PLAYING", second_title = "INSTALLED ON THIS CONSOLE";
  std::vector<Cover> first, second;
  int shelf = 0, index = 0;
  std::string empty_second;  // shown when `second` is empty
  bool big_picture = false;
  bool hints = true;  // off behind a modal
};
void DrawHome(Painter& p, const HomeView& view);

struct LibraryView {
  Frame frame;
  std::string subtitle;
  std::vector<std::pair<std::string, int>> views;  // name, count
  int separator = -1;  // a rule above this view (the first drive)
  int view = 1;
  bool views_focus = false;
  std::vector<Cover> games;  // the view's games, in order
  int index = 0;             // the focused game
  std::string sort;
  std::string empty;
  bool add_tile = false;  // "Add a non-Steam game" after the games: index == games.size() focuses it
};
void DrawLibrary(Painter& p, const LibraryView& view);

enum GameState { kInstalled, kNotInstalled, kRunning, kOffline, kMovePending, kDownloading, kPaused };
struct GameView {
  Frame frame;
  Cover cover;
  GameState state = kNotInstalled;
  std::string status;  // the line under the name
  std::vector<std::string> buttons;
  std::vector<bool> disabled;
  int focus = 0;
  std::vector<std::pair<std::string, std::string>> facts;  // label, value
  std::string chip;  // after the LOCATION value
  std::string status_chip;  // a warning chip after the status line ("COLDCLIENT \xc2\xb7 EXPERIMENTAL")
  std::string note;  // the paragraph at the bottom
  bool note_warn = false;
  int progress = -1;  // permille, downloading
  std::vector<Hint> hints;
};
void DrawGame(Painter& p, const GameView& view);

struct Drive {
  std::string letter, name, path, side_big, side_small, chip;
  bool chip_warn = false, side_warn = false, disabled = false;
  int used_permille = -1, steam_permille = -1;
};
struct PickerView {  // the install location and the move destination
  GameView backdrop;
  bool has_backdrop = true;
  std::string label, title, subtitle;
  std::vector<Drive> drives;
  int selected = 0;
  bool show_default = false, make_default = false;
  std::string note;
  std::vector<Hint> hints;
};
void DrawPicker(Painter& p, const PickerView& view);

struct MoveView {
  GameView backdrop;
  bool has_backdrop = true;
  int step = 0;  // 0 confirm, 1 moving, 2 done
  std::string title;
  Drive from, to;
  std::vector<std::pair<std::string, std::string>> facts;
  std::string note;
  int stage = 0;  // moving: 0 scan .. 4 remove
  int permille = 0;
  std::string percent, detail, route;
  bool ok = true;
  std::string headline, headline_sub;
  std::vector<std::string> buttons;
  int focus = 0;
  std::vector<Hint> hints;
};
void DrawMove(Painter& p, const MoveView& view);

struct DownloadRow {
  Cover cover;
  std::string name, detail, right;
};
struct DownloadsView {
  Frame frame;
  std::string subtitle;
  bool active = false;
  DownloadRow current;
  int permille = 0;
  std::string percent_line, speed_line, state_line;
  std::vector<DownloadRow> paused, finished;
  int selected = 0;  // over active (if any), paused, finished
};
void DrawDownloads(Painter& p, const DownloadsView& view);

struct StorageGame {
  std::string name, size;
};
struct StorageView {
  Frame frame;
  std::string subtitle;
  std::vector<std::pair<std::string, int>> drives;  // "E: USB 1", games
  int drive = 0;
  bool games_focus = false;
  std::string name, chip, paths;
  int steam_permille = 0, other_permille = 0;
  std::string steam_label, other_label, free_label;
  std::vector<StorageGame> games;
  int game = 0;
  std::string note;
};
void DrawStorage(Painter& p, const StorageView& view);

struct SettingRow {
  std::string label, value;
  bool choice = false;  // left and right change it: drawn with arrows when selected
  bool dim_value = false;
};
struct SettingsView {
  Frame frame;
  std::string subtitle;
  std::vector<SettingRow> rows;
  int selected = 0;
  std::string lead, detail, saved;
};
void DrawSettings(Painter& p, const SettingsView& view);

struct MenuView {  // the power menu, and a choice in a modal (a game still running)
  HomeView home;  // behind the scrim
  bool right_panel = true;
  std::string label, title, text;
  std::vector<std::string> rows;
  std::vector<int> icons;  // per row, -1 none
  int selected = 0;
  std::string note;
  std::vector<Hint> hints;
};
void DrawMenu(Painter& p, const MenuView& view);

struct MessageView {  // a modal message, confirmation or progress over a backdrop
  GameView backdrop;
  bool has_backdrop = false;
  std::string label, title, text;
  bool warn = false;
  std::vector<std::string> buttons;
  int focus = 0;
  int permille = -1;  // a progress bar
  std::vector<Hint> hints;
};
void DrawMessage(Painter& p, const MessageView& view);

// A choice in a modal over the game page (Steam emulation)
struct ChoiceRow {
  std::string label, value;
  bool disabled = false, warn = false;  // warn: the value is a warning chip
  // marks at the row's right end (Painter::Badge kinds); with marks, the value is a dim note before them
  std::vector<std::pair<std::string, int>> marks;
};
struct ChoiceView {
  GameView backdrop;
  std::string label, title, text;
  std::vector<ChoiceRow> rows;
  int selected = 0;
  std::vector<Hint> hints;
};
void DrawChoice(Painter& p, const ChoiceView& view);

// A loading screen (starting, restarting into the desktop)
void DrawSplash(Painter& p, const std::string& what);

// ---- adding a non-Steam game (the approved review, 2026-11-25) ----
struct FoundRow {
  std::string name, path, arch;
  bool shortcut = false, ticked = false;
};
struct FoundView {  // step 1: games found on the console, ticked to add
  std::string label = "ADD A NON-STEAM GAME", title = "Found on this console", subtitle;
  std::vector<FoundRow> rows;
  int selected = 0;
  std::string empty, note;
  std::vector<Hint> hints;
};
void DrawFound(Painter& p, const FoundView& view);

struct BrowseEntry {
  std::string name, detail;
  int kind = 0;  // 0 up one folder, 1 folder, 2 file
};
struct BrowseView {  // step 1b: a drive list and a folder
  std::string label = "BROWSE FOR AN EXE";
  std::vector<std::string> places;
  int place = 0;
  bool places_focus = false;
  std::string path;  // the folder, as Windows names it
  std::vector<BrowseEntry> entries;
  int selected = 0;
  std::string note, empty;
  std::vector<Hint> hints;
};
void DrawBrowse(Painter& p, const BrowseView& view);

struct DetailsView {  // step 2 (and Edit): name, program, folder, options, cover
  std::string label = "ADD A NON-STEAM GAME";
  Cover cover;
  std::string title;
  std::vector<SettingRow> rows;
  int selected = 0;  // rows, then the buttons
  std::vector<std::string> buttons;
  std::string note;
  std::vector<Hint> hints;
};
void DrawDetails(Painter& p, const DetailsView& view);

// The on-screen keyboard: four rows of ten characters, then SHIFT, SPACE, DELETE, DONE.
enum KeyKind { kKeyChar, kKeyShift, kKeySpace, kKeyDelete, kKeyDone };
constexpr int kKeyRows = 5, kKeyCols = 10;
KeyKind KeyAt(int row, int col, bool shift, std::string* text);
struct KeyboardView {
  std::string label = "ADD A NON-STEAM GAME", field, text;
  Cover cover;
  bool shift = false;
  int row = 0, col = 0;
  std::vector<Hint> hints;
};
void DrawKeyboard(Painter& p, const KeyboardView& view);

struct CoverChoice {
  Cover cover;
  std::string label, sub;
};
struct CoverChoiceView {  // step 3: the cover
  std::string label = "COVER", title;
  std::vector<CoverChoice> choices;
  int selected = 0;
  std::string note;
  std::vector<Hint> hints;
};
void DrawCoverChoice(Painter& p, const CoverChoiceView& view);

std::string Initials(const std::string& name);

}  // namespace bp

// steam_ui.c's text pages, drawn in Big Picture's look (C linkage). qr: modules or NULL.
extern "C" void steam_bp_draw_page(sd_canvas* canvas, const char* text, const unsigned char* qr, int qr_size);
