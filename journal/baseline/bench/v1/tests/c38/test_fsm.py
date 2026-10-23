import pytest

from fsm import (Event, GuardRejected, InvalidTransition, Machine, MachineError, State,
                 Transition)


def door(log=None, **kw):
    log = [] if log is None else log

    def hook(tag):
        return lambda m, ev: log.append((tag, ev.source, ev.target))

    states = [
        State('closed', on_enter=hook('enter closed'), on_exit=hook('exit closed')),
        State('open', on_enter=hook('enter open'), on_exit=hook('exit open')),
        'locked',
    ]
    transitions = [
        Transition('open', 'closed', 'open', action=hook('act open')),
        Transition('close', 'open', 'closed'),
        Transition('lock', 'closed', 'locked'),
        Transition('unlock', 'locked', 'closed'),
    ]
    return Machine(states, transitions, 'closed', **kw), log


def test_initial_state_and_no_hooks_at_construction():
    m, log = door(context={'k': 1})
    assert m.state == 'closed'
    assert m.context == {'k': 1}
    assert m.history == []
    assert log == []


@pytest.mark.parametrize('states, transitions, initial', [
    ([], [], 'a'),
    (['a', 'a'], [], 'a'),
    (['a'], [], 'b'),
    (['a'], [Transition('go', 'a', 'b')], 'a'),
    (['a', 'b'], [Transition('go', ['a', 'zz'], 'b')], 'a'),
])
def test_constructor_validation(states, transitions, initial):
    with pytest.raises(ValueError):
        Machine(states, transitions, initial)


def test_fire_returns_state_and_hook_order():
    m, log = door()
    assert m.fire('open') == 'open'
    assert m.state == 'open'
    assert log == [('exit closed', 'closed', 'open'), ('act open', 'closed', 'open'),
                   ('enter open', 'closed', 'open')]
    assert m.history == [('closed', 'open', 'open')]


def test_invalid_transition_attributes_and_state_kept():
    m, _ = door()
    with pytest.raises(InvalidTransition) as exc:
        m.fire('close')
    assert exc.value.state == 'closed' and exc.value.event == 'close'
    assert isinstance(exc.value, MachineError)
    assert m.state == 'closed' and m.history == []


def test_first_passing_guard_wins_and_later_guards_not_called():
    calls = []

    def g(name, ok):
        def guard(m, ev):
            calls.append(name)
            return ok
        return guard

    m = Machine(['a', 'b', 'c', 'd'], [
        Transition('go', 'a', 'b', guard=g('g1', False)),
        Transition('go', 'a', 'c', guard=g('g2', True)),
        Transition('go', 'a', 'd', guard=g('g3', True)),
    ], 'a')
    assert m.fire('go') == 'c'
    assert calls == ['g1', 'g2']


def test_unguarded_transition_after_rejected_one():
    m = Machine(['a', 'b', 'c'], [
        Transition('go', 'a', 'b', guard=lambda m, ev: False),
        Transition('go', 'a', 'c'),
    ], 'a')
    assert m.fire('go') == 'c'


def test_guard_rejected_runs_nothing():
    log = []
    m = Machine([State('a', on_exit=lambda m, ev: log.append('exit')), 'b'],
                [Transition('go', 'a', 'b', guard=lambda m, ev: ev.data.get('ok'),
                            action=lambda m, ev: log.append('act'))], 'a')
    with pytest.raises(GuardRejected) as exc:
        m.fire('go', ok=False)
    assert exc.value.state == 'a' and exc.value.event == 'go'
    assert not isinstance(exc.value, InvalidTransition)
    assert log == [] and m.state == 'a' and m.history == []
    assert m.fire('go', ok=True) == 'b'


def test_event_object_and_shared_data_dict():
    seen = []

    def guard(m, ev):
        seen.append(ev)
        ev.data['from_guard'] = 1
        return True

    def action(m, ev):
        seen.append(ev)
        ev.data['from_action'] = ev.data['from_guard'] + 1

    def enter(m, ev):
        seen.append(ev)

    m = Machine(['a', State('b', on_enter=enter)],
                [Transition('go', 'a', 'b', guard=guard, action=action)], 'a')
    m.fire('go', x=5)
    assert all(isinstance(e, Event) for e in seen)
    assert (seen[0].name, seen[0].source, seen[0].target) == ('go', 'a', 'b')
    assert seen[-1].data == {'x': 5, 'from_guard': 1, 'from_action': 2}
    assert all(e.data is seen[0].data for e in seen)


def test_hooks_receive_the_machine():
    got = []
    m = Machine(['a', 'b'], [Transition('go', 'a', 'b', action=lambda mm, ev: got.append(mm))],
                'a', context='ctx')
    m.fire('go')
    assert got == [m] and got[0].context == 'ctx'


def test_self_transition_runs_exit_and_enter():
    log = []
    m = Machine([State('a', on_enter=lambda m, ev: log.append('enter'),
                       on_exit=lambda m, ev: log.append('exit'))],
                [Transition('again', 'a', 'a')], 'a')
    assert m.fire('again') == 'a'
    assert log == ['exit', 'enter']
    assert m.history == [('a', 'again', 'a')]


def test_internal_transition_runs_only_action():
    log = []
    m = Machine([State('a', on_enter=lambda m, ev: log.append('enter'),
                       on_exit=lambda m, ev: log.append('exit'))],
                [Transition('tick', 'a', None, action=lambda m, ev: log.append(('act', ev.target)))],
                'a')
    seen = []
    m.on_transition(lambda *args: seen.append(args))
    assert m.fire('tick') == 'a'
    assert log == [('act', 'a')]
    assert m.history == [('a', 'tick', 'a')]
    assert seen == [('a', 'tick', 'a')]


def test_wildcard_and_list_sources():
    m = Machine(['a', 'b', 'c'], [
        Transition('reset', '*', 'a'),
        Transition('next', ('a', 'b'), 'c'),
        Transition('ab', 'a', 'b'),
    ], 'a')
    m.fire('ab')
    assert m.fire('next') == 'c'
    with pytest.raises(InvalidTransition):
        m.fire('next')
    assert m.fire('reset') == 'a'
    assert m.fire('reset') == 'a'


def test_listeners_called_in_order_after_enter():
    log = []
    m = Machine(['a', State('b', on_enter=lambda m, ev: log.append('enter'))],
                [Transition('go', 'a', 'b')], 'a')
    m.on_transition(lambda s, e, t: log.append(('L1', s, e, t)))
    m.on_transition(lambda s, e, t: log.append(('L2', s, e, t)))
    m.fire('go')
    assert log == ['enter', ('L1', 'a', 'go', 'b'), ('L2', 'a', 'go', 'b')]


def test_exception_in_action_leaves_state_unchanged():
    def boom(m, ev):
        raise KeyError('boom')

    m = Machine(['a', 'b'], [Transition('go', 'a', 'b', action=boom)], 'a')
    with pytest.raises(KeyError):
        m.fire('go')
    assert m.state == 'a' and m.history == []


def test_exception_in_on_enter_after_state_changed():
    def boom(m, ev):
        raise RuntimeError('enter failed')

    m = Machine(['a', State('b', on_enter=boom)], [Transition('go', 'a', 'b')], 'a')
    with pytest.raises(RuntimeError):
        m.fire('go')
    assert m.state == 'b'
    assert m.history == [('a', 'go', 'b')]


def test_reentrant_fire_raises_and_machine_stays_usable():
    def enter_b(m, ev):
        m.fire('back')

    m = Machine(['a', State('b', on_enter=enter_b)],
                [Transition('go', 'a', 'b'), Transition('back', 'b', 'a')], 'a')
    with pytest.raises(MachineError) as exc:
        m.fire('go')
    assert not isinstance(exc.value, (InvalidTransition, GuardRejected))
    assert m.state == 'b'
    assert m.fire('back') == 'a'


def test_can_fire_calls_guards_only():
    log = []
    m = Machine([State('a', on_exit=lambda m, ev: log.append('exit')), 'b'],
                [Transition('go', 'a', 'b', guard=lambda m, ev: ev.data.get('n', 0) > 2,
                            action=lambda m, ev: log.append('act'))], 'a')
    assert m.can_fire('go', n=3) is True
    assert m.can_fire('go', n=1) is False
    assert m.can_fire('nope') is False
    assert log == [] and m.state == 'a' and m.history == []


def test_available_events_sorted_unique_ignoring_guards():
    m = Machine(['a', 'b'], [
        Transition('zeta', 'a', 'b'),
        Transition('alpha', 'a', 'b', guard=lambda m, ev: False),
        Transition('alpha', '*', 'a'),
        Transition('only_b', 'b', 'a'),
    ], 'a')
    assert m.available_events() == ['alpha', 'zeta']
    m.fire('zeta')
    assert m.available_events() == ['alpha', 'only_b']


def test_reset_restores_initial_without_hooks():
    m, log = door()
    m.fire('open')
    m.fire('close')
    m.fire('lock')
    log.clear()
    m.reset()
    assert m.state == 'closed' and m.history == [] and log == []
    assert m.fire('lock') == 'locked'
