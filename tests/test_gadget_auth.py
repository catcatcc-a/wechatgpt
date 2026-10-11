from pathlib import Path
from types import SimpleNamespace

import pytest

from gadget_auth import connect, ensure_token, read_token, validate_app, write_config


def test_token_is_private_stable_and_never_falls_back(tmp_path):
    path = tmp_path / 'data/gadget.token'
    with pytest.raises(ValueError):
        read_token(path)
    token = ensure_token(path)
    assert len(token) == 64
    assert ensure_token(path) == token
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    called = []
    manager = SimpleNamespace(add_remote_device=lambda address, **kwargs: called.append((address, kwargs)))
    connect(SimpleNamespace(get_device_manager=lambda: manager), path)
    assert called == [('127.0.0.1:27042', {'token': token})]
    path.chmod(0o644)
    with pytest.raises(ValueError):
        connect(SimpleNamespace(get_device_manager=lambda: manager), path)
    assert len(called) == 1


@pytest.mark.parametrize('value', ['', 'short', 'a' * 129, 'a' * 64 + '\nsecond', 'é' * 64])
def test_invalid_token_is_rejected_without_echoing_it(tmp_path, value):
    path = tmp_path / 'gadget.token'
    path.write_text(value)
    path.chmod(0o600)
    with pytest.raises(ValueError, match='Invalid Gadget token format'):
        read_token(path)


def test_symlink_token_is_rejected(tmp_path):
    target = tmp_path / 'target'
    ensure_token(target)
    link = tmp_path / 'gadget.token'
    link.symlink_to(target)
    with pytest.raises(ValueError):
        read_token(link)


def make_app(tmp_path, token):
    app = tmp_path / 'WeChat.app'
    (app / 'Contents/Resources').mkdir(parents=True)
    (app / 'Contents/Frameworks').mkdir()
    (app / 'Contents/Frameworks/FridaGadget.config').symlink_to('../Resources/FridaGadget.config')
    write_config(app, token)
    return app


def test_app_and_client_must_share_private_credentials(tmp_path):
    token = ensure_token(tmp_path / 'data/gadget.token')
    app = make_app(tmp_path, token)
    validate_app(app, token)
    with pytest.raises(ValueError, match='do not match'):
        validate_app(app, 'different')
    config = app / 'Contents/Resources/FridaGadget.config'
    config.chmod(0o644)
    with pytest.raises(ValueError, match='owner-only'):
        validate_app(app, token)
    write_config(app, token)
    validate_app(app, token)
    config.write_text(config.read_text().replace('127.0.0.1', '0.0.0.0'))
    with pytest.raises(ValueError, match='loopback'):
        validate_app(app, token)
