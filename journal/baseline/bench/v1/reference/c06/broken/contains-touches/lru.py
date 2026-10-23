from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError('capacity must be at least 1')
        self.capacity = capacity
        self._data: OrderedDict = OrderedDict()

    def get(self, key, default=None):
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key, value):
        if key in self._data:
            self._data[key] = value
            self._data.move_to_end(key)
            return None
        evicted = None
        if len(self._data) >= self.capacity:
            evicted, _ = self._data.popitem(last=False)
        self._data[key] = value
        return evicted

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        if key in self._data:
            self._data.move_to_end(key)
            return True
        return False

    def keys(self):
        return list(self._data)

    def resize(self, capacity: int):
        if capacity < 1:
            raise ValueError('capacity must be at least 1')
        self.capacity = capacity
        evicted = []
        while len(self._data) > capacity:
            key, _ = self._data.popitem(last=False)
            evicted.append(key)
        return evicted
