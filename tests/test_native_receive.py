"""Exercise the native receiver with synthetic memory, without touching WeChat."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_incoming_batches_are_bounded_filtered_and_deduplicated():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed for the isolated Frida-script harness')
    script = Path(__file__).parents[1] / 'native/wechat_receive.js'
    harness = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const memory = new Map(), strings = new Map(), events = [];
let next = 0x100000n, hook;
class P {
 constructor(n) { this.n = BigInt(n); }
 add(n) { return new P(this.n + BigInt(n)); }
 sub(p) { return new P(this.n - p.n); }
 equals(p) { return this.n === p.n; }
 compare(p) { return this.n < p.n ? -1 : this.n > p.n ? 1 : 0; }
 toUInt32() { return Number(BigInt.asUintN(32, this.n)); }
 readPointer() { return new P(memory.get(this.n) ?? 0n); }
 readU8() { return Number(memory.get(this.n) ?? 0n); }
 readU32() { return this.readU8(); }
 readU64() { const n = memory.get(this.n) ?? 0n; return {toString:()=>String(n),toNumber:()=>Number(n)}; }
 readUtf8String(n) { const s = strings.get(this.n); if (s === undefined || Buffer.byteLength(s) !== n) throw Error('invalid string'); return s; }
}
const caller = new P(0x1234), receiver = new P(0x5678);
function set(p, o, v) { memory.set(p.n + BigInt(o), BigInt(v)); }
function str(p, o, s) { const q=p.add(o),len=Buffer.byteLength(s); if(len<=23){set(q,23,len);strings.set(q.n,s);}else{const a=next;next+=BigInt(len+64);set(q,0,a);set(q,8,len);set(q,23,128);strings.set(a,s);} }
function record(p, id, opts={}) {
 set(p,0x118,opts.state??3);set(p,0x108,opts.type??1);set(p,0xf8,id);set(p,0x100,1791720000000);
 str(p,0x18,'wxid_test_account');str(p,0x30,opts.chat??'filehelper');str(p,0x48,opts.sender??'wxid_test_sender');str(p,0x130,opts.text??'synthetic message');
}
const context={Uint8Array,Map,Number,JSON,Error,receiver,caller,uuid:'synthetic',send:e=>events.push(e),rpc:{exports:{}},Interceptor:{attach:(_,h)=>hook=h}};
vm.createContext(context);
const source=fs.readFileSync(process.argv[1],'utf8');vm.runInContext(source.slice(source.indexOf('let frames =')),context);
function batch(start,count,returnAddress=caller,delta=0n){const vector=new P(0x9000);set(vector,0,start.n);set(vector,8,start.n+BigInt(count)*0x278n+delta);hook.onEnter.call({returnAddress},[new P(0),vector]);}
const start=new P(0x20000);record(start,100);
batch(start,1,new P(1));assert.equal(events.length,0);
batch(start,1);batch(start,1);assert.equal(events.length,1);assert.equal(events[0].self_id,'filehelper');assert.equal(events[0].user_id,'filehelper');
record(start,101,{type:3});batch(start,1);record(start,102,{state:2});batch(start,1);assert.equal(events.length,1);
record(start,103,{chat:'12345@chatroom'});record(start.add(0x278),104,{chat:'wxid_friend'});batch(start,2);assert.equal(events.length,3);
assert.equal(events[1].group_id,'12345@chatroom');assert.equal(events[1].user_id,'wxid_test_sender');assert.equal(events[2].user_id,'wxid_friend');
record(start,105);batch(start,1,caller,1n);batch(start,1,caller,0x100000000n);assert.equal(events.length,3);assert.equal(context.rpc.exports.localStatus().rejected_frames,2);
record(start,106,{text:'x'.repeat(65537)});batch(start,1);assert.equal(events.length,3);assert.equal(context.rpc.exports.localStatus().rejected_frames,3);
assert.equal(context.rpc.exports.localStatus().login_verified,true);
console.log('native receive bounds, routing, filtering and deduplication passed');
'''
    result = subprocess.run([node, '-e', harness, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
