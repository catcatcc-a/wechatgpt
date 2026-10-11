// Pinned WeChat 4.1.11.53 ARM64 native text pipeline; offsets are build-specific.
'use strict';
const module = Process.enumerateModules().find(m => m.name === 'wechat.dylib' && m.size > 50000000);
if (!module || Process.arch !== 'arm64') throw new Error('Unsupported native module');
const base = module.base;
if(base.readU32()!==0xfeedfacf)throw new Error('Invalid native Mach-O header');
let moduleUuid = null, command = base.add(32);
for(let i=0;i<base.add(16).readU32();i++) {
    if(command.readU32()===0x1b)moduleUuid=Array.from(new Uint8Array(command.add(8).readByteArray(16))).map(x=>x.toString(16).padStart(2,'0')).join('');
    command=command.add(command.add(4).readU32());
}
if(typeof EXPECTED_MODULE_UUID==='undefined'||moduleUuid!==EXPECTED_MODULE_UUID)throw new Error('Unsupported WeChat native build UUID');
const keep = [];
const callbacks = new Map();
const makeNative = (offset, result, args) => new NativeFunction(base.add(offset), result, args);
const allocate = makeNative(0x67b35b0, 'pointer', ['uint64']);
const release = makeNative(0x67b358c, 'void', ['pointer', 'uint64']);
const taskCtor = makeNative(0x32718, 'void', ['pointer', 'pointer', 'pointer']);
const post = makeNative(0x436e480, 'uint64', ['pointer', 'pointer', 'pointer', 'int']);
const location = Memory.alloc(32);
const locationName = Memory.allocUtf8String('WeChatLocalMCP');
location.writePointer(locationName); location.add(8).writePointer(locationName);
location.add(16).writeU32(1); location.add(24).writePointer(base.add(0x436e480));
keep.push(location, locationName);

function sret(offset, argc) {
    const code = Memory.alloc(Process.pageSize);
    Memory.patchCode(code, 128, address => {
        const w = new Arm64Writer(address, {pc: code});
        w.putMovRegReg('x8', 'x0');
        for(let i=0;i<argc;i++) w.putMovRegReg('x'+i, 'x'+(i+1));
        w.putLdrRegAddress('x16',base.add(offset)); w.putBrReg('x16'); w.flush();
    });
    keep.push(code);
    return new NativeFunction(code, 'void', Array(argc+1).fill('pointer'));
}

function queued(fn) {
    return new Promise((resolve,reject) => {
        const task = allocate(0x28), owner = Memory.alloc(8);
        const invoke = new NativeCallback(() => {
            try { resolve(fn()); } catch(e) { reject(e); }
        }, 'void', ['pointer']);
        const destroy = new NativeCallback(p => {
            release(p,0x28); callbacks.delete(String(p));
        }, 'void', ['pointer']);
        callbacks.set(String(task),{invoke,destroy,owner});
        taskCtor(task,invoke,destroy); owner.writePointer(task);
        const id=post(location,owner,ptr(0),1);
        if(id.toString()==='0')reject(new Error('WeChat rejected the native UI task'));
    });
}

function cppstr(p) {
    const flag=p.add(23).readU8(), size=flag<128?flag:p.add(8).readU64().toNumber();
    if(size>8192)throw new Error('Invalid native string');
    return (flag<128?p:p.readPointer()).readUtf8String(size);
}
const paramCtor = makeNative(0x6bdd8c,'pointer',['pointer']);
const stringAssign = makeNative(0x67b2e3c,'pointer',['pointer','pointer']);
const pairRelease = makeNative(0x12aeb4,'void',['pointer']);
const nativeSubmit = makeNative(0x399a8b0,'void',['pointer','pointer']);
let pending = null;
Interceptor.attach(base.add(0xd1ee1c), {onEnter(a) {
    if(!pending)return;
    try {
        const p=a[1];
        if(cppstr(p.add(0x30))!==pending.chatId||cppstr(p.add(0x130))!==pending.text)return;
        if(pending.messageKey && cppstr(p.add(0x250))!==pending.messageKey)return;
        const state=p.add(0x118).readU32(), serverId=p.add(0xf8).readU64().toString();
        if(state===2&&serverId!=='0') {
            const current=pending;pending=null;
            current.resolve({status:'server_ack',server_id:serverId,local_id:p.add(0xf4).readU32(),state,thread:Process.getCurrentThreadId()});
        }
    }catch(e){}
}});
function assign(p,text) {
    const raw=Memory.allocUtf8String(text), temp=Memory.alloc(24);
    const size=unescape(encodeURIComponent(text)).length;
    temp.writePointer(raw);temp.add(8).writeU64(size);temp.add(16).writeU64(uint64('0x8000000000000000').add(size+1));
    stringAssign(p,temp);
}
function parameters(text,chatId='filehelper') {
    const block=allocate(0x5c8);paramCtor(block);
    const p=block.add(0x18),pair=Memory.alloc(16);
    pair.writePointer(p);pair.add(8).writePointer(block);
    assign(p.add(0x90),chatId);assign(p.add(0x580),text);
    p.add(0xb0).writeU32(1);p.add(0xb4).writeU32(0);
    return {p,pair};
}
rpc.exports = {
    drain: () => new Promise(resolve => {
        const poll=setInterval(()=>{if(callbacks.size===0){clearInterval(poll);resolve(true);}},25);
    }),
    probe: () => queued(() => ({thread:Process.getCurrentThreadId(),pending:callbacks.size})),
    prepare: text => queued(() => {
        const {p,pair}=parameters(text);
        const result={recipient:cppstr(p.add(0x90)),text:cppstr(p.add(0x580)),message_key:cppstr(p.add(0x538)),type:p.add(0xb0).readU32(),vtable:String(p.readPointer().sub(base))};
        pairRelease(pair);return result;
    }),
    sendText: (chatId,text) => {
        if(pending)throw new Error('A native send is already pending');
        if(typeof chatId!=='string'||! /^(filehelper|wxid_[A-Za-z0-9_-]+|[A-Za-z0-9_-]+@chatroom)$/.test(chatId))throw new Error('Invalid canonical WeChat recipient');
        if(typeof text!=='string'||!text.trim()||text.length>2000||text.includes('\0'))throw new Error('Text must contain 1..2000 characters without NUL');
        return new Promise((resolve,reject) => {
            const state={text,chatId,resolve,reject};pending=state;
            queued(() => {
                const {p,pair}=parameters(text,chatId),request=Memory.alloc(32),callback=Memory.alloc(0x88),flagOwner=allocate(0x20);
                // Native shared ownership with a trivial scalar destructor and
                // sized 0x20-byte deleter. All callback copies retain this owner.
                flagOwner.writePointer(base.add(0x8fe91c0));
                flagOwner.add(8).writeU64(0);flagOwner.add(16).writeU64(0);flagOwner.add(24).writeU64(0);
                const done=flagOwner.add(24);
                state.messageKey=cppstr(p.add(0x538));
                request.add(8).writePointer(pair);request.add(16).writePointer(pair.add(16));request.add(24).writePointer(pair.add(16));
                callback.writePointer(done);callback.add(8).writePointer(flagOwner);callback.add(0x70).writeU64(Date.now()*1000+Math.floor(Math.random()*1000));
                keep.push(request,callback,done,pair);
                nativeSubmit(request,callback);
                pairRelease(pair);
                pairRelease(callback);
                return {submitted:true};
            }).catch(e=>{if(pending===state)pending=null;reject(e);});
            setTimeout(()=>{if(pending===state){pending=null;resolve({status:'unverified',automatic_retry:false});}},20000);
        });
    },
};
