"""The key-value store: snapshot + write-ahead log."""
import os

from . import compact as _compact
from .log import DELETE, PUT, KVError, Log, check_key_value

SNAPSHOT = 'snapshot.db'
WAL = 'wal.log'


class KVStore:
    def __init__(self, directory, max_log_records: int | None = None):
        self.directory = os.fspath(directory)
        self.max_log_records = max_log_records
        os.makedirs(self.directory, exist_ok=True)
        self._snapshot_path = os.path.join(self.directory, SNAPSHOT)
        tmp = self._snapshot_path + '.tmp'
        if os.path.exists(tmp):
            os.remove(tmp)
        self._data = _compact.read_snapshot(self._snapshot_path)
        self._log = Log(os.path.join(self.directory, WAL))
        for rec in self._log.recovered:
            if rec.op == PUT:
                self._data[rec.key] = rec.value
            else:
                self._data.pop(rec.key, None)
        self._closed = False

    # ------------------------------------------------------------ helpers
    def _check_open(self) -> None:
        if self._closed:
            raise KVError('store is closed')

    def _after_write(self) -> None:
        if self.max_log_records is not None and self._log.count > self.max_log_records:
            self.compact()

    # ------------------------------------------------------------ API
    def put(self, key: bytes, value: bytes) -> None:
        """Log a PUT, then apply it (a record is written even for an unchanged value)."""
        self._check_open()
        check_key_value(key, value)
        self._log.append(PUT, key, value)
        self._data[key] = value
        self._after_write()

    def get(self, key: bytes, default=None):
        self._check_open()
        return self._data.get(key, default)

    def __contains__(self, key) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def delete(self, key: bytes) -> bool:
        """Log a DELETE and apply it; a missing key writes nothing and returns False."""
        self._check_open()
        check_key_value(key, b'')
        self._log.append(DELETE, key)
        if key not in self._data:
            return False
        del self._data[key]
        self._after_write()
        return True

    def scan(self, start=None, end=None, prefix: bytes = b'') -> list[tuple[bytes, bytes]]:
        """Sorted (key, value) pairs with start <= key < end and the given prefix."""
        self._check_open()
        out = []
        for key in sorted(self._data):
            if start is not None and key < start:
                continue
            if end is not None and key >= end:
                break
            if key.startswith(prefix):
                out.append((key, self._data[key]))
        return out

    def compact(self) -> None:
        """Write a snapshot of the current data, then empty the log."""
        self._check_open()
        _compact.compact(self._snapshot_path, dict(self._data), self._log)

    def stats(self) -> dict:
        self._check_open()
        return {'keys': len(self._data), 'log_records': self._log.count,
                'log_bytes': self._log.size}

    def close(self) -> None:
        if not self._closed:
            self._log.close()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
