#!/usr/bin/env python3
"""Observe the pinned native save path. No native calls or message writes."""
import frida
import json
import os
from pathlib import Path
import time
import argparse

ROOT = Path(__file__).resolve().parents[1]
os.umask(0o077)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=int, default=1800)
options = parser.parse_args()
directory = ROOT/'artifacts/local-echo'
session = frida.get_device_manager().add_remote_device('127.0.0.1:27042').attach('Gadget')
code = r'''
const mod = Process.enumerateModules().find(x=>x.name==='wechat.dylib'&&x.size>50000000);
const base = mod.base;
function cppstr(p) {
    try {
        const flag=p.add(23).readU8();
        const length=flag<128?flag:p.add(8).readU64().toNumber();
        if(length<1||length>1024)return null;
        const a=flag<128?p:p.readPointer();
        return a.readUtf8String(length);
    }catch(e){return null;}
}
let counts = {};
function observe(p, kind, context, extra={}) {
    try {
        const fields = {};
        for (const o of [0x18,0x30,0x48,0x60,0x78,0xc0,0xd8,0x130,0x148,0x160]) {
            const t=cppstr(p.add(o)); if(t) fields['0x'+o.toString(16)]=t;
        }
        if(!Object.values(fields).some(t=>t.includes('LECHO-')))return;
        send({kind,pid:Process.id,thread:Process.getCurrentThreadId(),pointer:String(p),
              fields,record:Array.from(new Uint8Array(p.readByteArray(0x268))),...extra,
              backtrace:Thread.backtrace(context,Backtracer.ACCURATE).map(a=>String(a.sub(base)))});
    } catch(e) { send({kind:'error',error:String(e)}); }
}
for (const [kind,offset] of [['save',0x2afc210],['store',0x2c1c52c]]) Interceptor.attach(base.add(offset), {
    onEnter(args) {
        counts[kind]=(counts[kind]||0)+1;
        try {
            const start=args[1].readPointer(), end=args[1].add(8).readPointer();
            const size=end.sub(start).toInt32();
            if(size<0||size>0x268*100||size%0x268!==0)return;
            for(let n=0;n<size;n+=0x268) {
                observe(start.add(n),kind,this.context,{manager:String(args[0]),flags:[args[2].toInt32(),args[3].toInt32()]});
            }
        }catch(e){send({kind:'error',error:String(e)});}
    }
});
Interceptor.attach(base.add(0xd1ee1c), {
    onEnter(args) { counts.copy=(counts.copy||0)+1;observe(args[1],'copy',this.context); }
});
setInterval(()=>send({kind:'counts',counts}),15000);
send({kind:'attached',pid:Process.id,base:String(base)});
'''
script=session.create_script(code)
def message(value,data):
    with (directory/'native-observations.jsonl').open('a') as out:
        out.write(json.dumps(value,ensure_ascii=False)+'\n')
    payload=value.get('payload',{})
    print(json.dumps({'type':value.get('type'),'kind':payload.get('kind'),'thread':payload.get('thread')},ensure_ascii=False),flush=True)
script.on('message',message)
try:
    script.load()
    time.sleep(options.seconds)
finally:
    script.unload()
    session.detach()
