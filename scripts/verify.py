#!/usr/bin/env python3
"""Check that a program can start in a rootfs.

Two things have to hold, and both are the difference between a program that
runs on the phone and one that dies with "cannot open shared object file":

1. every library the program wants (DT_NEEDED) is in the rootfs, and
2. the interpreter it asks for is the loader of that rootfs.

    python3 verify.py --binary <program> --rootfs <rootfs dir> [--interp <path>]

The rootfs is the tree the app unpacks (the payload's rootfs). The loader
path the app uses is the app's own: /data/data/<package>/files/rootfs/...
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from elf import Elf  # noqa: E402

# where the libraries of a Debian rootfs live, the multiarch directory first
LIB_DIRS = ['usr/lib/aarch64-linux-gnu', 'lib/aarch64-linux-gnu', 'usr/lib', 'lib', 'usr/lib64']


def provided(rootfs):
    """The libraries the rootfs has, by name (a link counts as the file it points at)"""
    out = set()
    for d in LIB_DIRS:
        base = rootfs / d
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if '.so' not in p.name:
                continue
            out.add(p.name)
            try:
                out.add(os.path.basename(os.path.realpath(p)))
            except OSError:
                pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', required=True)
    ap.add_argument('--rootfs', required=True)
    ap.add_argument('--interp', default='', help='the interpreter path the program must ask for')
    a = ap.parse_args()

    binary = Path(a.binary)
    rootfs = Path(a.rootfs)
    if not binary.is_file():
        print(f'no such program: {binary}', file=sys.stderr)
        return 1
    if not rootfs.is_dir():
        print(f'no such rootfs: {rootfs}', file=sys.stderr)
        return 1

    e = Elf(binary.read_bytes())
    if not e.interp:
        print(f'{binary.name} has no interpreter: it is static and needs nothing')
        return 0

    print(f'  interpreter: {e.interp}')
    print(f'  libraries:   {", ".join(e.needed) if e.needed else "(none)"}')

    bad = False
    if a.interp and e.interp != a.interp:
        print(f'  FAIL: the program asks for {e.interp}, not {a.interp}')
        bad = True

    have = provided(rootfs)
    missing = []
    for name in e.needed:
        if name.startswith('ld-linux') or name.startswith('ld-musl'):
            continue                         # the loader itself: the interpreter path names it
        if name not in have:
            missing.append(name)
    if missing:
        print(f'  FAIL: the rootfs has no {", ".join(missing)}')
        bad = True
    else:
        print('  every library the program wants is in the rootfs')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
