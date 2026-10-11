#!/usr/bin/env python3
"""Read-only ARM64 Mach-O inspection for the pinned WeChat build."""
from pathlib import Path
import argparse
import bisect
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/wechat_chatter/tools/addrfind'))
from addrfind import MachO
from string_anchor import adrp_target
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM


class Binary(MachO):
    def __init__(self, path):
        super().__init__(path)
        self.starts = []
        lc = self.off + 32
        self.code_start, self.code_size = self.text_vmaddr, len(self.text_bytes)
        for _ in range(struct.unpack_from('<I', self.data, self.off + 16)[0]):
            cmd, size = struct.unpack_from('<II', self.data, lc)
            if cmd == 0x19:
                nsects = struct.unpack_from('<I', self.data, lc + 64)[0]
                for n in range(nsects):
                    sec = lc + 72 + n * 80
                    if self.data[sec:sec+16].rstrip(b'\0') == b'__text':
                        self.code_start, self.code_size = struct.unpack_from('<QQ', self.data, sec + 32)
            if cmd == 0x26:
                offset, count = struct.unpack_from('<II', self.data, lc + 8)
                addr = self.text_vmaddr
                delta = shift = 0
                for b in self.data[self.off+offset:self.off+offset+count]:
                    delta |= (b & 127) << shift
                    if b & 128:
                        shift += 7
                    else:
                        if not delta: break
                        addr += delta; self.starts.append(addr)
                        delta = shift = 0
            lc += size
        self.dis = Cs(CS_ARCH_ARM64, CS_MODE_ARM)

    def function(self, addr):
        idx = bisect.bisect_right(self.starts, addr) - 1
        return self.starts[idx], self.starts[idx+1] if idx+1 < len(self.starts) else self.code_start+self.code_size

    def listing(self, start, end):
        return '\n'.join(f'{i.address:#x}  {i.mnemonic:8} {i.op_str}' for i in self.dis.disasm(self.read_at(start,end-start),start))

    def page_refs(self, target):
        page = target & ~4095
        code = self.read_at(self.code_start, self.code_size)
        for off, (word,) in enumerate(struct.iter_unpack('<I',code[:len(code)//4*4])):
            addr = self.code_start + off * 4
            if adrp_target(word,addr) == page:
                yield addr


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['refs','disasm','strings']);p.add_argument('target');p.add_argument('--size',type=lambda x:int(x,0),default=256)
    args=p.parse_args();m=Binary(ROOT/'artifacts/local-echo/wechat-arm64.dylib')
    if args.mode=='strings':
        data=m.text_bytes;start=0
        while True:
            at=data.find(args.target.encode(),start)
            if at<0:break
            print(hex(m.text_vmaddr+at),repr(data[at:at+args.size]));start=at+1
    else:
        addr=int(args.target,0)
        if args.mode=='disasm':
            print('function',*[hex(a) for a in m.function(addr)]);print(m.listing(addr,addr+args.size))
        else:
            for at in m.page_refs(addr):
                print('function',*[hex(a) for a in m.function(at)]);print(m.listing(at,at+32))

if __name__=='__main__':main()
