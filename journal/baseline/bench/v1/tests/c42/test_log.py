import struct
import zlib

import pytest

from kv import DELETE, PUT, CorruptLog, KVError, Log, Record, decode_records, encode_record


def manual(op, key, value=b''):
    payload = bytes([op]) + struct.pack('>H', len(key)) + key + value
    body = struct.pack('>I', len(payload)) + payload
    return struct.pack('>I', zlib.crc32(body)) + body


def test_encode_record_exact_bytes():
    assert PUT == 1 and DELETE == 2
    rec = encode_record(PUT, b'key', b'value')
    assert rec == manual(PUT, b'key', b'value')
    assert rec[4:8] == b'\x00\x00\x00\x0b' and rec[8:11] == b'\x01\x00\x03'
    assert encode_record(DELETE, b'k') == manual(DELETE, b'k')
    assert len(encode_record(DELETE, b'k')) == 12


@pytest.mark.parametrize('args, exc', [
    ((PUT, 'key', b'v'), TypeError),
    ((PUT, b'key', 'v'), TypeError),
    ((3, b'key', b'v'), ValueError),
    ((PUT, b'', b'v'), ValueError),
    ((PUT, b'k' * 65536, b'v'), ValueError),
    ((DELETE, b'key', b'v'), ValueError),
])
def test_encode_record_validation(args, exc):
    with pytest.raises(exc):
        encode_record(*args)


def test_long_key_limit_is_inclusive():
    rec = encode_record(PUT, b'k' * 65535, b'')
    assert decode_records(rec)[0] == [Record(PUT, b'k' * 65535, b'')]


def test_decode_round_trip():
    data = manual(PUT, b'a', b'1') + manual(PUT, b'b', b'') + manual(DELETE, b'a')
    records, end = decode_records(data)
    assert records == [Record(PUT, b'a', b'1'), Record(PUT, b'b', b''), Record(DELETE, b'a', b'')]
    assert isinstance(records[0], tuple) and records[0].op == PUT
    assert end == len(data)
    assert decode_records(b'') == ([], 0)


@pytest.mark.parametrize('damage', ['short-header', 'short-payload', 'bad-crc-at-end'])
def test_torn_tail_is_ignored(damage):
    good = manual(PUT, b'a', b'1') + manual(PUT, b'b', b'2')
    last = manual(PUT, b'c', b'333')
    if damage == 'short-header':
        tail = last[:5]
    elif damage == 'short-payload':
        tail = last[:-1]
    else:
        tail = last[:-1] + b'X'
    records, end = decode_records(good + tail)
    assert [r.key for r in records] == [b'a', b'b']
    assert end == len(good)


def test_bad_crc_in_the_middle_is_corruption():
    first = manual(PUT, b'a', b'1')
    second = bytearray(manual(PUT, b'b', b'2'))
    second[-1] ^= 0xFF
    with pytest.raises(CorruptLog) as exc:
        decode_records(first + bytes(second) + manual(PUT, b'c', b'3'))
    assert exc.value.offset == len(first)
    assert isinstance(exc.value, KVError)


def raw_record(payload):
    body = struct.pack('>I', len(payload)) + payload
    return struct.pack('>I', zlib.crc32(body)) + body


MALFORMED = [
    b'\x01\x00',                       # shorter than 3 bytes
    b'\x07\x00\x01k',                  # unknown op
    b'\x01\x00\x00v',                  # key_len 0
    b'\x01\x00\x05ab',                 # key_len past the payload
    b'\x02\x00\x01kv',                 # DELETE with a value
]


def test_malformed_payload_with_good_crc_is_corruption():
    good = manual(PUT, b'a', b'1')
    for payload in MALFORMED:
        with pytest.raises(CorruptLog) as exc:
            decode_records(good + raw_record(payload))  # even as the last record
        assert exc.value.offset == len(good), payload


def test_log_recovery_truncates_torn_tail(tmp_path):
    path = tmp_path / 'wal.log'
    good = manual(PUT, b'a', b'1') + manual(DELETE, b'a')
    path.write_bytes(good + manual(PUT, b'b', b'2')[:7])
    log = Log(str(path))
    assert log.recovered == [Record(PUT, b'a', b'1'), Record(DELETE, b'a', b'')]
    assert log.truncated == 7 and log.count == 2 and log.size == len(good)
    assert path.read_bytes() == good
    off = log.append(PUT, b'z', b'9')
    assert off == len(good)
    log.close()
    again = Log(str(path))
    assert again.truncated == 0
    assert [r.key for r in again.recovered] == [b'a', b'a', b'z']
    again.close()


def test_log_creates_file_append_and_reset(tmp_path):
    path = tmp_path / 'new.log'
    log = Log(str(path))
    assert path.exists() and log.recovered == [] and log.count == 0 and log.size == 0
    assert log.append(PUT, b'k', b'v') == 0
    second = log.append(DELETE, b'k')
    assert second == len(manual(PUT, b'k', b'v'))
    assert log.count == 2 and log.size == path.stat().st_size
    log.reset()
    assert log.count == 0 and log.size == 0 and path.stat().st_size == 0
    log.append(PUT, b'x', b'y')
    log.close()
    assert path.read_bytes() == manual(PUT, b'x', b'y')


def test_log_open_raises_on_corruption(tmp_path):
    path = tmp_path / 'wal.log'
    bad = bytearray(manual(PUT, b'a', b'1'))
    bad[0] ^= 1
    path.write_bytes(bytes(bad) + manual(PUT, b'b', b'2'))
    with pytest.raises(CorruptLog) as exc:
        Log(str(path))
    assert exc.value.offset == 0
