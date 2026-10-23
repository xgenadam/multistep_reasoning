import random

import pytest

from toposort import CycleError, toposort


def deps_of(graph):
    out = {}
    for node, needs in graph.items():
        out.setdefault(node, set()).update(needs)
        for d in needs:
            out.setdefault(d, set())
    return out


def model(graph):
    deps = deps_of(graph)
    done, order = set(), []
    while len(order) < len(deps):
        ready = [n for n in deps if n not in done and deps[n] <= done]
        if not ready:
            return None
        nxt = min(ready)
        order.append(nxt)
        done.add(nxt)
    return order


def assert_valid_cycle(graph, cycle):
    deps = deps_of(graph)
    assert isinstance(cycle, list) and cycle
    assert len(set(cycle)) == len(cycle)
    for i, node in enumerate(cycle):
        assert cycle[(i + 1) % len(cycle)] in deps[node], (cycle, node)


def cycle_of(graph):
    with pytest.raises(CycleError) as info:
        toposort(graph)
    return info.value.cycle


def test_examples_from_the_spec():
    assert toposort({'b': [], 'a': [], 'c': ['b']}) == ['a', 'b', 'c']
    assert toposort({'z': [], 'a': ['z']}) == ['z', 'a']


def test_empty_graph():
    assert toposort({}) == []


def test_dependency_only_nodes_included():
    assert toposort({'app': ['lib', 'log'], 'lib': ['log']}) == ['log', 'lib', 'app']
    assert toposort({'x': ['b', 'a']}) == ['a', 'b', 'x']


def test_lexicographic_tie_break_not_insertion_order():
    graph = {'d': [], 'c': [], 'b': ['d'], 'a': ['d']}
    assert toposort(graph) == ['c', 'd', 'a', 'b']


def test_tie_break_applies_at_every_step():
    graph = {'m': ['k'], 'b': ['z'], 'k': [], 'z': []}
    # ready: k, z -> k; then m, z -> m; then z; then b
    assert toposort(graph) == ['k', 'm', 'z', 'b']


def test_duplicates_and_iterables():
    graph = {'a': ('b', 'b', 'c'), 'b': {'c'}, 'c': iter([])}
    assert toposort(graph) == ['c', 'b', 'a']


def test_input_not_modified():
    graph = {'a': ['b'], 'b': []}
    toposort(graph)
    assert graph == {'a': ['b'], 'b': []}


def test_self_dependency():
    graph = {'a': [], 'b': ['b']}
    assert cycle_of(graph) == ['b']


def test_two_node_cycle():
    graph = {'a': ['b'], 'b': ['a'], 'c': []}
    cycle = cycle_of(graph)
    assert sorted(cycle) == ['a', 'b']
    assert_valid_cycle(graph, cycle)


def test_cycle_direction():
    graph = {'a': ['b'], 'b': ['c'], 'c': ['a']}
    cycle = cycle_of(graph)
    assert_valid_cycle(graph, cycle)
    assert len(cycle) == 3


def test_cycle_behind_acyclic_part():
    graph = {'app': ['core'], 'core': ['util'], 'util': ['io'], 'io': ['core'], 'x': []}
    cycle = cycle_of(graph)
    assert_valid_cycle(graph, cycle)
    assert sorted(cycle) == ['core', 'io', 'util']


def test_cycle_error_is_value_error():
    with pytest.raises(ValueError):
        toposort({'a': ['a']})


def test_random_dags_match_rule():
    rng = random.Random(16)
    for _ in range(300):
        names = rng.sample([f'n{k:02d}' for k in range(40)], rng.randrange(1, 15))
        graph = {}
        for i, name in enumerate(names):
            if rng.random() < 0.8:
                graph[name] = rng.sample(names[i + 1:], min(len(names) - i - 1, rng.randrange(0, 4)))
        assert toposort(graph) == model(graph)


def test_random_cycles_are_real():
    rng = random.Random(17)
    found = 0
    for _ in range(300):
        names = [chr(ord('a') + k) for k in range(rng.randrange(1, 9))]
        graph = {n: rng.sample(names, rng.randrange(0, min(3, len(names) + 1))) for n in names}
        if model(graph) is None:
            found += 1
            assert_valid_cycle(graph, cycle_of(graph))
        else:
            assert toposort(graph) == model(graph)
    assert found > 50
