// Receive-only profile: no task replacement, native writes or media hooks.
// Go text/template substitutes the exact ABI manifest before loading.
'use strict';
const module = Process.enumerateModules().find(m => m.name === 'wechat.dylib' && m.size > 50000000);
if (!module || Process.arch !== 'arm64') throw new Error('Unsupported receiver module');
const base = module.base;
if (base.readU32() !== 0xfeedfacf) throw new Error('Invalid Mach-O header');
let uuid = null, command = base.add(32);
for (let i = 0; i < base.add(16).readU32(); i++) {
    if (command.readU32() === 0x1b) uuid = Array.from(new Uint8Array(command.add(8).readByteArray(16))).map(x => x.toString(16).padStart(2, '0')).join('');
    command = command.add(command.add(4).readU32());
}
if (uuid !== '{{.module_uuid}}') throw new Error('Unsupported receiver UUID');
const receiver = base.add({{.receiver_offset}});
const expected = '{{.receiver_fingerprint}}';
const actual = Array.from(new Uint8Array(receiver.readByteArray(expected.length / 2))).map(x => x.toString(16).padStart(2, '0')).join('');
if (!expected || actual !== expected) throw new Error('Receiver instruction fingerprint mismatch');
let frames = 0, rejected = 0;
Interceptor.attach(receiver, {
    onEnter() {
        try {
            // At this checked instruction the original AutoBufferWrite has
            // returned its byte count in x0; x20 still owns the source bytes.
            const size = this.context.x0.toInt32();
            if (size < 4 || size > 2 * 1024 * 1024) return;
            const data = new Uint8Array(this.context.x20.readByteArray(size));
            if (data[0] !== 0x08) return;
            frames++;
            send({type: 'protobuf_msg', data: Array.from(data)});
        } catch (_) { rejected++; }
    }
});
rpc.exports = {
    localStatus() {
        return {hook_verified: true, native_sender_supported: true, send_template_ready: false,
                login_verified: false, receive_frames: frames, rejected_frames: rejected,
                receive_only: true, module_uuid: uuid};
    }
};
