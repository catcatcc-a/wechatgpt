#!/usr/bin/env python3
"""Read-only WeChat/OneBot diagnostics. Never opens WeChat or reads chat data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess


PROJECT = Path(__file__).resolve().parent.parent
CORE_OFFSETS = {
    "sendFuncAddr", "req2bufEnterAddr", "req2bufExitAddr",
    "buf2RespAddr", "blrX8Addr", "autoBufferWriteFunc",
}
# Only these build correspondences are documented by the supplied projects.
# Do not infer a build number from the final component of a config filename.
KNOWN_BUILDS = {"4.1.11.53": "269109", "4.1.12.53": "269365"}


def run_read_only(args: list[str], timeout: float = 15) -> tuple[int | None, str]:
    try:
        # Prevent `go version` from downloading an automatically selected toolchain.
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                env={**os.environ, "GOTOOLCHAIN": "local"})
        return result.returncode, result.stdout + result.stderr
    except (OSError, subprocess.TimeoutExpired):
        return None, ""


def inspect_config(path: Path, app_version: str, app_build: str) -> dict:
    match = re.fullmatch(r"(\d+(?:_\d+)+)_mac\.json", path.name)
    version = match.group(1).replace("_", ".") if match else ""
    expected_build = KNOWN_BUILDS.get(version)
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(content, dict):
            raise ValueError("object required")
        core_valid = all(
            isinstance(content.get(key), str)
            and re.fullmatch(r"0x[0-9a-fA-F]+", content[key])
            and int(content[key], 16) > 0
            and int(content[key], 16) % 4 == 0
            for key in CORE_OFFSETS
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        core_valid = False

    exact_version = bool(version and app_version == version)
    known_short_version = bool(
        expected_build and app_version == ".".join(version.split(".")[:3])
    )
    version_match = exact_version or known_short_version
    build_match = expected_build == app_build if expected_build else None
    selectable = bool(core_valid and version_match and (build_match is not False))
    return {
        "file": path.name,
        "config_version": version or None,
        "core_offsets_well_formed": bool(core_valid),
        "version_matches": version_match,
        "documented_build": expected_build,
        "build_matches": build_match,
        "candidate_for_installed_version": selectable,
        "offsets_verified_in_binary": False,
    }


def inspect_signature(app: Path) -> dict:
    if not app.is_dir():
        return {"verification": "not_installed", "kind": "unknown"}
    if platform.system() != "Darwin":
        return {"verification": "unavailable", "kind": "unknown"}
    code, output = run_read_only(["/usr/bin/codesign", "-dv", "--verbose=4", str(app)])
    kind = "unknown"
    if code == 0:
        if "Signature=adhoc" in output:
            kind = "ad_hoc"
        elif "Authority=" in output:
            kind = "certificate"
    verify_code, _ = run_read_only(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)], timeout=30
    )
    verification = "unavailable" if verify_code is None else "valid" if verify_code == 0 else "invalid"
    # Never include raw tool output: signatures can identify a local developer.
    return {"verification": verification, "kind": kind}


def diagnose(app: Path, project: Path = PROJECT) -> dict:
    info_path = app / "Contents/Info.plist"
    installed = info_path.is_file()
    app_version = app_build = ""
    metadata_status = "not_installed"
    if installed:
        try:
            with info_path.open("rb") as handle:
                info = plistlib.load(handle)
            app_version = str(info.get("CFBundleShortVersionString", ""))
            app_build = str(info.get("CFBundleVersion", ""))
            metadata_status = "read"
        except (OSError, ValueError, TypeError, AttributeError, plistlib.InvalidFileException):
            metadata_status = "unreadable"

    native_macos = platform.system() == "Darwin"
    architectures: list[str] = []
    if installed and native_macos:
        code, output = run_read_only(
            ["/usr/bin/lipo", "-archs", str(app / "Contents/MacOS/WeChat")]
        )
        if code == 0:
            architectures = [value for value in output.split() if value in {"arm64", "arm64e", "x86_64"}]
    sip = "unavailable"
    if native_macos:
        code, output = run_read_only(["/usr/bin/csrutil", "status"])
        if code == 0:
            match = re.search(r"status:\s*(enabled|disabled)", output, re.IGNORECASE)
            sip = match.group(1).lower() if match else "unknown"

    vendor = project / "vendor/wechat_chatter"
    configs = [inspect_config(path, app_version, app_build)
               for path in sorted((vendor / "wechat_version").glob("*_mac.json"))]
    candidates = [item["file"] for item in configs if item["candidate_for_installed_version"]]
    commit_code, commit_output = run_read_only(["git", "-C", str(vendor), "rev-parse", "HEAD"])
    commit = commit_output.strip() if commit_code == 0 and re.fullmatch(r"[0-9a-f]{40}\s*", commit_output) else None
    go_version = None
    if shutil.which("go"):
        code, output = run_read_only(["go", "version"])
        match = re.search(r"\bgo(\d+\.\d+(?:\.\d+)?)\b", output)
        if code == 0 and match:
            go_version = match.group(1)

    computer_use = (Path.home() / ".codex/computer-use/Codex Computer Use.app/Contents/SharedSupport"
                    / "SkyComputerUseClient.app/Contents/MacOS/SkyComputerUseClient")
    return {
        "schema_version": 1,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "chat_data_accessed": False,
        "system": {"os": platform.system(), "architecture": platform.machine(), "sip": sip},
        "wechat": {
            "installed": installed,
            "metadata_status": metadata_status,
            "version": app_version or None,
            "build": app_build or None,
            "architectures": architectures,
            "signature": inspect_signature(app),
            "gadget_file_present": (app / "Contents/Frameworks/FridaGadget.dylib").is_file(),
        },
        "onebot": {
            "upstream_commit": commit,
            "config_directory_present": (vendor / "wechat_version").is_dir(),
            "configs": configs,
            "candidate_configs": candidates,
            "compatibility": "candidate_config_runtime_unverified" if candidates else "no_matching_version_config",
            "runtime_verified": False,
            "binary_present": (vendor / "onebot/onebot").is_file(),
            "go_version": go_version,
            "frida_cli_present": bool(shutil.which("frida")),
            "devkit_files_present": all((vendor / "frida-devkit" / name).is_file()
                                         for name in ("frida-core.h", "libfrida-core.a")),
        },
        "gui": {
            "computer_use_client_present": computer_use.is_file(),
            "enabled": False,
            "disabled_reason": "User requires background-only operation without desktop interaction.",
            "runtime_verified_by_this_check": False,
        },
        "recommended_backend": "onebot",
        "notes": [
            "Config names and core-offset syntax do not prove binary compatibility or successful delivery.",
            "This check does not launch, inject into, restart, or send messages through WeChat.",
            "GUI automation is disabled by user preference; unavailable OneBot must not fall back to GUI.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=Path("/Applications/WeChat.app"))
    args = parser.parse_args()
    print(json.dumps(diagnose(args.app.expanduser()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
