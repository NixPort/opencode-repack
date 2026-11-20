"""A small ELF reader: the program headers and the dynamic section.

Only what the repack needs: the interpreter a program asks for, and the
libraries it wants (DT_NEEDED). The programs are aarch64 little-endian
ELF64, so only that is handled.

    from elf import Elf
    e = Elf(open("opencode", "rb").read())
    e.interp    # '/lib/ld-linux-aarch64.so.1'
    e.needed    # ['libc.so.6', 'libm.so.6', ...]
"""
import struct

PT_LOAD, PT_DYNAMIC, PT_INTERP = 1, 2, 3
DT_NULL, DT_NEEDED, DT_STRTAB, DT_STRSZ = 0, 1, 5, 10


class Elf:
    """What an ELF file asks for"""

    def __init__(self, data: bytes):
        self.data = data
        self.interp = None
        self.needed = []
        self._read()

    def _read(self):
        head = self.data[:64]
        if len(head) < 64 or head[:4] != b'\x7fELF' or head[4] != 2 or head[5] != 1:
            return                       # not an ELF64 little-endian file: it asks for nothing
        phoff, = struct.unpack_from('<Q', head, 32)
        phentsize, phnum = struct.unpack_from('<HH', head, 54)
        ph = self.data[phoff:phoff + phentsize * phnum]
        loads, dynamic = [], None
        for i in range(phnum):
            o = i * phentsize
            if o + phentsize > len(ph):
                break
            p_type, = struct.unpack_from('<I', ph, o)
            p_offset, p_vaddr, _p_paddr, p_filesz = struct.unpack_from('<QQQQ', ph, o + 8)
            if p_type == PT_LOAD:
                loads.append((p_vaddr, p_offset, p_filesz))
            elif p_type == PT_DYNAMIC:
                dynamic = (p_offset, p_filesz)
            elif p_type == PT_INTERP:
                self.interp = self.data[p_offset:p_offset + p_filesz].split(b'\0')[0].decode('utf-8', 'replace')
        if not dynamic:
            return
        dyn = self.data[dynamic[0]:dynamic[0] + dynamic[1]]
        needed_offsets, strtab_vaddr, strtab_size = [], None, 0
        for i in range(0, len(dyn) - 15, 16):
            tag, val = struct.unpack_from('<qQ', dyn, i)
            if tag == DT_NULL:
                break
            if tag == DT_NEEDED:
                needed_offsets.append(val)
            elif tag == DT_STRTAB:
                strtab_vaddr = val
            elif tag == DT_STRSZ:
                strtab_size = val
        if strtab_vaddr is None:
            return
        strtab_off = self._offset(loads, strtab_vaddr)
        if strtab_off is None:
            return
        # the string table of a big library is big: the names of its exports sit in it too
        table = self.data[strtab_off:strtab_off + max(strtab_size, 1 << 20)]
        self.needed = [self._string(table, o) for o in needed_offsets]

    @staticmethod
    def _offset(loads, vaddr):
        """The file offset of an address: the load segment that holds it decides"""
        for v, off, size in loads:
            if v <= vaddr < v + size:
                return off + (vaddr - v)
        return None

    @staticmethod
    def _string(table, off):
        end = table.find(b'\0', off)
        return table[off:end].decode('utf-8', 'replace') if end > 0 else ''
