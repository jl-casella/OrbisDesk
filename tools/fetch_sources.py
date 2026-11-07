#!/usr/bin/env python3
"""Fetch precisely the revisions in sources.lock.json, without touching existing trees."""
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
lock = json.loads((ROOT / "sources.lock.json").read_text())
for name, source in lock["sources"].items():
    directory = ROOT / "upstream" / name
    if directory.exists():
        actual = subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()
        if actual != source["commit"]:
            raise SystemExit(f"{name}: revision differs; refusing to overwrite")
        continue
    subprocess.run(["git", "init", str(directory)], check=True)
    subprocess.run(["git", "-C", str(directory), "remote", "add", "origin", source["url"]], check=True)
    subprocess.run(["git", "-C", str(directory), "fetch", "--depth", "1", "origin", source["commit"]], check=True)
    subprocess.run(["git", "-C", str(directory), "checkout", "--detach", "FETCH_HEAD"], check=True)
