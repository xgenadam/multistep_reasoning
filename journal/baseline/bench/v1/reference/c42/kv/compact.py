"""Snapshot files and compaction."""
import os
import struct
import zlib

from .log import KVError

MAGIC = b'KVS1'


class CorruptSnapshot(KVError):
    pass


def encode_snapshot(items: dict[bytes, bytes]) -> bytes:
    out = bytearray(MAGIC)
    out += struct.pack('>I', len(items))
    for key in sorted(items):
        value = items[key]
        out += struct.pack('>H', len(key)) + key
        out += struct.pack('>I', len(value)) + value
    out += struct.pack('>I', zlib.crc32(out))
    return bytes(out)


def decode_snapshot(data: bytes) -> dict[bytes, bytes]:
    if len(data) < 12 or data[:4] != MAGIC:
        raise CorruptSnapshot('bad magic or too short')
    body, (crc,) = data[:-4], struct.unpack('>I', data[-4:])
    if zlib.crc32(body) != crc:
        raise CorruptSnapshot('checksum mismatch')
    (count,) = struct.unpack_from('>I', body, 4)
    pos = 8
    items: dict[bytes, bytes] = {}
    try:
        for _ in range(count):
            (klen,) = struct.unpack_from('>H', body, pos)
            pos += 2
            key = body[pos:pos + klen]
            pos += klen
            (vlen,) = struct.unpack_from('>I', body, pos)
            pos += 4
            value = body[pos:pos + vlen]
            pos += vlen
            if len(key) != klen or len(value) != vlen:
                raise CorruptSnapshot('entry runs past the end')
            items[bytes(key)] = bytes(value)
    except struct.error:
        raise CorruptSnapshot('entry runs past the end') from None
    if pos != len(body):
        raise CorruptSnapshot('bytes left over')
    return items


def write_snapshot(path, items: dict[bytes, bytes]) -> None:
    path = os.fspath(path)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(encode_snapshot(items))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_snapshot(path) -> dict[bytes, bytes]:
    path = os.fspath(path)
    if not os.path.exists(path):
        return {}
    with open(path, 'rb') as f:
        return decode_snapshot(f.read())


def compact(snapshot_path, items: dict[bytes, bytes], log) -> None:
    """Snapshot first, then empty the log: a crash in between replays idempotently."""
    write_snapshot(snapshot_path, items)
    log.reset()
