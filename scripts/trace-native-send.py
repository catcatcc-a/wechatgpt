#!/usr/bin/env python3
"""Read-only observation of native File Transfer Assistant send parameters."""
import frida
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.umask(0o077)
session = frida.get_device_manager().add_remote_device('127.0.0.1:27042').attach('Gadget')
script = session.create_script(r'''
const m=Process.enumerateModules().find(m=>m.name==='wechat.dylib'&&m.size>50000000),b=m.base;
function str(p) {
    try {
        const f=p.add(23).readU8(),n=f<128?f:p.add(8).readU64().toNumber();
        return n>0&&n<1000?(f<128?p:p.readPointer()).readUtf8String(n):null;
    }catch(e){return null;}
}
Interceptor.attach(b.add(0x2aebe7c),{onEnter(a){
    try {
        const p=a[1].readPointer();
        if(str(p.add(0x90))!=='filehelper')return;
        const fields={};for(let o=8;o<0x300;o+=8){const t=str(p.add(o));if(t)fields['0x'+o.toString(16)]=t;}
        const vt=p.readPointer(),methods=[];
        for(let o=0;o<0x80;o+=8)methods.push(String(vt.add(o).readPointer().sub(b)));
        send({kind:'native_send',manager:String(a[0]),thread:Process.getCurrentThreadId(),
              fields,methods,vtable:String(vt.sub(b)),pointer:String(p),
              bytes:Array.from(new Uint8Array(p.readByteArray(0x300))),
              stack:Thread.backtrace(this.context,Backtracer.ACCURATE).map(x=>String(x.sub(b)))});
    }catch(e){send({kind:'error',error:String(e)});}
}});
send({kind:'attached'});
''')
def message(m,data):
    with (ROOT/'artifacts/local-echo/send-parameters.jsonl').open('a') as f:
        f.write(json.dumps(m,ensure_ascii=False)+'\n')
    print(m.get('payload',{}).get('kind',m.get('type')),flush=True)
script.on('message',message)
try:
    script.load()
    time.sleep(1800)
finally:
    script.unload()
    session.detach()
