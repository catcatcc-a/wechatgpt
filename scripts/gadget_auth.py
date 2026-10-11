"""Private Gadget credentials shared by staging, launchers and diagnostic tools."""
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat

ROOT = Path(__file__).resolve().parents[1]


def read_token(path=None):
    path = Path(path) if path is not None else ROOT / 'data/gadget.token'
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Gadget token must be an owner-only regular file (0600)')
            value = stream.read(257).strip()
    except OSError:
        raise ValueError('Private data/gadget.token is required; prepare the authenticated app first') from None
    if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', value):
        raise ValueError('Invalid Gadget token format')
    return value


def ensure_token(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return read_token(path)
    with os.fdopen(fd, 'w') as stream:
        value = secrets.token_urlsafe(48)
        stream.write(value + '\n')
    return value


def write_config(app, token):
    path = Path(app) / 'Contents/Resources/FridaGadget.config'
    if path.is_symlink():
        raise ValueError('Refusing a symlink at the Gadget configuration destination')
    configuration = {'interaction': {'type': 'listen', 'address': '127.0.0.1',
                     'port': 27042, 'on_load': 'resume', 'token': token}}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(configuration, stream, indent=2)
        stream.write('\n')


def validate_app(app, token):
    path = Path(app) / 'Contents/Resources/FridaGadget.config'
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Gadget configuration must be an owner-only regular file (0600)')
        interaction = json.loads(path.read_text())['interaction']
        expected = {'type': 'listen', 'address': '127.0.0.1', 'port': 27042, 'on_load': 'resume'}
        if any(interaction.get(k) != v for k, v in expected.items()):
            raise ValueError('Gadget must use the supported loopback listener configuration')
        configured = interaction.get('token', '')
        if not isinstance(configured, str) or not hmac.compare_digest(configured.encode(), token.encode()):
            raise ValueError('Gadget configuration and private token do not match')
        link = Path(app) / 'Contents/Frameworks/FridaGadget.config'
        if not link.is_symlink() or link.resolve() != path.resolve():
            raise ValueError('Gadget framework configuration must link to its private resource configuration')
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('Authenticated Gadget configuration is missing or invalid') from None


def connect(frida, token_path=None):
    # No unauthenticated fallback, even for diagnostic scripts.
    token = read_token(token_path)
    return frida.get_device_manager().add_remote_device('127.0.0.1:27042', token=token)
