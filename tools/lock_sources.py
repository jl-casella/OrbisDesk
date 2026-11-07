#!/usr/bin/env python3
"""Capture exact source and artifact identities; never silently update a lock."""
import argparse
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOS = {
    "prospero-win": "https://github.com/mpereiraesaa/prospero-win.git",
    "DolphinPS4": "https://github.com/iHaiDeeZ/DolphinPS4.git",
    "Crema": "https://github.com/iHaiDeeZ/Crema.git",
    "Resonance": "https://github.com/iHaiDeeZ/Resonance.git",
    "shadPS4": "https://github.com/shadps4-emu/shadPS4.git",
}


def git(directory, *args):
    return subprocess.check_output(["git", "-c", "core.autocrlf=true", "-C", str(directory), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    path = ROOT / "sources.lock.json"
    if args.create:
        if path.exists():
            parser.error("lock already exists; updates require an explicit reviewed edit")
        sources = {}
        for name, url in REPOS.items():
            directory = ROOT / "upstream" / name
            sources[name] = {"url": url, "commit": git(directory, "rev-parse", "HEAD")}
        script = (ROOT / "upstream/prospero-win/tools/build_wine_ps5.sh").read_text()
        wine = re.search(r"^WINE_COMMIT=([0-9a-f]{40})$", script, re.M).group(1)
        sources["wine"] = {"url": "https://github.com/wine-mirror/wine.git", "commit": wine}
        path.write_text(json.dumps({"schema_version": 1, "sources": sources}, indent=2) + "\n")
    lock = json.loads(path.read_text())
    for name in REPOS:
        actual = git(ROOT / "upstream" / name, "rev-parse", "HEAD")
        if actual != lock["sources"][name]["commit"]:
            raise SystemExit(f"source mismatch: {name}: {actual}")
        dirty = git(ROOT / "upstream" / name, "status", "--porcelain", "--untracked-files=no")
        if dirty:
            raise SystemExit(f"upstream tracked sources changed: {name}")
    print("Pinned source revisions verified")


if __name__ == "__main__":
    main()
