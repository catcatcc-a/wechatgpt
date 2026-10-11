"""Configuration is explicit and resolved relative to its TOML file."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import tomllib
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    backend: str = "onebot"
    data_dir: Path = field(default_factory=lambda: Path("data").resolve())
    onebot_url: str = "http://127.0.0.1:58080"
    onebot_token: str = field(default="", repr=False)
    request_timeout: float = 20
    webhook_host: str = "127.0.0.1"
    webhook_port: int = 36060
    gui: dict = field(default_factory=dict)
    native_sender_command: tuple[str, ...] = ()

    @property
    def database(self) -> Path:
        return self.data_dir / "messages.sqlite3"


def load_config(path: str | Path | None = None) -> Config:
    target = Path(path or os.getenv("WECHAT_MCP_CONFIG", "config.toml")).expanduser().resolve()
    content = tomllib.loads(target.read_text()) if target.is_file() else {}
    onebot = content.get("onebot", {})
    webhook = content.get("webhook", {})
    data_dir = Path(content.get("data_dir", "data")).expanduser()
    if not data_dir.is_absolute():
        data_dir = target.parent / data_dir
    token = os.getenv("WECHAT_ONEBOT_TOKEN", onebot.get("token", ""))
    if not token and onebot.get("token_file"):
        token_file = Path(onebot["token_file"]).expanduser()
        if not token_file.is_absolute():
            token_file = target.parent / token_file
        token = token_file.read_text().strip()
    backend = content.get("backend", "onebot")
    if backend not in {"onebot", "gui"}:
        raise ValueError("backend must be 'onebot' or 'gui'")
    url = onebot.get("url", "http://127.0.0.1:58080").rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("The local OneBot endpoint must use a loopback HTTP(S) address")
    host = webhook.get("host", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Webhook host must be a loopback address")
    native = content.get("native", {})
    command = native.get("command", []) if native.get("enabled", False) else []
    if not isinstance(command, list) or any(not isinstance(part, str) or not part for part in command):
        raise ValueError("native.command must be a list of nonempty strings")
    if native.get("enabled", False) and len(command) < 2:
        raise ValueError("Native sending requires an explicit Python/helper command")
    return Config(
        backend=backend,
        data_dir=data_dir.resolve(),
        onebot_url=url,
        onebot_token=token,
        request_timeout=float(onebot.get("timeout", 20)),
        webhook_host=host,
        webhook_port=int(webhook.get("port", 36060)),
        gui=content.get("gui", {}),
        native_sender_command=tuple(command),
    )
