"""Publication checks use synthetic repositories and never read user data."""
import subprocess

from check_public_tree import scan


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


def repository(tmp_path):
    git(tmp_path, 'init')
    git(tmp_path, 'config', 'user.name', 'Test Contributor')
    git(tmp_path, 'config', 'user.email', 'test@example.invalid')
    return tmp_path


def test_scans_index_instead_of_unstaged_replacement(tmp_path):
    root = repository(tmp_path)
    token = b'synthetic-private-credential-123456789'
    (root / 'README.md').write_bytes(token)
    git(root, 'add', 'README.md')
    (root / 'README.md').write_text('Clean working copy does not clean the index')
    report = scan(root, secrets=[token])
    assert not report['ok']
    assert report['findings'][0]['rule'] == 'known-local-secret'
    assert token.decode() not in str(report)


def test_removed_private_file_remains_visible_in_history(tmp_path):
    root = repository(tmp_path)
    (root / 'data').mkdir()
    (root / 'data/gadget.token').write_text('synthetic-old-token')
    git(root, 'add', '.')
    git(root, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Synthetic private file')
    git(root, 'rm', 'data/gadget.token')
    git(root, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', 'Remove private file')
    assert scan(root)['ok']
    report = scan(root, history=True)
    assert {'location': 'data/gadget.token', 'rule': 'private-path'} in report['findings']


def test_examples_are_allowed_but_binaries_and_symlinks_are_not(tmp_path):
    root = repository(tmp_path)
    for name in ('config.example.toml', 'mcp.example.json', '.env.example'):
        (root / name).write_text('example')
    git(root, 'add', '.')
    assert scan(root)['ok']
    (root / 'disguised.txt').write_bytes(b'binary\0content')
    (root / 'link').symlink_to('config.example.toml')
    git(root, 'add', '.')
    assert {item['rule'] for item in scan(root)['findings']} == {'binary-content', 'non-regular-file'}


def test_commit_metadata_is_checked(tmp_path):
    root = repository(tmp_path)
    (root / 'README.md').write_text('example')
    git(root, 'add', '.')
    # Construct a private path without putting a real or fixture home in source.
    message = '/'.join(('', 'Users', 'synthetic', 'project'))
    git(root, '-c', 'core.hooksPath=/dev/null', 'commit', '-m', message)
    assert any(item['rule'] == 'personal-home-path' for item in scan(root, history=True)['findings'])


def test_upstream_placeholder_is_allowed_but_other_homes_are_not(tmp_path):
    root = repository(tmp_path)
    (root / 'example.md').write_text('/'.join(('', 'Users', 'xxx', 'project')))
    git(root, 'add', '.')
    assert scan(root)['ok']
    (root / 'example.md').write_text('/'.join(('', 'Users', 'synthetic', 'project')))
    git(root, 'add', '.')
    assert not scan(root)['ok']
