import pytest

from events import EmitError, Emitter


def recorder(log, name):
    def listener(*args, **kwargs):
        log.append((name, args, kwargs))
    listener.__name__ = name
    return listener


def test_on_and_emit_in_order_with_args():
    em, log = Emitter(), []
    a, b = recorder(log, 'a'), recorder(log, 'b')
    assert em.on('x', a) is a
    em.on('x', b)
    assert em.emit('x', 1, k=2) == 2
    assert log == [('a', (1,), {'k': 2}), ('b', (1,), {'k': 2})]


def test_emit_without_listeners():
    assert Emitter().emit('nothing') == 0


def test_events_are_separate():
    em, log = Emitter(), []
    em.on('x', recorder(log, 'a'))
    assert em.emit('y') == 0
    assert log == []


def test_same_listener_twice():
    em, log = Emitter(), []
    a = recorder(log, 'a')
    em.on('x', a)
    em.on('x', a)
    assert em.emit('x') == 2
    assert em.listeners('x') == [a, a]


def test_once_runs_once():
    em, log = Emitter(), []
    a = recorder(log, 'a')
    assert em.once('x', a) is a
    assert em.emit('x') == 1
    assert em.emit('x') == 0
    assert len(log) == 1
    assert em.listeners('x') == []


def test_once_removed_before_call_reentrant():
    em, calls = Emitter(), []

    def again():
        calls.append('again')
        em.emit('x')

    em.once('x', again)
    em.emit('x')
    assert calls == ['again']


def test_off_removes_earliest_registration():
    em, log = Emitter(), []
    a, b = recorder(log, 'a'), recorder(log, 'b')
    em.on('x', a)
    em.on('x', b)
    em.on('x', a)
    assert em.off('x', a) == 1
    assert em.listeners('x') == [b, a]
    assert em.off('x', a) == 1
    assert em.off('x', a) == 0
    assert em.listeners('x') == [b]


def test_off_once_registration_and_unknown():
    em, log = Emitter(), []
    a = recorder(log, 'a')
    em.once('x', a)
    assert em.off('x', a) == 1
    assert em.emit('x') == 0
    assert em.off('nope', a) == 0


def test_off_all():
    em, log = Emitter(), []
    em.on('x', recorder(log, 'a'))
    em.once('x', recorder(log, 'b'))
    em.on('y', recorder(log, 'c'))
    assert em.off('x') == 2
    assert em.listeners('x') == []
    assert em.off('x') == 0
    assert em.emit('y') == 1


def test_listener_added_during_emit_not_called():
    em, log = Emitter(), []
    late = recorder(log, 'late')

    def adder():
        log.append('adder')
        em.on('x', late)

    em.on('x', adder)
    assert em.emit('x') == 1
    assert log == ['adder']
    assert em.listeners('x') == [adder, late]


def test_listener_removed_during_emit_not_called():
    em, log = Emitter(), []
    victim = recorder(log, 'victim')

    def remover():
        log.append('remover')
        em.off('x', victim)

    em.on('x', remover)
    em.on('x', victim)
    assert em.emit('x') == 1
    assert log == ['remover']


def test_errors_collected_after_all_listeners():
    em, log = Emitter(), []

    def bad1():
        raise ValueError('one')

    def bad2():
        raise KeyError('two')

    em.on('x', bad1)
    em.on('x', recorder(log, 'ok'))
    em.on('x', bad2)
    with pytest.raises(EmitError) as e:
        em.emit('x')
    assert [name for name, _, _ in log] == ['ok']
    errors = e.value.errors
    assert [listener for listener, _ in errors] == [bad1, bad2]
    assert isinstance(errors[0][1], ValueError) and isinstance(errors[1][1], KeyError)


def test_failing_once_listener_is_still_removed():
    em = Emitter()

    def bad():
        raise RuntimeError('x')

    em.once('x', bad)
    with pytest.raises(EmitError):
        em.emit('x')
    assert em.emit('x') == 0


def test_listeners_returns_a_copy():
    em = Emitter()
    f = em.on('x', lambda: None)
    got = em.listeners('x')
    got.clear()
    assert em.listeners('x') == [f]
    assert em.listeners('unknown') == []
