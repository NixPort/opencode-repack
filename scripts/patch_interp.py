#!/usr/bin/env python3
"""Set the ELF interpreter (PT_INTERP) of a program.

Android has no /lib/ld-linux-aarch64.so.1, and the nixport guest is not a
chroot: the guest sees the phone's own root, where the loader of the rootfs
is not. A Linux program that runs in the guest therefore has to be started
through the path the app actually keeps its loader at.

A longer path than the one in the file is fine: the new string is appended to
the file and the program header points at it, so nothing else moves.

    python3 patch_interp.py <file> <interpreter path> [--dry-run] [--verbose]

Idempotent: a file that already has the path is left alone.
"""
import argparse
import os
import struct
import sys
from pathlib import Path

PT_INTERP = 3
ELF = b'\x7fELF'


def interp_of(path):
    """The interpreter a file asks for, read from its header only"""
    with path.open('rb') as f:
        head = f.read(64)
        if len(head) < 64 or head[:4] != ELF:
            return None
        if head[4] != 2 or head[5] != 1:
            return None                      # only aarch64 little-endian is handled
        phoff, = struct.unpack_from('<Q', head, 32)
        phentsize, phnum = struct.unpack_from('<HH', head, 54)
        f.seek(phoff)
        ph = f.read(phentsize * phnum)
        if len(ph) < phentsize * phnum:
            return None
        for i in range(phnum):
            p = phoff + i * phentsize
            q = i * phentsize
            p_type, = struct.unpack_from('<I', ph, q)
            if p_type != PT_INTERP:
                continue
            p_offset, = struct.unpack_from('<Q', ph, q + 8)
            p_filesz, = struct.unpack_from('<Q', ph, q + 32)
            f.seek(p_offset)
            s = f.read(p_filesz).split(b'\0')[0].decode('utf-8', 'replace')
            return p, p_offset, p_filesz, s
    return None


def patch(path, interp, dry=False, verbose=False):
    """Sets the interpreter of one file; True when the file changed"""
    got = interp_of(path)
    if not got:
        return False
    p, p_offset, p_filesz, cur = got
    if cur == interp:
        return False
    if verbose:
        print(f'  {path}: {cur} -> {interp}')
    if dry:
        return True
    data = bytearray(path.read_bytes())
    new = interp.encode() + b'\0'
    at = (len(data) + 7) & ~7                 # the string starts at an aligned offset
    data += b'\0' * (at - len(data))
    data += new
    # the program header: p_offset, then p_filesz and p_memsz (the string's length)
    struct.pack_into('<Q', data, p + 8, at)
    struct.pack_into('<Q', data, p + 32, len(new))
    struct.pack_into('<Q', data, p + 40, len(new))
    tmp = path.with_name(path.name + '.interp-tmp')
    tmp.write_bytes(bytes(data))
    os.chmod(tmp, os.stat(path).st_mode & 0o777)
    os.replace(tmp, path)                     # a crash in the middle leaves the old file alone
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('interp')
    ap.add_argument('--dry-run', dest='dry', action='store_true')
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args()
    path = Path(a.file)
    if not path.is_file():
        print(f'no such file: {path}', file=sys.stderr)
        return 1
    if patch(path, a.interp, a.dry, a.verbose):
        print(f'patched {path}')
        return 0
    print(f'{path} already asks for {a.interp}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
