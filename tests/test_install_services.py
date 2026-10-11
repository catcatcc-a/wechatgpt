"""Installer regression checks use temporary directories and mocked launchctl."""

import importlib.util
import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.parametrize("existing", [False, True])
def test_installer_preserves_token_and_restricts_permissions(tmp_path, monkeypatch, existing):
    spec = importlib.util.spec_from_file_location(
        "install_services", Path(__file__).resolve().parents[1] / "scripts/install-services.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    root, runtime, agents = (tmp_path / name for name in ("project", "runtime", "agents"))
    for relative in ("src/wechat_local_mcp", "scripts", "native", "data"):
        (root / relative).mkdir(parents=True)
    for relative in ("vendor/wechat_chatter/onebot/onebot", "vendor/wechat_chatter/onebot/script.js",
                     "vendor/wechat_chatter/wechat_version/4_1_11_53_mac.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test fixture")
    source = root / "data/onebot.token"
    source.write_text("fixture-project-token")
    source.chmod(0o644)
    target = runtime / "data/onebot.token"
    if existing:
        target.parent.mkdir(parents=True)
        target.write_text("fixture-existing-token")
        target.chmod(0o644)
    for name, value in (("ROOT", root), ("RUNTIME", runtime), ("AGENTS", agents)):
        monkeypatch.setattr(installer, name, value)
    monkeypatch.setattr(installer.subprocess, "run", lambda args, **kwargs: subprocess.CompletedProcess(args, 0))
    monkeypatch.setattr(installer.time, "sleep", lambda _: None)
    old_mask = os.umask(0o077)
    try:
        installer.main()
    finally:
        os.umask(old_mask)
    assert target.read_text() == ("fixture-existing-token" if existing else "fixture-project-token")
    assert target.stat().st_mode & 0o777 == 0o600
