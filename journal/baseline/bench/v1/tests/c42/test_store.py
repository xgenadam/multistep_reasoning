import struct
import zlib

import pytest

from kv import (DELETE, PUT, CorruptLog, CorruptSnapshot, KVError, KVStore, decode_snapshot,
                encode_record, encode_snapshot)


def test_basic_operations(tmp_path):
    with KVStore(tmp_path / 'db') as s:
        assert (tmp_path / 'db').is_dir()
        s.put(b'a', b'1')
        s.put(b'b', b'2')
        s.put(b'a', b'3')
        assert s.get(b'a') == b'3' and s.get(b'zz') is None and s.get(b'zz', b'd') == b'd'
        assert b'a' in s and b'zz' not in s and len(s) == 2
        assert s.delete(b'a') is True
        assert s.delete(b'a') is False
        assert s.stats() == {'keys': 1, 'log_records': 4,
                             'log_bytes': (tmp_path / 'db' / 'wal.log').stat().st_size}


def test_same_value_still_writes_a_record(tmp_path):
    with KVStore(tmp_path) as s:
        s.put(b'a', b'1')
        s.put(b'a', b'1')
        assert s.stats()['log_records'] == 2


def test_persists_across_reopen(tmp_path):
    with KVStore(tmp_path) as s:
        s.put(b'x', b'1')
        s.put(b'y', b'2')
        s.delete(b'x')
        s.put(b'z', b'')
    with KVStore(tmp_path) as s:
        assert s.scan() == [(b'y', b'2'), (b'z', b'')]
    assert (tmp_path / 'wal.log').read_bytes() == (
        encode_record(PUT, b'x', b'1') + encode_record(PUT, b'y', b'2')
        + encode_record(DELETE, b'x') + encode_record(PUT, b'z', b''))


@pytest.mark.parametrize('kwargs, keys', [
    ({}, [b'a', b'ab', b'abc', b'b', b'ba', b'c']),
    ({'start': b'ab', 'end': b'b'}, [b'ab', b'abc']),
    ({'prefix': b'b'}, [b'b', b'ba']),
    ({'start': b'aa', 'end': b'c', 'prefix': b'a'}, [b'ab', b'abc']),
])
def test_scan(tmp_path, kwargs, keys):
    with KVStore(tmp_path) as s:
        for k in [b'c', b'ba', b'abc', b'a', b'b', b'ab']:
            s.put(k, k.upper())
        got = s.scan(**kwargs)
        assert [k for k, _ in got] == keys
        assert all(v == k.upper() for k, v in got)


def test_torn_last_write_is_ignored_on_reopen(tmp_path):
    with KVStore(tmp_path) as s:
        s.put(b'a', b'1')
        s.put(b'b', b'2')
    wal = tmp_path / 'wal.log'
    size = wal.stat().st_size
    with open(wal, 'ab') as f:
        f.write(encode_record(PUT, b'c', b'3')[:-2])
    with KVStore(tmp_path) as s:
        assert s.scan() == [(b'a', b'1'), (b'b', b'2')]
        assert wal.stat().st_size == size
        s.put(b'd', b'4')
    with KVStore(tmp_path) as s:
        assert s.get(b'd') == b'4' and len(s) == 3


def test_corruption_in_the_middle_raises_on_open(tmp_path):
    with KVStore(tmp_path) as s:
        s.put(b'a', b'1')
        s.put(b'b', b'2')
    wal = tmp_path / 'wal.log'
    data = bytearray(wal.read_bytes())
    data[9] ^= 0x40  # inside the first record's payload
    wal.write_bytes(bytes(data))
    with pytest.raises(CorruptLog):
        KVStore(tmp_path)


def test_snapshot_format():
    data = encode_snapshot({b'b': b'22', b'a': b''})
    body = (b'KVS1' + struct.pack('>I', 2) + struct.pack('>H', 1) + b'a' + struct.pack('>I', 0)
            + struct.pack('>H', 1) + b'b' + struct.pack('>I', 2) + b'22')
    assert data == body + struct.pack('>I', zlib.crc32(body))
    assert decode_snapshot(data) == {b'a': b'', b'b': b'22'}
    assert decode_snapshot(encode_snapshot({})) == {}


@pytest.mark.parametrize('damage', ['magic', 'crc', 'short', 'extra'])
def test_corrupt_snapshot_detected(damage):
    data = bytearray(encode_snapshot({b'a': b'1', b'b': b'2'}))
    if damage == 'magic':
        data[:4] = b'KVS2'
    elif damage == 'crc':
        data[10] ^= 1
    elif damage == 'short':
        body = bytes(data[:-10])
        data = bytearray(body + struct.pack('>I', zlib.crc32(body)))
    else:
        body = bytes(data[:-4]) + b'\x00'
        data = bytearray(body + struct.pack('>I', zlib.crc32(body)))
    with pytest.raises(CorruptSnapshot) as exc:
        decode_snapshot(bytes(data))
    assert isinstance(exc.value, KVError)


def test_compact_writes_snapshot_and_empties_log(tmp_path):
    with KVStore(tmp_path) as s:
        for i in range(5):
            s.put(b'k%d' % i, b'v%d' % i)
        s.delete(b'k1')
        s.compact()
        assert s.stats() == {'keys': 4, 'log_records': 0, 'log_bytes': 0}
        assert (tmp_path / 'wal.log').stat().st_size == 0
        assert decode_snapshot((tmp_path / 'snapshot.db').read_bytes()) == \
            {b'k0': b'v0', b'k2': b'v2', b'k3': b'v3', b'k4': b'v4'}
        s.put(b'k0', b'new')
        s.delete(b'k2')
    with KVStore(tmp_path) as s:
        assert s.scan() == [(b'k0', b'new'), (b'k3', b'v3'), (b'k4', b'v4')]
        assert s.stats()['log_records'] == 2


def test_crash_between_snapshot_and_log_reset_replays_cleanly(tmp_path):
    with KVStore(tmp_path) as s:
        s.put(b'a', b'1')
        s.put(b'b', b'2')
        s.delete(b'a')
        s.put(b'a', b'3')
    # simulate the crash: the snapshot was written, the log was never emptied
    (tmp_path / 'snapshot.db').write_bytes(encode_snapshot({b'a': b'3', b'b': b'2'}))
    with KVStore(tmp_path) as s:
        assert s.scan() == [(b'a', b'3'), (b'b', b'2')]


def test_leftover_tmp_snapshot_is_removed(tmp_path):
    with KVStore(tmp_path) as s:
        s.put(b'a', b'1')
        s.compact()
    (tmp_path / 'snapshot.db.tmp').write_bytes(b'half-written junk')
    with KVStore(tmp_path) as s:
        assert s.get(b'a') == b'1'
    assert not (tmp_path / 'snapshot.db.tmp').exists()


def test_corrupt_snapshot_file_raises_on_open(tmp_path):
    (tmp_path / 'snapshot.db').write_bytes(b'KVS1junkjunk')
    with pytest.raises(CorruptSnapshot):
        KVStore(tmp_path)


def test_auto_compaction_threshold(tmp_path):
    with KVStore(tmp_path, max_log_records=3) as s:
        s.put(b'a', b'1')
        s.put(b'b', b'2')
        s.put(b'c', b'3')
        assert s.stats()['log_records'] == 3
        assert not (tmp_path / 'snapshot.db').exists()
        s.delete(b'a')  # the 4th record triggers compaction
        assert s.stats()['log_records'] == 0
        assert decode_snapshot((tmp_path / 'snapshot.db').read_bytes()) == {b'b': b'2', b'c': b'3'}
        s.delete(b'zz')  # writes nothing
        s.put(b'd', b'4')
        assert s.stats()['log_records'] == 1


def test_type_and_size_errors(tmp_path):
    with KVStore(tmp_path) as s:
        with pytest.raises(TypeError):
            s.put('a', b'1')
        with pytest.raises(TypeError):
            s.put(b'a', '1')
        with pytest.raises(ValueError):
            s.put(b'', b'1')
        with pytest.raises(ValueError):
            s.put(b'k' * 70000, b'1')
        assert s.stats()['log_records'] == 0


def test_closed_store_raises(tmp_path):
    s = KVStore(tmp_path)
    s.put(b'a', b'1')
    s.close()
    for call in (lambda: s.put(b'b', b'2'), lambda: s.get(b'a'), lambda: s.delete(b'a'),
                 lambda: s.scan(), lambda: s.compact(), lambda: s.stats()):
        with pytest.raises(KVError):
            call()
    with KVStore(tmp_path) as again:
        assert again.get(b'a') == b'1'
