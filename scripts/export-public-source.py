#!/usr/bin/env python3
"""Export only a clean, privacy-checked Git HEAD; never zip the working folder."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

from check_public_tree import git, scan


def source_archive(root):
    if git(root, 'status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('Commit or resolve tracked changes before exporting source')
    credentials = []
    for name in ('gadget.token', 'onebot.token'):
        path = root / 'data' / name
        if path.is_file():
            value = path.read_bytes().strip()
            if len(value) < 16:
                raise ValueError('Local credential file is empty or malformed')
            credentials.append(value)
    result = scan(root, secrets=credentials, all_objects=True)
    if not result['ok']:
        raise ValueError('Publication check failed; run scripts/check-publication.sh for opaque finding IDs')
    archive = git(root, 'archive', '--format=tar.gz', '--prefix=wechat-local-mcp/', 'HEAD')
    expected = {p for p in git(root, 'ls-files', '-z').split(b'\0') if p}
    found = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as handle:
        for member in handle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != 'wechat-local-mcp':
                raise ValueError('Unexpected archive path')
            if member.uid != 0 or member.gid != 0 or member.uname not in ('', 'root') or member.gname not in ('', 'root'):
                raise ValueError('Archive contains local ownership metadata')
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError('Archive contains a non-regular entry')
            found.add(str(PurePosixPath(*path.parts[1:])).encode())
    if found != expected:
        raise ValueError('Archive file list does not match the checked Git tree')
    return archive, len(found)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='A new file in an ignored directory within this checkout')
    args = parser.parse_args()
    root = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
    target = args.output.absolute()
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        parser.error('Output must stay inside this checkout and cannot be a symlink')
    relative = str(target.relative_to(root))
    ignored = subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', '--', relative])
    if ignored.returncode != 0:
        parser.error('Choose an ignored output path, for example artifacts/open-source-review/source.tar.gz')
    archive, count = source_archive(root)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with target.open('xb') as stream:
        stream.write(archive)
    print(json.dumps({'commit': git(root, 'rev-parse', 'HEAD').decode().strip(),
                      'files': count, 'sha256': hashlib.sha256(archive).hexdigest(),
                      'output': relative, 'includes_git_metadata': False}))


if __name__ == '__main__':
    main()
