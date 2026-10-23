import time
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int, ttl=None, clock=time.monotonic):
        if capacity < 1:
            raise ValueError('capacity must be at least 1')
        if ttl is not None and ttl <= 0:
            raise ValueError('ttl must be greater than 0')
        self.capacity = capacity
        self.ttl = ttl
        self._clock = clock
        self._data: OrderedDict = OrderedDict()  # key -> (value, time stored)
        self._stats = {'hits': 0, 'misses': 0, 'evictions': 0, 'expirations': 0}

    def _purge(self) -> None:
        if self.ttl is None:
            return
        now = self._clock()
        for key in [k for k, (_, t) in self._data.items() if now - t >= self.ttl]:
            del self._data[key]
            self._stats['expirations'] += 1

    def get(self, key, default=None):
        self._purge()
        if key not in self._data:
            self._stats['misses'] += 1
            return default
        self._stats['hits'] += 1
        self._data.move_to_end(key)
        return self._data[key][0]

    def put(self, key, value):
        self._purge()
        now = self._clock() if self.ttl is not None else 0
        if key in self._data:
            self._data[key] = (value, now)
            self._data.move_to_end(key)
            return None
        evicted = None
        if len(self._data) >= self.capacity:
            evicted, _ = self._data.popitem(last=False)
            self._stats['evictions'] += 1
        self._data[key] = (value, now)
        return evicted

    def __len__(self):
        self._purge()
        return len(self._data)

    def __contains__(self, key):
        self._purge()
        return key in self._data

    def keys(self):
        self._purge()
        return list(self._data)

    def resize(self, capacity: int):
        if capacity < 1:
            raise ValueError('capacity must be at least 1')
        self._purge()
        self.capacity = capacity
        evicted = []
        while len(self._data) > capacity:
            key, _ = self._data.popitem(last=False)
            evicted.append(key)
            self._stats['evictions'] += 1
        return evicted

    def stats(self):
        self._purge()
        return dict(self._stats)
