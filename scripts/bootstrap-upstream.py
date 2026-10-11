#!/usr/bin/env python3
"""Fetch the pinned upstream engine, apply the local patch, and build OneBot."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor/wechat_chatter"
URL = "https://github.com/yincongcyincong/wechat_chatter.git"
COMMIT = "f222f37321f66d3a199cb3c7642f77f7504d85da"
PATCH = ROOT / "patches/wechat_chatter-local-auth.patch"
DEVKIT_URL = "https://github.com/frida/frida/releases/download/17.8.0/frida-core-devkit-17.8.0-macos-arm64.tar.xz"
DEVKIT_SHA256 = "7606cd0eda21829e268ed66e1ac7dcd819570baee7b7049a96e8986969bf32d1"
GO_TOOLCHAIN = "go1.26.9"


def run(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch_upstream() -> None:
    if not (UPSTREAM / ".git").is_dir():
        UPSTREAM.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", URL, str(UPSTREAM))
    current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=UPSTREAM, text=True).strip()
    if current != COMMIT:
        run("git", "fetch", "--depth", "1", "origin", COMMIT, cwd=UPSTREAM)
        if subprocess.run(["git", "diff", "--quiet"], cwd=UPSTREAM).returncode:
            raise SystemExit("The upstream worktree has local changes; review them before changing revisions.")
        run("git", "checkout", "--detach", COMMIT, cwd=UPSTREAM)
    if not (UPSTREAM / "onebot/server.go").exists():
        run("git", "apply", "--check", str(PATCH), cwd=UPSTREAM)
        run("git", "apply", str(PATCH), cwd=UPSTREAM)
    elif subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)], cwd=UPSTREAM).returncode != 0:
        raise SystemExit("Upstream worktree contains server.go but does not match the recorded patch.")


def fetch_devkit() -> Path:
    archive = ROOT / "downloads/frida-core-devkit-17.8.0-macos-arm64.tar.xz"
    target = UPSTREAM / "frida-devkit"
    required = [target / "libfrida-core.a", target / "frida-core.h"]
    if all(path.is_file() for path in required):
        return target
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix(archive.suffix + ".part")
        try:
            with urllib.request.urlopen(DEVKIT_URL, timeout=120) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if sha256(temporary) != DEVKIT_SHA256:
                raise SystemExit("Frida devkit SHA-256 mismatch")
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    elif sha256(archive) != DEVKIT_SHA256:
        raise SystemExit(f"Unexpected Frida devkit archive: {archive}")
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:xz") as bundle:
        for member in bundle.getmembers():
            destination = (target / member.name).resolve()
            if target.resolve() not in destination.parents:
                raise SystemExit("Unsafe path in devkit archive")
        bundle.extractall(target)
    return target


def build(devkit: Path) -> Path:
    onebot = UPSTREAM / "onebot"
    output = onebot / "onebot"
    env = dict(os.environ)
    env.update({
        "GOOS": "darwin", "GOARCH": "arm64", "CGO_ENABLED": "1", "CC": "/usr/bin/clang",
        "CGO_CFLAGS": f"-I{devkit}", "CGO_LDFLAGS": f"-L{devkit} -lfrida-core",
        "GOTOOLCHAIN": GO_TOOLCHAIN, "GOMAXPROCS": "2",
    })
    run("go", "build", "-p=2", "-trimpath", "-o", str(output), ".", cwd=onebot, env=env)
    output.chmod(output.stat().st_mode | 0o111)
    return output


def main() -> None:
    fetch_upstream()
    devkit = fetch_devkit()
    binary = build(devkit)
    print(f"Built {binary}")


if __name__ == "__main__":
    main()
