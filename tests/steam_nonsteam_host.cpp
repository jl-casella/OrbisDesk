// SPDX-License-Identifier: GPL-3.0-or-later
// Non-Steam games (native/steam/steam_nonsteam.cpp) against a made-up console: a Wine prefix with shortcuts,
// game folders on C: and on a USB drive, exes built here with a version resource, and .lnk files.
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdint>
#include <cstdlib>
#include <string>
#include <vector>

#include "steam_nonsteam.h"

namespace {
int failures = 0;
#define CHECK(x)                                                    \
  do {                                                              \
    if (!(x)) {                                                     \
      fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); \
      ++failures;                                                   \
    }                                                               \
  } while (0)

void Put16(std::string& s, std::size_t at, std::uint32_t v) {
  if (s.size() < at + 2) s.resize(at + 2);
  s[at] = static_cast<char>(v & 0xff), s[at + 1] = static_cast<char>((v >> 8) & 0xff);
}
void Put32(std::string& s, std::size_t at, std::uint32_t v) { Put16(s, at, v & 0xffff), Put16(s, at + 2, v >> 16); }
// UTF-8 (up to three bytes a character) to UTF-16LE
std::string Wide(const std::string& text) {
  std::string w;
  for (std::size_t i = 0; i < text.size(); ++i) {
    std::uint32_t cp = static_cast<std::uint8_t>(text[i]);
    if (cp >= 0xe0 && i + 2 < text.size())
      cp = (cp & 0x0f) << 12 | (static_cast<std::uint8_t>(text[i + 1]) & 0x3f) << 6 | (static_cast<std::uint8_t>(text[i + 2]) & 0x3f), i += 2;
    else if (cp >= 0xc0 && i + 1 < text.size())
      cp = (cp & 0x1f) << 6 | (static_cast<std::uint8_t>(text[i + 1]) & 0x3f), i += 1;
    w += static_cast<char>(cp & 0xff), w += static_cast<char>(cp >> 8);
  }
  return w;
}

// a PE32 or PE32+ image with one .rsrc section holding RT_VERSION -> 1 -> 0x409 -> a String `key` = `value`
std::string Exe(bool x64, const std::string& key, const std::string& value) {
  std::string pe(0x200, '\0');
  pe[0] = 'M', pe[1] = 'Z';
  Put32(pe, 0x3c, 0x40);
  pe.replace(0x40, 4, std::string("PE\0\0", 4));
  Put16(pe, 0x44, x64 ? 0x8664 : 0x14c);
  Put16(pe, 0x46, 1);
  const std::uint32_t optional_size = x64 ? 240 : 224;
  Put16(pe, 0x54, optional_size);
  const std::size_t optional = 0x58;
  Put16(pe, optional, x64 ? 0x20b : 0x10b);
  const std::size_t directories = optional + (x64 ? 112 : 96);
  std::string res(0x58, '\0');
  // the String: wLength, wValueLength, wType, key, padding, value
  std::string str(6, '\0');
  str += Wide(key) + std::string(2, '\0');
  while (str.size() % 4) str += '\0';
  str += Wide(value) + std::string(2, '\0');
  Put16(str, 0, static_cast<std::uint32_t>(str.size()));
  Put16(str, 2, static_cast<std::uint32_t>(value.size() + 1));
  Put16(str, 4, 1);
  Put16(res, 14, 1), Put32(res, 16, 16), Put32(res, 20, 0x80000000u | 0x18);
  Put16(res, 0x18 + 14, 1), Put32(res, 0x18 + 16, 1), Put32(res, 0x18 + 20, 0x80000000u | 0x30);
  Put16(res, 0x30 + 14, 1), Put32(res, 0x30 + 16, 0x409), Put32(res, 0x30 + 20, 0x48);
  Put32(res, 0x48, 0x1000 + 0x58), Put32(res, 0x4c, static_cast<std::uint32_t>(str.size()));
  res += str;
  Put32(pe, directories + 16, 0x1000), Put32(pe, directories + 20, static_cast<std::uint32_t>(res.size()));
  const std::size_t section = optional + optional_size;
  pe.replace(section, 5, ".rsrc");
  Put32(pe, section + 8, static_cast<std::uint32_t>(res.size()));
  Put32(pe, section + 12, 0x1000);
  Put32(pe, section + 16, static_cast<std::uint32_t>(res.size()));
  Put32(pe, section + 20, 0x200);
  return pe + res;
}

// a .lnk with LinkInfo (ANSI local base path) and Unicode working folder and arguments
std::string Link(const std::string& target, const std::string& folder, const std::string& arguments) {
  std::string l(0x4c, '\0');
  Put32(l, 0, 0x4c);
  Put32(l, 0x14, 0x2 | 0x10 | 0x20 | 0x80);
  std::string info(0x1c, '\0');
  Put32(info, 4, 0x1c), Put32(info, 8, 1), Put32(info, 12, 0x1c);
  const std::string volume = std::string(16, '\0');
  Put32(info, 12, 0x1c);
  info += volume;
  Put32(info, 16, static_cast<std::uint32_t>(info.size()));
  info += target + std::string(1, '\0');
  Put32(info, 24, static_cast<std::uint32_t>(info.size()));
  info += std::string(1, '\0');
  Put32(info, 0, static_cast<std::uint32_t>(info.size()));
  l += info;
  for (const auto& text : {folder, arguments}) {
    std::string count;
    Put16(count, 0, static_cast<std::uint32_t>(text.size()));
    l += count + Wide(text);
  }
  return l;
}

void Write(const std::string& path, const std::string& bytes) {
  FILE* f = fopen(path.c_str(), "wb");
  if (!f) return;
  fwrite(bytes.data(), 1, bytes.size(), f);
  fclose(f);
}
void Mkdirs(const std::string& path) {
  std::string at;
  for (std::size_t i = 0; i <= path.size(); ++i) {
    if (i == path.size() || path[i] == '/') {
      if (!at.empty()) mkdir(at.c_str(), 0755);
    }
    if (i < path.size()) at += path[i];
  }
}
}  // namespace

int main(int argc, char** argv) {
  using namespace orbisdesk;
  const std::string base = argc > 1 ? argv[1] : "nonsteam-sandbox";
  Mkdirs(base);
  char real[4096];
  const std::string root = realpath(base.c_str(), real) ? real : base;
  auto& roots = Roots();
  roots.drive_c = root + "/prefix/drive_c";
  roots.z = root + "/data";
  roots.usb = {root + "/usb0", root + "/usb1"};
  const std::string c = roots.drive_c;
  Mkdirs(c + "/users/orbis/Desktop");
  Mkdirs(c + "/ProgramData/Microsoft/Windows/Start Menu/Programs/Steam");
  Mkdirs(c + "/Program Files (x86)/Rockstar Games/GTAIV");
  Mkdirs(c + "/Program Files/Common Files/Thing");
  Mkdirs(c + "/windows/system32");
  Mkdirs(roots.usb[1] + "/Games/NFS Most Wanted/bin");
  Mkdirs(roots.usb[1] + "/Steam Games/220");
  Mkdirs(roots.z);

  // exes: their name and kind come from the image
  Write(c + "/Program Files (x86)/Rockstar Games/GTAIV/GTAIV.exe", Exe(false, "ProductName", "Grand Theft Auto IV") + std::string(5000, 'x'));
  Write(c + "/Program Files (x86)/Rockstar Games/GTAIV/LaunchGTAIV.exe", Exe(false, "FileDescription", "Launcher"));
  Write(c + "/Program Files (x86)/Rockstar Games/GTAIV/unins000.exe", Exe(false, "ProductName", "Uninstall"));
  Write(c + "/Program Files/Common Files/Thing/thing.exe", Exe(true, "ProductName", "Shared thing"));
  Write(roots.usb[1] + "/Games/NFS Most Wanted/speed.exe", Exe(false, "ProductName", "Need for Speed\xe2\x84\xa2 Most Wanted"));
  Write(roots.usb[1] + "/Games/NFS Most Wanted/NFSMWConfig.exe", Exe(false, "ProductName", "Config"));
  Write(roots.usb[1] + "/Games/NFS Most Wanted/bin/tool.exe", Exe(false, "", ""));
  Write(roots.usb[1] + "/Steam Games/220/hl2.exe", Exe(false, "ProductName", "Half-Life 2"));
  Write(roots.usb[1] + "/Games/notes.txt", "x");

  auto gta = ReadExeInfo(c + "/Program Files (x86)/Rockstar Games/GTAIV/GTAIV.exe");
  CHECK(gta.pe && gta.arch == "x86" && gta.product == "Grand Theft Auto IV");
  auto thing = ReadExeInfo(c + "/Program Files/Common Files/Thing/thing.exe");
  CHECK(thing.pe && thing.arch == "x64" && thing.product == "Shared thing");
  auto launcher = ReadExeInfo(c + "/Program Files (x86)/Rockstar Games/GTAIV/LaunchGTAIV.exe");
  CHECK(launcher.product == "Launcher");
  CHECK(!ReadExeInfo(roots.usb[1] + "/Games/notes.txt").pe);

  // paths: drive letters both ways, case-insensitive on the way in
  CHECK(WindowsToUnix("C:\\program files (x86)\\ROCKSTAR GAMES\\gtaiv\\gtaiv.EXE") ==
        c + "/Program Files (x86)/Rockstar Games/GTAIV/GTAIV.exe");
  CHECK(WindowsToUnix("e:\\Games") == roots.usb[1] + "/Games");
  CHECK(WindowsToUnix("Q:\\x").empty() && WindowsToUnix("nope").empty());
  CHECK(UnixToWindows(roots.usb[1] + "/Games/NFS Most Wanted/speed.exe") == "E:\\Games\\NFS Most Wanted\\speed.exe");
  CHECK(UnixToWindows(c + "/Games") == "C:\\Games" && UnixToWindows(roots.z + "/orbisdesk") == "Z:\\orbisdesk");
  CHECK(WindowsFolder("C:\\Games\\X\\x.exe") == "C:\\Games\\X" && WindowsFolder("C:\\x.exe") == "C:\\");
  CHECK(WindowsBasename("C:\\Games\\X\\x.exe") == "x.exe");

  // a shortcut on the desktop: its own name, target, folder and arguments
  Write(c + "/users/orbis/Desktop/Grand Theft Auto IV.lnk",
        Link("C:\\Program Files (x86)\\Rockstar Games\\GTAIV\\LaunchGTAIV.exe", "C:\\Program Files (x86)\\Rockstar Games\\GTAIV",
             "-norestrictions"));
  Write(c + "/users/orbis/Desktop/Uninstall.lnk", Link("C:\\Program Files (x86)\\Rockstar Games\\GTAIV\\unins000.exe", "", ""));
  Write(c + "/users/orbis/Desktop/Gone.lnk", Link("C:\\Games\\Gone\\gone.exe", "", ""));
  Write(c + "/ProgramData/Microsoft/Windows/Start Menu/Programs/Steam/Half-Life 2.lnk",
        Link("E:\\Steam Games\\220\\hl2.exe", "", ""));
  auto link = ReadLink(c + "/users/orbis/Desktop/Grand Theft Auto IV.lnk");
  CHECK(link.ok && link.target == "C:\\Program Files (x86)\\Rockstar Games\\GTAIV\\LaunchGTAIV.exe" &&
        link.arguments == "-norestrictions" && link.folder == "C:\\Program Files (x86)\\Rockstar Games\\GTAIV");
  CHECK(!ParseLink("not a link").ok);

  // the search: the shortcut, the USB game; not the uninstaller, the shared Common Files, a missing target,
  // OrbisDesk's Steam shortcut or a Steam game's folder
  auto found = FindNonSteamGames({}, {roots.usb[1] + "/Steam Games"});
  CHECK(found.size() == 2);
  bool shortcut = false, usb = false, folder_gta = false;
  for (const auto& f : found) {
    if (f.shortcut && f.name == "Grand Theft Auto IV" && f.options == "-norestrictions" &&
        f.program == "C:\\Program Files (x86)\\Rockstar Games\\GTAIV\\LaunchGTAIV.exe")
      shortcut = true;
    if (!f.shortcut && f.name == "Need for Speed\xe2\x84\xa2 Most Wanted" && f.program == "E:\\Games\\NFS Most Wanted\\speed.exe" &&
        f.folder == "E:\\Games\\NFS Most Wanted" && f.arch == "x86")
      usb = true;
    if (!f.shortcut && f.program == "C:\\Program Files (x86)\\Rockstar Games\\GTAIV\\GTAIV.exe") folder_gta = true;
    CHECK(f.name != "Half-Life 2" && f.name != "Shared thing" && f.name != "Uninstall");
  }
  if (!(shortcut && usb && !folder_gta))
    for (const auto& f : found)
      fprintf(stderr, "found [%s] [%s] [%s] [%s] [%s] shortcut=%d\n", f.name.c_str(), f.program.c_str(), f.folder.c_str(),
              f.options.c_str(), f.arch.c_str(), f.shortcut);
  CHECK(shortcut && usb && !folder_gta);
  // what is already in the list is not offered again
  auto again = FindNonSteamGames({LowerAscii("E:\\Games\\NFS Most Wanted\\speed.exe")}, {roots.usb[1] + "/Steam Games"});
  CHECK(again.size() == 1);

  // the list: saved, read back, ids from the program, odd characters survive, duplicates dropped
  NonSteamGame a;
  a.program = "E:\\Games\\NFS Most Wanted\\speed.exe";
  a.id = NonSteamId(a.program);
  a.name = "Need for Speed\xe2\x84\xa2 Most Wanted";
  a.folder = "E:\\Games\\NFS Most Wanted";
  a.options = "-a \\b\tc";
  a.cover = "store:1262560";
  a.added = 1764000000;
  NonSteamGame b = a;
  b.program = "e:\\games\\nfs most wanted\\SPEED.exe";  // the same program
  b.id = NonSteamId(b.program);
  CHECK(a.id == b.id && IsNonSteamId(a.id) && !IsNonSteamId(220));
  const std::string list = root + "/data/non-steam-games.txt";
  CHECK(SaveNonSteamGames(list, {a, b}));
  struct stat st{};
  CHECK(stat(list.c_str(), &st) == 0 && (st.st_mode & 0777) == 0600);
  auto loaded = LoadNonSteamGames(list);
  CHECK(loaded.size() == 1 && loaded[0].name == a.name && loaded[0].options == a.options && loaded[0].cover == a.cover &&
        loaded[0].id == a.id && loaded[0].added == a.added && loaded[0].folder == a.folder && !loaded[0].named);
  // a typed name survives; a list written before that column reads as not named
  a.named = true;
  CHECK(SaveNonSteamGames(list, {a}));
  loaded = LoadNonSteamGames(list);
  CHECK(loaded.size() == 1 && loaded[0].named);
  {
    FILE* old = fopen(list.c_str(), "w");
    fputs("1\t1764000000\tOld\tC:\\\\Old\\\\old.exe\tC:\\\\Old\t\tplain\n", old);
    fclose(old);
    loaded = LoadNonSteamGames(list);
    CHECK(loaded.size() == 1 && loaded[0].name == "Old" && !loaded[0].named);
  }
  CHECK(LoadNonSteamGames(root + "/data/none.txt").empty());

  // folders for the browser: sub-folders first, then the asked-for files
  std::vector<FolderEntry> entries;
  CHECK(ListFolder(roots.usb[1] + "/Games/NFS Most Wanted", {".exe"}, &entries));
  CHECK(entries.size() == 3 && entries[0].folder && entries[0].name == "bin" && entries[1].name == "NFSMWConfig.exe" &&
        entries[2].name == "speed.exe" && entries[2].bytes > 0);
  CHECK(ListFolder(roots.usb[1] + "/Games", {".exe"}, &entries) && entries.size() == 1);
  CHECK(!ListFolder(root + "/nowhere", {".exe"}, &entries));

  CHECK(ExcludedProgram("unins000.exe") && ExcludedProgram("vcredist_x86.exe") && ExcludedProgram("readme.txt") &&
        !ExcludedProgram("GTAIV.exe") && !ExcludedProgram("LaunchGTAIV.exe"));
  CHECK(CleanName(" a\tb\n ") == "a b");

  // the store search
  CHECK(StoreSearchUrl("Grand Theft Auto IV") ==
        "https://store.steampowered.com/api/storesearch/?term=Grand%20Theft%20Auto%20IV&l=english&cc=US");
  auto apps = ParseStoreSearch(
      "{\"total\":3,\"items\":[{\"type\":\"app\",\"name\":\"Need for Speed\\u2122 Most Wanted\",\"id\":1262560},"
      "{\"type\":\"sub\",\"name\":\"Bundle\",\"id\":5},{\"type\":\"app\",\"name\":\"Other\",\"id\":17430}]}");
  CHECK(apps.size() == 2 && apps[0].first == 1262560 && apps[0].second == "Need for Speed\xe2\x84\xa2 Most Wanted" &&
        apps[1].first == 17430);
  CHECK(ParseStoreSearch("nope").empty());

  // the api host's search
  CHECK(StoreSuggestUrl("Grand \"Theft\"").rfind("https://api.steampowered.com/IStoreQueryService/SearchSuggestions/v1?input_json=", 0) == 0);
  CHECK(StoreSuggestUrl("Grand \"Theft\"").find("Grand%20%5C%22Theft%5C%22") != std::string::npos);
  auto ids = ParseStoreSuggest(
      "{\"response\":{\"metadata\":{\"total_matching_records\":6},\"ids\":[{\"appid\":1262560},{\"appid\":1262572},{\"x\":1}]}}");
  CHECK(ids.size() == 2 && ids[0] == 1262560 && ids[1] == 1262572);
  CHECK(ParseStoreSuggest("{\"response\":{\"metadata\":{\"total_matching_records\":0}}}").empty() && ParseStoreSuggest("x").empty());

  // what is searched for: signs, brackets and editions out, the subtitle cut, then the folder
  auto terms = StoreSearchTerms("Need for Speed\xe2\x84\xa2 Most Wanted Black Edition (v1.3)",
                                "E:\\PC\\Need for Speed Most Wanted\\speed2.exe");
  CHECK(terms.size() == 2 && terms[0] == "Need for Speed Most Wanted Black Edition" && terms[1] == "Need for Speed Most Wanted");
  terms = StoreSearchTerms("Star Wars\xc2\xae: The Force Unleashed - Ultimate Sith Edition", "C:\\Games\\SWTFU\\bin\\swtfu.exe");
  CHECK(terms.size() == 5 && terms[0] == "Star Wars: The Force Unleashed - Ultimate Sith Edition" &&
        terms[1] == "Star Wars: The Force Unleashed - Ultimate Sith" && terms[2] == "Star Wars: The Force Unleashed" &&
        terms[3] == "Star Wars" && terms[4] == "SWTFU");
  terms = StoreSearchTerms("speed2", "E:\\PC\\Need for Speed Most Wanted\\speed2.exe");
  CHECK(terms.size() == 2 && terms[0] == "Need for Speed Most Wanted" && terms[1] == "speed2");
  CHECK(StoreSearchTerms("", "C:\\x.exe").empty());
  // the store's name has to be the term's (hardware 2026-11-26: Underground 2 took other games' DLC covers)
  CHECK(!StoreNameMatches("Need for Speed Underground 2", "Need for Speed\xe2\x84\xa2 Unbound - Audi RS 6 Avant \xe2\x80\x98" "20 Set"));
  CHECK(!StoreNameMatches("Need for Speed Underground 2", "Need for Speed\xe2\x84\xa2 Payback: Chevrolet Colorado ZR2 Bundle"));
  CHECK(!StoreNameMatches("Need for Speed Underground", "Need for Speed Underground 2"));
  CHECK(!StoreNameMatches("Need for Speed Underground 2", "Need for Speed Underground"));
  CHECK(StoreNameMatches("Need for Speed Most Wanted", "Need for Speed\xe2\x84\xa2 Most Wanted"));
  CHECK(StoreNameMatches("Star Wars: The Force Unleashed - Ultimate Sith Edition",
                         "STAR WARS\xe2\x84\xa2 - The Force Unleashed\xe2\x84\xa2 Ultimate Sith Edition"));
  CHECK(!StoreNameMatches("Star Wars: The Force Unleashed", "STAR WARS\xe2\x84\xa2: The Force Unleashed\xe2\x84\xa2 II"));
  CHECK(StoreNameMatches("Grand Theft Auto 4", "Grand Theft Auto IV: The Complete Edition"));
  CHECK(StoreNameMatches("Need for Speed Most Wanted Black Edition", "Need for Speed\xe2\x84\xa2 Most Wanted"));
  CHECK(!StoreNameMatches("Need for Speed Underground", "Need for Speed\xe2\x84\xa2"));  // the 2015 game: another one
  CHECK(!StoreNameMatches("Need for Speed", "Need for Speed: Underground"));
  CHECK(!StoreNameMatches("Star Wars: The Force Unleashed - Ultimate Sith Edition", "LEGO\xc2\xae STAR WARS\xe2\x84\xa2: The Force Awakens"));
  CHECK(StoreNameMatches("Star Wars: The Force Unleashed - Ultimate Sith Edition", "STAR WARS\xe2\x84\xa2: The Force Unleashed"));
  CHECK(!StoreNameMatches("Star Wars: The Force Unleashed - Ultimate Sith Edition", "STAR WARS\xe2\x84\xa2"));
  CHECK(!StoreNameMatches("Batman: Arkham Asylum", "Batman\xe2\x84\xa2: Arkham City"));
  CHECK(StoreNameMatches("Batman Arkham Asylum", "Batman: Arkham Asylum Game of the Year Edition"));
  // the folder, for a name the user didn't type ("speed2" is the exe's)
  CHECK(CoverNameMatches("speed2", "E:\\PC\\Need for Speed Most Wanted\\speed2.exe", false, "Need for Speed\xe2\x84\xa2 Most Wanted"));
  CHECK(!CoverNameMatches("speed2", "E:\\PC\\Need for Speed Most Wanted\\speed2.exe", true, "Need for Speed\xe2\x84\xa2 Most Wanted"));
  CHECK(StoreNameMatches("Tomb Raider", "Tomb Raider (2013)"));
  CHECK(StoreNameMatches("Assassin's Creed 2", "Assassins Creed II Deluxe Edition"));
  CHECK(!StoreNameMatches("", "Portal") && !StoreNameMatches("Portal", "") && !StoreNameMatches("The", "The"));
  // Wikipedia when the store has none: one video game's article, the term's title, an upload.wikimedia.org image
  {
    const std::string reply =
        "{\"query\":{\"pages\":{"
        "\"18672269\":{\"title\":\"List of Need for Speed video games\",\"index\":4,\"description\":\"\"},"
        "\"518192\":{\"title\":\"Need for Speed\",\"index\":3,\"description\":\"Racing video game franchise\","
        "\"original\":{\"source\":\"https://upload.wikimedia.org/wikipedia/en/x/xx/NFS.png\",\"width\":300,\"height\":200}},"
        "\"1138363\":{\"title\":\"Need for Speed: Underground\",\"index\":2,\"description\":\"2003 racing video game\","
        "\"original\":{\"source\":\"https://upload.wikimedia.org/wikipedia/en/5/52/Need_for_Speed_Underground_cover.jpg\","
        "\"width\":258,\"height\":387}},"
        "\"1307965\":{\"title\":\"Need for Speed: Underground 2\",\"index\":1,\"description\":\"2004 racing video game\","
        "\"original\":{\"source\":\"https://upload.wikimedia.org/wikipedia/en/1/10/Nfsu2-win-cover.jpg\",\"width\":255,"
        "\"height\":390}},"
        "\"7\":{\"title\":\"Need for Speed: Underground 2 (film)\",\"index\":5,\"description\":\"2030 film\","
        "\"original\":{\"source\":\"https://upload.wikimedia.org/a.jpg\"}},"
        "\"8\":{\"title\":\"Need for Speed: Underground 2 (2004 video game)\",\"index\":6,\"description\":\"2004 video game\","
        "\"original\":{\"source\":\"https://evil.example/a.jpg\"}}}}}";
    const std::string program = "E:\\Games\\NFSU2\\speed2.exe";
    auto covers = ParseWikipediaCovers(reply, "Need for Speed Underground 2", program, true);
    CHECK(covers.size() == 1 && covers[0].title == "Need for Speed: Underground 2" &&
          covers[0].image == "https://upload.wikimedia.org/wikipedia/en/1/10/Nfsu2-win-cover.jpg" && covers[0].width == 255 &&
          covers[0].height == 390);
    covers = ParseWikipediaCovers(reply, "Need for Speed Underground", program, true);
    CHECK(covers.size() == 1 && covers[0].title == "Need for Speed: Underground");
    CHECK(ParseWikipediaCovers(reply, "Need for Speed", program, true).empty());  // the franchise's article is no game's
    CHECK(ParseWikipediaCovers("not json", "x", program, true).empty());
    const std::string url = WikipediaSearchUrl("Need for Speed: Underground 2");
    CHECK(url.rfind("https://en.wikipedia.org/w/api.php?", 0) == 0 &&
          url.find("gsrsearch=Need%20for%20Speed%3A%20Underground%202") != std::string::npos);
  }
  // a typed name: its own terms only, never the folder it corrected
  terms = StoreSearchTerms("Underground", "E:\\PC\\Need for Speed Most Wanted\\speed2.exe", true);
  CHECK(terms.size() == 1 && terms[0] == "Underground");
  terms = StoreSearchTerms("Need for Speed: Underground 2 - Deluxe Edition", "E:\\PC\\NFS\\speed2.exe", true);
  CHECK(terms.size() == 3 && terms[0] == "Need for Speed: Underground 2 - Deluxe Edition" &&
        terms[1] == "Need for Speed: Underground 2" && terms[2] == "Need for Speed");

  printf("non-steam games: %s\n", failures ? "FAILED" : "ok");
  return failures ? 1 : 0;
}
