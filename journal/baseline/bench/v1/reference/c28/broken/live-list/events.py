class EmitError(Exception):
    def __init__(self, errors):
        super().__init__(f'{len(errors)} listener(s) failed')
        self.errors = errors


class _Registration:
    __slots__ = ('listener', 'once', 'active')

    def __init__(self, listener, once):
        self.listener = listener
        self.once = once
        self.active = True


class Emitter:
    def __init__(self):
        self._regs = {}

    def _add(self, event, listener, once):
        self._regs.setdefault(event, []).append(_Registration(listener, once))
        return listener

    def on(self, event, listener):
        return self._add(event, listener, False)

    def once(self, event, listener):
        return self._add(event, listener, True)

    def _drop(self, event, reg):
        reg.active = False
        regs = self._regs[event]
        regs.remove(reg)
        if not regs:
            del self._regs[event]

    def off(self, event, listener=None):
        regs = list(self._regs.get(event, []))
        if listener is None:
            for reg in regs:
                self._drop(event, reg)
            return len(regs)
        for reg in regs:
            if reg.listener == listener:
                self._drop(event, reg)
                return 1
        return 0

    def emit(self, event, *args, **kwargs):
        calls, errors = 0, []
        for reg in self._regs.get(event, []):
            if not reg.active:
                continue
            if reg.once:
                self._drop(event, reg)
            calls += 1
            try:
                reg.listener(*args, **kwargs)
            except Exception as exc:
                errors.append((reg.listener, exc))
        if errors:
            raise EmitError(errors)
        return calls

    def listeners(self, event):
        return [reg.listener for reg in self._regs.get(event, [])]
