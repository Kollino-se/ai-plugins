#!/usr/bin/env python3
"""Validate and reproduce Kollino Restaurant distribution archives without Laravel."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

import jsonschema

NAME = "kollino-restaurant"
VERSION = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
SCHEMA_BASE = "https://agent-plugins.org/schemas/1.0.0/"
PLATFORMS = ("openai", "claude")
SHARED_FILES = {
    "README.md", "LICENSE", "LICENSES.md", "BRAND_POLICY.md", "CHANGELOG.md", ".gitignore",
    "release-manifest.json", "requirements.txt", "scripts/package.py", "scripts/release.py",
    "scripts/version.py", "schemas/plugin.schema.json", "schemas/mcp.schema.json",
    ".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json",
    ".github/workflows/plugin-ci.yml", ".github/workflows/plugin-release.yml",
}
PLUGIN_FILES = {
    "openai": {"plugin.json", "mcp.json", "assets/logo.png", "README.md", "LICENSE", "LICENSES.md",
               "skills/kollino-restaurant/SKILL.md"},
    "claude": {".claude-plugin/plugin.json", ".mcp.json", "assets/logo.png", "README.md", "LICENSE", "LICENSES.md",
               "skills/kollino-restaurant/SKILL.md", "skills/kollino-restaurant/references/restaurant-public.md"},
}
SECRET = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-(?:proj-|ant-)[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9]{30,}")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    require(root.is_dir() and not root.is_symlink(), "The distribution root must be a real directory")
    result = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if name.split("/")[0] in (".git", ".artifacts"):
            continue
        require(not path.is_symlink(), "Symlink rejected: " + name)
        if path.is_dir():
            continue
        require(path.is_file(), "Special file rejected: " + name)
        parts = name.split("/")
        require(all(part not in ("", ".", "..") for part in parts), "Invalid path")
        allowed = name in SHARED_FILES or (parts[0] in PLUGIN_FILES and "/".join(parts[1:]) in PLUGIN_FILES[parts[0]])
        require(allowed, "Unlisted distribution file: " + name)
        require(path.stat().st_size <= 5 * 1024 * 1024, "Oversized file: " + name)
        if path.suffix != ".png":
            content = path.read_bytes()
            content.decode("utf-8")
            require(not SECRET.search(content), "Credential material rejected: " + name)
        result[name] = digest(path)
    return result


def no_apps(value):
    if isinstance(value, dict):
        require(value.get("apps") is None, "Author packages cannot contain app bindings")
        for item in value.values():
            no_apps(item)
    elif isinstance(value, list):
        for item in value:
            no_apps(item)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root, schema_root, expected_origin=None, verify_manifest=True):
    files = inventory(root)
    for name in files:
        path = root / name
        if path.suffix == ".md":
            contents = path.read_text(encoding="utf-8")
            require(not re.search(r"/(?:home|var|etc|tmp)/|[A-Za-z]:\\", contents), "Absolute filesystem path rejected")
            for target in re.findall(r"\]\(([^)]+)\)", contents):
                if target.startswith(("https://", "#")):
                    continue
                require(not target.startswith(("/", "http://")), "Unsafe Markdown reference")
                linked = (path.parent / target.split("#")[0]).resolve()
                require(linked.is_relative_to((root / name.split("/")[0]).resolve()) if name.split("/")[0] in PLUGIN_FILES else linked.is_relative_to(root.resolve()), "Markdown reference escapes package")
                require(linked.exists(), "Missing Markdown reference")
    manifest = load(root / "release-manifest.json")
    version = manifest.get("version")
    require(isinstance(version, str) and VERSION.fullmatch(version), "Strict semantic version required")
    require(manifest.get("contract_version") == 1, "Unsupported plugin contract")
    require(manifest.get("platforms") in (["openai"], ["claude"], ["openai", "claude"]), "Unsupported platforms")
    for platform in manifest["platforms"]:
        base = root / platform
        require(set(name[len(platform) + 1:] for name in files if name.startswith(platform + "/")) == PLUGIN_FILES[platform], "Incomplete plugin: " + platform)
        plugin = load(base / ("plugin.json" if platform == "openai" else ".claude-plugin/plugin.json"))
        require(plugin.get("name") == NAME and plugin.get("version") == version, "Plugin identity/version mismatch")
        mcp = load(base / ("mcp.json" if platform == "openai" else ".mcp.json"))
        require(set(mcp["mcpServers"]) == {NAME}, "Exactly one restaurant server required")
        server = mcp["mcpServers"][NAME]
        url = server.get("url", "")
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        suffix = "/restaurant" if platform == "openai" else "/claude"
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and parsed.path == suffix, "Invalid restaurant resource")
        require(server.get("type") == ("streamable-http" if platform == "openai" else "http") and set(server) == {"type", "url"}, "Invalid remote server configuration")
        require(manifest["resources"].get(platform) == url, "Resource manifest mismatch")
        if expected_origin:
            require(url == expected_origin.rstrip("/") + suffix, "Release resource is not the configured production resource")
            require("." in parsed.hostname and not re.fullmatch(r"[0-9.]+", parsed.hostname) and ":" not in parsed.hostname, "Production requires a DNS hostname")
            require(not parsed.hostname.endswith((".dev", ".test", ".local", ".localhost")) and not re.search(r"(^|[.-])(demo|staging|localhost)([.-]|$)", parsed.hostname), "Non-production release host rejected")
        skill = (base / "skills" / NAME / "SKILL.md").read_text()
        require(skill.startswith("---\nname: " + NAME + "\n") and "\ndescription: " in skill, "Invalid skill frontmatter")
        icon = (base / "assets/logo.png").read_bytes()
        require(icon.startswith(b"\x89PNG\r\n\x1a\n"), "PNG logo required")
        width, height = int.from_bytes(icon[16:20], "big"), int.from_bytes(icon[20:24], "big")
        require(width == height and 256 <= width <= 4096, "Invalid icon dimensions")
        if platform == "openai":
            no_apps(plugin)
            for filename, value in (("plugin", plugin), ("mcp", mcp)):
                jsonschema.Draft202012Validator(load(schema_root / (filename + ".schema.json"))).validate(value)
            interface = plugin["extensions"]["com.openai"]["interface"]
            for key, limit in (("displayName", 30), ("shortDescription", 30), ("longDescription", 4000), ("developerName", 80)):
                require(isinstance(interface.get(key), str) and 0 < len(interface[key]) <= limit, "Invalid listing field: " + key)
            require(interface["logo"] == "./assets/logo.png" and interface["composerIcon"] == "./assets/logo.png", "Contained icons required")
            prompts = interface.get("defaultPrompt", [])
            require(isinstance(prompts, list) and 1 <= len(prompts) <= 3 and len(set(prompts)) == len(prompts) and all(isinstance(p, str) and len(p) <= 128 and "\n" not in p and "@" not in p for p in prompts), "Invalid starter prompts")
            market = load(root / ".agents/plugins/marketplace.json")
            require(market["plugins"][0]["source"]["path"] == "./openai" and market["plugins"][0]["name"] == NAME, "OpenAI marketplace mismatch")
        else:
            content = (base / "skills" / NAME / "references/restaurant-public.md").read_bytes()
            require(digest(base / "skills" / NAME / "references/restaurant-public.md") == manifest["guide_hashes"]["restaurant-public"], "Guide snapshot mismatch")
            require(not re.search(rb"(?:get_guide|search_guides|https?://)", content + skill.encode()), "Claude workflow must be bundled and contain no remote instructions")
            market = load(root / ".claude-plugin/marketplace.json")
            require(market["plugins"][0]["source"] == "./claude" and market["plugins"][0]["name"] == NAME, "Claude marketplace mismatch")
    if verify_manifest:
        require({k: v for k, v in files.items() if k != "release-manifest.json"} == manifest["files"], "Distribution inventory/hash mismatch")
    return manifest


def archive(root, platform, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".package-")
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as output:
            for path in sorted((root / platform).rglob("*")):
                if not path.is_file():
                    continue
                require(not path.is_symlink(), "Symlink rejected")
                info = zipfile.ZipInfo(NAME + "/" + path.relative_to(root / platform).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_STORED
                output.writestr(info, path.read_bytes())
        with zipfile.ZipFile(temporary) as check:
            require(check.testzip() is None, "Archive integrity failed")
            expected = {NAME + "/" + name for name in PLUGIN_FILES[platform]}
            require(set(check.namelist()) == expected and len(check.namelist()) == len(expected), "Archive inventory mismatch")
            for entry in check.infolist():
                require(check.read(entry) == (root / platform / entry.filename[len(NAME) + 1:]).read_bytes(), "Archive bytes mismatch")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "validate"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--schemas", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--production-origin")
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args()
    require(not args.root.is_symlink(), "Symlink root rejected")
    root = args.root.resolve()
    manifest = validate(root, args.schemas or root / "schemas", args.production_origin, not args.initialize)
    if args.action == "validate":
        output = args.output or root / ".artifacts"
        for platform in manifest["platforms"]:
            filename = NAME + "-" + platform + "-" + manifest["version"] + ".zip"
            path = output / filename
            require(path.is_file() and not path.is_symlink(), "Missing or symlinked archive")
            require(digest(path) == manifest["archives"].get(filename), "Archive checksum mismatch")
            with zipfile.ZipFile(path) as check:
                require(check.testzip() is None and set(check.namelist()) == {NAME + "/" + n for n in PLUGIN_FILES[platform]}, "Archive inventory mismatch")
                require(len(check.namelist()) == len(PLUGIN_FILES[platform]), "Duplicate archive entries")
                for entry in check.infolist():
                    require(entry.date_time == (1980, 1, 1, 0, 0, 0) and entry.compress_type == zipfile.ZIP_STORED and entry.external_attr >> 16 == stat.S_IFREG | 0o644, "Unsafe archive metadata")
                    require(check.read(entry) == (root / platform / entry.filename[len(NAME) + 1:]).read_bytes(), "Archive content mismatch")
    if args.action == "build":
        output = args.output or root / ".artifacts"
        archives = {}
        for platform in manifest["platforms"]:
            filename = NAME + "-" + platform + "-" + manifest["version"] + ".zip"
            archive(root, platform, output / filename)
            archives[filename] = digest(output / filename)
        if args.initialize:
            manifest["files"] = {k: v for k, v in inventory(root).items() if k != "release-manifest.json"}
            manifest["archives"] = archives
            (root / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        else:
            require(archives == manifest["archives"], "Rebuilt archive hashes differ")
        (output / "SHA256SUMS").write_text("".join(value + "  " + key + "\n" for key, value in sorted(archives.items())))
    print(json.dumps({"version": manifest["version"], "platforms": manifest["platforms"], "validated": True}))


if __name__ == "__main__":
    main()
