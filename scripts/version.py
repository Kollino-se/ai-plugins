#!/usr/bin/env python3
"""Choose a strict, immutable package version; never tag the Merchant repository."""
import argparse
import re
import json
import urllib.request
import urllib.error

PATTERN = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")


def next_version(latest, bump):
    if bump not in ("major", "minor", "patch"):
        raise ValueError("Choose major, minor or patch")
    if not latest:
        return "1.0.0"
    match = PATTERN.fullmatch(latest)
    if not match:
        raise ValueError("A stable semantic version is required")
    values = [int(value) for value in match.groups()]
    index = ("major", "minor", "patch").index(bump)
    values[index] += 1
    for reset in range(index + 1, 3):
        values[reset] = 0
    return ".".join(map(str, values))


def public_latest():
    request = urllib.request.Request("https://api.github.com/repos/Kollino-se/ai-plugins/releases/latest", headers={"Accept": "application/vnd.github+json", "User-Agent": "kollino-restaurant-release"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return ""
        raise
    if data.get("draft") or data.get("prerelease") or not isinstance(data.get("tag_name"), str):
        raise ValueError("Unexpected latest release metadata")
    return data["tag_name"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest", default="")
    parser.add_argument("--public-latest", action="store_true")
    parser.add_argument("--bump", required=True, choices=("major", "minor", "patch"))
    args = parser.parse_args()
    print(next_version(public_latest() if args.public_latest else args.latest, args.bump))
