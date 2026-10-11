"""Select an exact native ABI profile; unknown builds are never guessed."""
import json
import os
from pathlib import Path
import plistlib
import struct

ROOT = Path(__file__).resolve().parents[1]


def load_profile(app=Path('/Applications/WeChat.app'), root=ROOT):
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    version = str(info.get('CFBundleShortVersionString', ''))
    build = str(info.get('CFBundleVersion', ''))
    for path in (root / 'native').glob('wechat-*.json'):
        profile = json.loads(path.read_text())
        if profile['build'] == build and version in {profile['version'], '.'.join(profile['version'].split('.')[:3])}:
            if not profile.get('runtime_verified') and os.environ.get('WECHAT_ALLOW_EXPERIMENTAL') != build:
                raise ValueError('This exact WeChat build is still awaiting controlled runtime validation')
            return profile, path
    raise ValueError('Installed WeChat build has no native ABI profile; no attach attempted')


def sender_code(profile, root=ROOT):
    return 'const PROFILE=' + json.dumps(profile) + ';\n' + (root / 'native/wechat_send.js').read_text()


def verify_binary_profile(path, profile):
    """Read only Mach-O headers and checked instruction sites, including FAT64."""
    with Path(path).open('rb') as stream:
        head = stream.read(8)
        magic, count = struct.unpack('>II', head)
        offset = 0
        if magic in {0xcafebabe, 0xcafebabf}:
            width = 20 if magic == 0xcafebabe else 32
            for _ in range(count):
                arch = stream.read(width)
                if struct.unpack_from('>I', arch)[0] == 0x100000c:
                    offset = struct.unpack_from('>I' if width == 20 else '>Q', arch, 8)[0]
                    break
            else:
                raise ValueError('No ARM64 Mach-O slice')
        stream.seek(offset)
        header = stream.read(32)
        if struct.unpack_from('<II', header) != (0xfeedfacf, 0x100000c):
            raise ValueError('Expected ARM64 Mach-O')
        commands = stream.read(struct.unpack_from('<I', header, 20)[0])
        cursor, uuid, segments = 0, None, []
        for _ in range(struct.unpack_from('<I', header, 16)[0]):
            command, size = struct.unpack_from('<II', commands, cursor)
            if command == 0x1b:
                uuid = commands[cursor+8:cursor+24].hex()
            if command == 0x19:
                segments.append(struct.unpack_from('<QQQQ', commands, cursor+24))
            cursor += size
        if uuid != profile['module_uuid']:
            raise ValueError('WeChat core module UUID does not match its ABI profile')
        sites = [(profile['offsets'][name], value) for name, value in profile['fingerprints'].items()]
        if profile.get('receiver_offset'):
            sites.append((profile['receiver_offset'], profile['receiver_fingerprint']))
        for address, fingerprint in sites:
            address, expected = int(address, 16), bytes.fromhex(fingerprint)
            for vm, _, file_offset, file_size in segments:
                if vm <= address and address + len(expected) <= vm + file_size:
                    stream.seek(offset + file_offset + address - vm)
                    if stream.read(len(expected)) != expected:
                        raise ValueError('WeChat instruction fingerprint mismatch')
                    break
            else:
                raise ValueError('Instruction offset is outside the mapped file')
