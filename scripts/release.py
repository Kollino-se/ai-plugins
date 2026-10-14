#!/usr/bin/env python3
"""Resume a public release without moving tags or replacing published bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from package import require, validate

REPOSITORY = "Kollino-se/ai-plugins"


def gh(*args, check=True):
    return subprocess.run(["gh", *args], text=True, capture_output=True, check=check)


def api(path):
    response = gh("api", "repos/" + REPOSITORY + "/" + path, check=False)
    if response.returncode:
        require("HTTP 404" in response.stderr, "GitHub API failed: " + response.stderr)
        return None
    return json.loads(response.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--production-origin", required=True)
    args = parser.parse_args()
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY, "Releases may only target the public distribution repository")
    require(__import__("re").fullmatch(r"[0-9a-f]{40}", args.commit), "Exact commit required")
    manifest = validate(args.root, args.root / "schemas", args.production_origin)
    tag = "v" + manifest["version"]
    existing = api("git/ref/tags/" + tag)
    if existing:
        require(existing["object"]["type"] == "commit" and existing["object"]["sha"] == args.commit, "Immutable tag already points to different content")
    else:
        gh("api", "--method", "POST", "repos/" + REPOSITORY + "/git/refs", "-f", "ref=refs/tags/" + tag, "-f", "sha=" + args.commit)
    release = api("releases/tags/" + tag)
    if release is None:
        gh("release", "create", tag, "--repo", REPOSITORY, "--draft", "--verify-tag", "--title", "Kollino Restaurant " + manifest["version"], "--notes-file", str(args.root / "CHANGELOG.md"))
        release = api("releases/tags/" + tag)
    require(release is not None and not release["prerelease"], "Unexpected release state")
    expected = dict(manifest["archives"])
    expected["SHA256SUMS"] = hashlib.sha256((args.artifacts / "SHA256SUMS").read_bytes()).hexdigest()
    expected["release-manifest.json"] = hashlib.sha256((args.root / "release-manifest.json").read_bytes()).hexdigest()
    existing_assets = {asset["name"]: asset for asset in release["assets"]}
    require(set(existing_assets) <= set(expected), "Unexpected asset already attached to release")
    for name, checksum in expected.items():
        local = args.root / name if name == "release-manifest.json" else args.artifacts / name
        require(local.is_file() and hashlib.sha256(local.read_bytes()).hexdigest() == checksum, "Local artifact checksum mismatch")
        if name not in existing_assets:
            require(release["draft"], "A published release cannot be repaired by adding new assets")
            gh("release", "upload", tag, str(local), "--repo", REPOSITORY)
        with tempfile.TemporaryDirectory() as folder:
            gh("release", "download", tag, "--repo", REPOSITORY, "--pattern", name, "--dir", folder)
            require(hashlib.sha256((Path(folder) / name).read_bytes()).hexdigest() == checksum, "Existing release asset has different bytes")
    if release["draft"]:
        gh("release", "edit", tag, "--repo", REPOSITORY, "--draft=false")
    print("Verified release " + tag)


if __name__ == "__main__":
    main()
