#!/usr/bin/env python3
"""Exercise Python and Go authentication against a separate dummy Gadget process.

Does not attach to WeChat, load a WeChat hook or send any messages.
Requires downloaded Frida 17.8.0 and the prepared Go/devkit environment.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

import frida
from frida import _frida
from gadget_auth import ensure_token

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.umask(0o077)
    library = ROOT / 'downloads/frida-gadget-17.8.0-macos-universal.dylib'
    if hashlib.sha256(library.read_bytes()).hexdigest() != 'fa67242fa0cee16e80a803703991e81381cd05f7823a4151515460339c942f9f':
        raise ValueError('Unexpected Gadget binary')
    with tempfile.TemporaryDirectory(prefix='wechat-gadget-test-') as tmp:
        directory = Path(tmp)
        token_file = directory / 'gadget.token'
        token = ensure_token(token_file)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        if port == 27042:
            raise ValueError('Refusing the live WeChat port')
        dylib = directory / 'FridaGadget.dylib'
        shutil.copy2(library, dylib)
        (directory / 'FridaGadget.config').write_text(json.dumps({'interaction': {
            'type': 'listen', 'address': '127.0.0.1', 'port': port, 'token': token, 'on_load': 'resume'}}))
        source = directory / 'host.c'
        source.write_text('#include <dlfcn.h>\n#include <unistd.h>\nint main(int n,char **v){if(n!=2||!dlopen(v[1],RTLD_NOW))return 2;for(;;)pause();}\n')
        host = directory / 'host'
        subprocess.run(['/usr/bin/clang', str(source), '-o', str(host)], check=True, capture_output=True)
        process = subprocess.Popen([str(host), str(dylib)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        address = f'127.0.0.1:{port}'
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Isolated Gadget host exited')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError('Isolated Gadget did not start')
            for candidate in (None, 'wrong-token', token):
                manager = frida.core.DeviceManager(_frida.DeviceManager())
                connected = False
                try:
                    device = manager.add_remote_device(address, token=candidate)
                    device.enumerate_processes()
                    connected = True
                except (frida.InvalidArgumentError, frida.PermissionDeniedError, frida.TransportError):
                    pass
                finally:
                    if connected:
                        manager.remove_remote_device(address)
                if connected != (candidate == token):
                    raise RuntimeError('Unexpected Python authentication result for ' + ('correct' if candidate == token else 'absent/wrong') + ' token')
            print('Python: absent/wrong token rejected; correct token accepted.', flush=True)
            devkit = ROOT / 'vendor/wechat_chatter/frida-devkit'
            env = dict(os.environ, GOTOOLCHAIN='go1.26.9', GOMAXPROCS='2', CGO_ENABLED='1',
                       CGO_CFLAGS=f'-I{devkit}', CGO_LDFLAGS=f'-L{devkit} -lfrida-core',
                       WECHAT_TEST_GADGET_ADDR=address, WECHAT_TEST_GADGET_TOKEN_FILE=str(token_file))
            subprocess.run(['nice', '-n', '10', 'go', 'test', '-p=2', '-run', '^TestIsolatedGadgetAuthentication$', '-count=1', '.'],
                           cwd=ROOT / 'vendor/wechat_chatter/onebot', env=env, check=True, timeout=60)
            print('Go: absent/wrong token rejected; correct token accepted.')
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
