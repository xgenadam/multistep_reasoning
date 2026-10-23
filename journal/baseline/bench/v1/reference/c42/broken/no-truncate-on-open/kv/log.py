"""The append-only write-ahead log: record format, decoding and recovery."""
import os
import struct
import zlib
from typing import NamedTuple

PUT = 1
DELETE = 2
_HEADER = struct.Struct('>II')    # crc, length
_PAYLOAD_HEAD = struct.Struct('>BH')  # op, key_len
MAX_KEY = 0xFFFF


class KVError(Exception):
    pass


class CorruptLog(KVError):
    def __init__(self, offset: int, message: str = 'corrupt log record'):
        super().__init__(f'{message} at offset {offset}')
        self.offset = offset


class Record(NamedTuple):
    op: int
    key: bytes
    value: bytes


def check_key_value(key, value) -> None:
    if not isinstance(key, bytes) or not isinstance(value, bytes):
        raise TypeError('keys and values must be bytes')
    if not 1 <= len(key) <= MAX_KEY:
        raise ValueError('key length must be 1..65535 bytes')


def encode_record(op: int, key: bytes, value: bytes = b'') -> bytes:
    check_key_value(key, value)
    if op not in (PUT, DELETE):
        raise ValueError(f'unknown op {op!r}')
    if op == DELETE and value:
        raise ValueError('a DELETE record has no value')
    payload = _PAYLOAD_HEAD.pack(op, len(key)) + key + value
    body = struct.pack('>I', len(payload)) + payload
    return struct.pack('>I', zlib.crc32(body)) + body


def _parse_payload(payload: bytes, offset: int) -> Record:
    if len(payload) < _PAYLOAD_HEAD.size:
        raise CorruptLog(offset, 'payload too short')
    op, key_len = _PAYLOAD_HEAD.unpack_from(payload)
    if op not in (PUT, DELETE):
        raise CorruptLog(offset, f'unknown op {op}')
    rest = payload[_PAYLOAD_HEAD.size:]
    if key_len == 0 or key_len > len(rest):
        raise CorruptLog(offset, 'bad key length')
    key, value = rest[:key_len], rest[key_len:]
    if op == DELETE and value:
        raise CorruptLog(offset, 'DELETE with a value')
    return Record(op, bytes(key), bytes(value))


def decode_records(data: bytes) -> tuple[list[Record], int]:
    records: list[Record] = []
    pos = 0
    n = len(data)
    while pos < n:
        if n - pos < _HEADER.size:
            break  # torn header
        crc, length = _HEADER.unpack_from(data, pos)
        end = pos + _HEADER.size + length
        if end > n:
            break  # torn payload
        if zlib.crc32(data[pos + 4:end]) != crc:
            if end == n:
                break  # a torn last write
            raise CorruptLog(pos, 'checksum mismatch')
        records.append(_parse_payload(data[pos + _HEADER.size:end], pos))
        pos = end
    return records, pos


class Log:
    def __init__(self, path):
        self.path = os.fspath(path)
        data = b''
        if os.path.exists(self.path):
            with open(self.path, 'rb') as f:
                data = f.read()
        records, valid_end = decode_records(data)
        self.recovered = records
        self.truncated = len(data) - valid_end
        self._file = open(self.path, 'ab')
        self.count = len(records)
        self.size = valid_end

    def append(self, op: int, key: bytes, value: bytes = b'') -> int:
        record = encode_record(op, key, value)
        offset = self.size
        self._file.write(record)
        self._file.flush()
        self.size += len(record)
        self.count += 1
        return offset

    def reset(self) -> None:
        self._file.truncate(0)
        self._file.flush()
        self.size = 0
        self.count = 0

    def close(self) -> None:
        self._file.close()

    @property
    def closed(self) -> bool:
        return self._file.closed
