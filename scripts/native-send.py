#!/usr/bin/env python3
"""One native background send, configured and launched by the MCP adapter.

Reads one JSON object from stdin; never takes message text from shell arguments.
The MCP's durable outgoing ledger owns retry decisions. This helper never retries.
"""
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import sys
import time
from gadget_auth import connect
from native_profile import load_profile, sender_code

ROOT = Path(__file__).resolve().parents[1]


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError('Expected a JSON object')
    chat = payload.get('chat_id', '')
    text = payload.get('text', '')
    if not isinstance(chat, str) or not re.fullmatch(r'filehelper|wxid_[A-Za-z0-9_-]+|[A-Za-z0-9_-]+@chatroom', chat):
        raise ValueError('Use a canonical wxid, group ID, or filehelper')
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le')) > 4000 or '\0' in text:
        raise ValueError('Text must contain 1..2000 UTF-16 code units without NUL')
    return chat, text


def preflight():
    return load_profile(root=ROOT)[0]


def main():
    os.umask(0o077)
    attempted = False
    script = session = None
    try:
        payload = json.loads(sys.stdin.read(32000))
        chat, text = validate(payload)
        manifest = preflight()
        import frida
        lock_dir = Path.home() / 'Library/Application Support/WeChatLocalMCP/data'
        lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (lock_dir / 'native-send.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            session = connect(frida).attach('Gadget')
            script = session.create_script(sender_code(manifest, ROOT))
            script.load()
            script.exports_sync.probe()
            attempted = True
            result = script.exports_sync.send_text(chat, text)
            acknowledged = result.get('status') == 'server_ack'
            result.update(chat_id=chat, backend='wechat_native', desktop_send_echo=True,
                          delivery_status='unverified', automatic_retry=False,
                          transmission='accepted' if acknowledged else 'unknown',
                          local_record_confirmed=acknowledged and result.get('local_id', 0) > 0,
                          message=('Native WeChat recorded the send and its server acknowledgement. Recipient receipt is not independently confirmed.'
                                   if acknowledged else 'No matched native acknowledgement was observed before timeout. Do not automatically resend.'))
            # Allow native callbacks to finish before detaching the observer.
            time.sleep(1)
    except Exception as exc:
        result = {'delivery_status': 'unverified' if attempted else 'failed',
                  'transmission': 'unknown' if attempted else 'not_sent',
                  'automatic_retry': False, 'error': str(exc)}
    finally:
        if script:
            try:
                # Do not free NativeCallbacks while a queued UI task still owns
                # them, including after a timeout. A stalled helper may wait in
                # the background; the MCP reports unknown and never resends.
                script.exports_sync.drain()
                script.unload()
            except Exception:
                pass  # A terminated WeChat process has no live native tasks.
        if session:
            try:
                session.detach()
            except Exception:
                pass
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
