#!/usr/bin/env python3
"""Check the Git index, optionally all reachable history, without printing secrets.

This is a small project-specific publication check, not a comprehensive secret
scanner. Untracked files, reflogs and unreachable objects are outside its scope.
"""
import argparse
import fnmatch
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


PRIVATE_DIRS = {
    'data', 'artifacts', 'evidence', 'logs', 'runtime', 'backups', 'downloads',
    'bin', '.venv', '.re-venv', '.secrets', '__pycache__', 'dist', 'build',
}
PRIVATE_NAMES = {'AGENTS.md', 'config.toml', 'config.onebot.toml', 'mcp.json', '.DS_Store'}
PRIVATE_GLOBS = ('*.token', '*.key', '*.pem', '*.log', '*.db*', '*.sqlite*',
                 '*.dmg', '*.dylib', '*.a', '*.png', '*.jpg', '*.zip', '*.local.toml')
PATTERNS = {
    'private-key': re.compile(rb'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    # The upstream patch uses a literal home-directory placeholder named xxx.
    'personal-home-path': re.compile(rb'/(?:Users|home)/(?!xxx/)[A-Za-z0-9][A-Za-z0-9._-]*/'),
}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def private_path(name):
    path = PurePosixPath(name)
    return (
        any(part in PRIVATE_DIRS or part.endswith('.app') for part in path.parts)
        or path.name in PRIVATE_NAMES
        or (path.name.startswith('.env') and path.name != '.env.example')
        or any(fnmatch.fnmatch(path.name, pattern) for pattern in PRIVATE_GLOBS)
        or (path.parts[0] == 'vendor' and name != 'vendor/UPSTREAM_NOTES.md')
    )


def scan(root, history=False, secrets=()):
    findings, objects, checked = set(), set(), set()

    def inspect(oid, kind):
        if oid in checked:
            return
        checked.add(oid)
        data = git(root, 'cat-file', kind, oid)
        for rule, pattern in PATTERNS.items():
            if pattern.search(data):
                findings.add((oid, rule))
        if kind == 'blob' and b'\0' in data:
            findings.add((oid, 'binary-content'))
        if any(secret in data for secret in secrets):
            findings.add((oid, 'known-local-secret'))

    def paths(entries):
        for entry in entries.split(b'\0'):
            if not entry:
                continue
            header, raw_name = entry.split(b'\t', 1)
            mode, middle, last = header.decode().split()
            # Index: mode oid stage. Tree: mode type oid.
            oid = last if middle in {'blob', 'commit'} else middle
            name = raw_name.decode('utf-8', errors='replace')
            if private_path(name):
                findings.add((name, 'private-path'))
            if mode not in {'100644', '100755'}:
                findings.add((name, 'non-regular-file'))
            if middle not in {'blob', 'commit'} and last != '0':
                findings.add((name, 'unmerged-index'))
            if mode in {'100644', '100755', '120000'}:
                objects.add(oid)

    # Scan staged bytes, not potentially different working-tree content.
    paths(git(root, 'ls-files', '--stage', '-z'))
    if history:
        if git(root, 'rev-parse', '--is-shallow-repository').strip() == b'true':
            findings.add(('history', 'shallow-history'))
        commits = git(root, 'rev-list', '--all').decode().splitlines()
        for oid in commits:
            inspect(oid, 'commit')
            paths(git(root, 'ls-tree', '-rz', '--full-tree', oid))
        # Include annotated tag messages and all reachable blob objects too.
        for oid in git(root, 'rev-list', '--objects', '--all', '--no-object-names').decode().splitlines():
            kind = git(root, 'cat-file', '-t', oid).decode().strip()
            if kind in {'blob', 'tag'}:
                inspect(oid, kind)
    for oid in sorted(objects):
        inspect(oid, 'blob')
    return {'ok': not findings, 'scope': 'index_and_reachable_history' if history else 'index',
            'checked_objects': len(checked),
            'findings': [{'location': location, 'rule': rule} for location, rule in sorted(findings)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--history', action='store_true')
    parser.add_argument('--secret-file', action='append', type=Path, default=[],
                        help='Compare a local token file without printing its contents; repeatable')
    args = parser.parse_args()
    root = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
    secrets = []
    for path in args.secret_file:
        value = path.read_bytes().strip()
        if len(value) < 16:
            parser.error('Secret files must contain at least 16 bytes')
        secrets.append(value)
    result = scan(root, args.history, secrets)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
