"""The launcher must never use an older offset table with a new app build."""
import importlib.util
from pathlib import Path
import plistlib

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).resolve().parents[1] / "scripts/start-onebot.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def write_app(tmp_path, version, build):
    app = tmp_path / "WeChat.app"
    (app / "Contents").mkdir(parents=True, exist_ok=True)
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleShortVersionString": version, "CFBundleVersion": build}))
    binary = tmp_path / "vendor/wechat_chatter/onebot/onebot"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.touch()
    config = tmp_path / "vendor/wechat_chatter/wechat_version/4_1_11_53_mac.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('{}')
    return app


def test_current_build_is_rejected_even_with_old_config_and_binary(tmp_path):
    app = write_app(tmp_path, "4.1.15", "270134")
    result = launcher.preflight(app, tmp_path)
    assert result['can_launch'] is False
    assert result['version_config'] is None


def test_exact_compatible_build_is_required(tmp_path):
    app = write_app(tmp_path, "4.1.11", "269109")
    assert launcher.preflight(app, tmp_path)['can_launch'] is True
    app = write_app(tmp_path, "4.1.11", "269110")
    assert launcher.preflight(app, tmp_path)['can_launch'] is False
