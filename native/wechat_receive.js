// Read-only observer of live incoming text batches, verified on Build 270134.
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
if (uuid !== '{{.module_uuid}}' || '{{.receiver_mode}}' !== 'native_text_batch') throw new Error('Unsupported receiver profile');
const receiver = base.add({{.receiver_offset}});
const caller = base.add({{.offsets.receiveCaller}});
for (const [address, expected] of [[receiver, '{{.receiver_fingerprint}}'], [caller, '{{.fingerprints.receiveCaller}}']]) {
    const actual = Array.from(new Uint8Array(address.readByteArray(expected.length / 2))).map(x => x.toString(16).padStart(2, '0')).join('');
    if (!expected || actual !== expected) throw new Error('Receiver instruction fingerprint mismatch');
}
let frames = 0, rejected = 0;
const seen = new Map();
function cppString(p, maxBytes) {
    const flag = p.add(23).readU8(), length = flag < 128 ? flag : p.add(8).readU64().toNumber();
    if (length > maxBytes) throw new Error('Native string exceeds limit');
    return (flag < 128 ? p : p.readPointer()).readUtf8String(length);
}
function observeRecord(p) {
    // Only incoming text records. UI copies, drafts, outgoing acknowledgements
    // and media metadata never become incoming text events.
    if (p.add(0x118).readU32() !== 3 || p.add(0x108).readU32() !== 1) return;
    const id = p.add(0xf8).readU64().toString();
    if (id === '0') return;
    const account = cppString(p.add(0x18), 256), chat = cppString(p.add(0x30), 256);
    const sender = cppString(p.add(0x48), 256), text = cppString(p.add(0x130), 65536);
    const timestamp = p.add(0x100).readU64().toNumber();
    if (!account || !chat || !sender || !text || !Number.isSafeInteger(timestamp) || timestamp <= 0) return;
    const key = JSON.stringify([account, chat, id]);
    if (seen.has(key)) return;
    seen.set(key, true);
    if (seen.size > 4096) seen.delete(seen.keys().next().value);
    const group = chat.endsWith('@chatroom');
    frames++;
    send({type: 'send', post_type: 'message', message_type: group ? 'group' : 'private',
          self_id: chat === 'filehelper' ? 'filehelper' : account,
          group_id: group ? chat : '', user_id: group ? sender : chat,
          sender: {user_id: sender, nickname: ''}, message_id: id, time: timestamp,
          message: [{type: 'text', data: {text}}], raw_message: text,
          capture_source: 'native_incoming_text_batch'});
}
Interceptor.attach(receiver, {
    onEnter(args) {
        // Restrict this shared batch function to the observed live receive caller.
        if (!this.returnAddress.equals(caller)) return;
        try {
            const start = args[1].readPointer(), end = args[1].add(8).readPointer();
            if (end.compare(start) < 0) throw new Error('Invalid native batch');
            const bytes = end.sub(start).toUInt32();
            if (bytes > 0x278 * 4096 || bytes % 0x278 !== 0 || !start.add(bytes).equals(end)) throw new Error('Invalid native batch size');
            for (let offset = 0; offset < bytes; offset += 0x278) {
                try { observeRecord(start.add(offset)); } catch (_) { rejected++; }
            }
        } catch (_) { rejected++; }
    }
});
rpc.exports = {
    localStatus() {
        return {hook_verified: true, native_sender_supported: true, send_template_ready: false,
                login_verified: frames > 0, receive_frames: frames, rejected_frames: rejected,
                receive_only: true, receive_scope: 'live incoming text batches; media excluded', module_uuid: uuid};
    }
};
