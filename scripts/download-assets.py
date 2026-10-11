#!/usr/bin/env python3
"""Download pinned, public build inputs without installing or launching WeChat."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "wechat": {
        "url": "https://dldir1v6.qq.com/weixin/Universal/Mac/xWeChatMac_universal_4.1.11.53_41748.dmg",
        "path": ROOT / "downloads/xWeChatMac_universal_4.1.11.53_41748.dmg",
        "sha256": "ea80413fca0ea09eb4241e333a8f09862d33c6c967e6ab66244fd474e6ab4115",
    },
    "gadget": {
        "url": "https://github.com/frida/frida/releases/download/17.8.0/frida-gadget-17.8.0-macos-universal.dylib.xz",
        "path": ROOT / "downloads/frida-gadget-17.8.0-macos-universal.dylib.xz",
        "sha256": "4cf5433452e745e8b283c7a2e79518c2cd6295e85869589dc3c171d5689e6b8c",
    },
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fetch(name: str) -> None:
    item = ASSETS[name]
    path: Path = item["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and sha256(path) == item["sha256"]:
        print(f"{name}: already verified ({path})")
        return
    if path.exists():
        raise SystemExit(f"Refusing to overwrite an unexpected file: {path}")
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        print(f"Downloading {name} from {item['url']}")
        with urllib.request.urlopen(item["url"], timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if sha256(temporary) != item["sha256"]:
            raise SystemExit(f"SHA-256 mismatch for {name}: {temporary}")
        temporary.replace(path)
        print(f"{name}: verified ({path})")
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", choices=sorted(ASSETS), default=list(ASSETS),
                        help="Assets to fetch; default: wechat gadget")
    args = parser.parse_args()
    for name in args.names:
        fetch(name)


if __name__ == "__main__":
    main()
