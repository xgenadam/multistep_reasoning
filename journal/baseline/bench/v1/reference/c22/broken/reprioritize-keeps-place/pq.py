import heapq
import itertools


class TaskQueue:
    def __init__(self):
        self._heap = []                 # [priority, seq, task, alive]
        self._entries = {}              # task -> its live heap entry
        self._seq = itertools.count()

    def _add(self, task, priority):
        entry = [priority, next(self._seq), task, True]
        self._entries[task] = entry
        heapq.heappush(self._heap, entry)

    def _kill(self, task):
        entry = self._entries.pop(task)
        entry[3] = False

    def _clean(self):
        while self._heap and not self._heap[0][3]:
            heapq.heappop(self._heap)

    def push(self, task, priority):
        if task in self._entries:
            raise ValueError(f'task already queued: {task!r}')
        self._add(task, priority)

    def peek(self):
        self._clean()
        if not self._heap:
            raise IndexError('peek from an empty queue')
        priority, _, task, _ = self._heap[0]
        return task, priority

    def pop(self):
        self._clean()
        if not self._heap:
            raise IndexError('pop from an empty queue')
        priority, _, task, _ = heapq.heappop(self._heap)
        del self._entries[task]
        return task, priority

    def reprioritize(self, task, priority):
        if task not in self._entries:
            raise KeyError(task)
        old = self._entries[task]
        self._kill(task)
        entry = [priority, old[1], task, True]
        self._entries[task] = entry
        heapq.heappush(self._heap, entry)

    def remove(self, task):
        if task not in self._entries:
            raise KeyError(task)
        self._kill(task)

    def priority(self, task):
        return self._entries[task][0]

    def __len__(self):
        return len(self._entries)

    def __contains__(self, task):
        return task in self._entries
