#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
"""MangoHud takes the parentheses out of the GPU name without std::regex (04.26).

overlay_CreateSwapchainKHR (src/vulkan.cpp) names the GPU with remove_parentheses (src/file_utils.cpp), which builds
std::regex("\\\\([^)]*\\\\)") on every swapchain. It is the only std::regex the Windows build compiles. libc++'s regex
classifies each pattern character through the ctype<char> facet of std::locale::classic(), and on the MSVC C runtime
libc++ fills that facet once, at its first use, with __pctype_func(): the character table of the calling thread's
locale at that moment, not a table of its own. MangoHud's static iostream setup makes that first use when the DLL
loads. With every guest in one process, the DLL stays loaded from one program to the next, so the pointer it keeps can
outlive the locale it came from (SeaMonkey switches ucrt's locale away from "C" at start; Wine's ucrt allocates the
table of any locale but "C").
Hardware 2026-11-18 (run-0234, OpenGL on): SeaMonkey's second start ended in an uncaught C++ exception (0x20474343) on
Gecko's compositor thread, with typeinfo for std::regex_error and libMangoHud.dll's unwinder on its stack, right after
Mesa started Zink's queue threads; Gecko's crash reporter followed. The first start created the same swapchains
without it. A constant, valid pattern only fails to parse when the table changed under it.
Here the parentheses are removed by a loop with the regex's result: each "(" with a ")" after it is removed up to and
including that ")"; an unmatched "(" stays. Nothing in it depends on a locale. The i386 build copies this tree
(build-mangohud-i386.sh) and checks the marker.
"""
import pathlib, sys

MARKER = 'OrbisDesk 04.26: GPU name without std::regex'
path = pathlib.Path(sys.argv[1]) / 'src/file_utils.cpp'
text = path.read_text()
if MARKER in text:
    print('gpu name patch already applied')
    sys.exit(0)
old = """std::string remove_parentheses(const std::string& text) {
    // Remove parentheses and text between them
    std::regex pattern("\\\\([^)]*\\\\)");
    return std::regex_replace(text, pattern, "");
}
"""
new = """std::string remove_parentheses(const std::string& text) {
    /* """ + MARKER + """ (tools/vk-h0/patch-mangohud-gpu-name.py): libc++'s regex reads the
     * character table std::locale::classic() kept from the locale of the program that loaded this DLL first */
    std::string out;
    out.reserve(text.size());
    for (size_t i = 0; i < text.size(); ++i) {
        size_t close;
        if (text[i] == '(' && (close = text.find(')', i + 1)) != std::string::npos) {
            i = close;
            continue;
        }
        out += text[i];
    }
    return out;
}
"""
if text.count(old) != 1:
    raise SystemExit('unexpected remove_parentheses in src/file_utils.cpp')
path.write_text(text.replace(old, new))
print('gpu name patch applied')
