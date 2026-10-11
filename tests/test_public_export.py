"""Export boundary tests use synthetic data, never a running WeChat account."""
import importlib.util
import io
from pathlib import Path
import subprocess
import tarfile

import pytest

spec = importlib.util.spec_from_file_location('public_export', Path(__file__).parents[1] / 'scripts/export-public-source.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


def repo(tmp_path):
    git(tmp_path, 'init')
    git(tmp_path, 'config', 'user.name', 'Synthetic Contributor')
    git(tmp_path, 'config', 'user.email', 'synthetic@example.invalid')
    (tmp_path / 'README.md').write_text('Public source')
    (tmp_path / '.gitignore').write_text('data/\n')
    git(tmp_path, 'add', '.')
    git(tmp_path, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Public source')
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/private.json').write_text('synthetic private conversation')
    return tmp_path


def test_export_excludes_untracked_private_data_and_owner_metadata(tmp_path):
    root = repo(tmp_path)
    content, count = exporter.source_archive(root)
    assert count == 2
    with tarfile.open(fileobj=io.BytesIO(content), mode='r:gz') as archive:
        files = [m for m in archive if m.isfile()]
        assert {m.name for m in files} == {'wechat-local-mcp/README.md', 'wechat-local-mcp/.gitignore'}
        assert all(m.uid == m.gid == 0 for m in files)


def test_export_refuses_uncommitted_changes(tmp_path):
    root = repo(tmp_path)
    (root / 'README.md').write_text('Unreviewed change')
    with pytest.raises(ValueError, match='tracked changes'):
        exporter.source_archive(root)


def test_export_refuses_local_credential_in_dangling_object(tmp_path):
    root = repo(tmp_path)
    (root / 'data/gadget.token').write_text('synthetic-secret-for-export-123456789')
    git(root, 'hash-object', '-w', 'data/gadget.token')
    with pytest.raises(ValueError, match='Publication check failed'):
        exporter.source_archive(root)
