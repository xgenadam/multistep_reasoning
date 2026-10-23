import random

import pytest

from toposort import CycleError, levels, subgraph_order, toposort


def deps_of(graph):
    out = {}
    for node, needs in graph.items():
        out.setdefault(node, set()).update(needs)
        for d in needs:
            out.setdefault(d, set())
    return out


def assert_valid_cycle(graph, cycle):
    deps = deps_of(graph)
    assert isinstance(cycle, list) and cycle and len(set(cycle)) == len(cycle)
    for i, node in enumerate(cycle):
        assert cycle[(i + 1) % len(cycle)] in deps[node]


def random_dag(rng, n_max=14):
    names = rng.sample([f'n{k:02d}' for k in range(40)], rng.randrange(1, n_max))
    graph = {}
    for i, name in enumerate(names):
        if rng.random() < 0.8:
            graph[name] = rng.sample(names[i + 1:], min(len(names) - i - 1, rng.randrange(0, 4)))
    return graph


BUILD = {'app': ['lib', 'log'], 'lib': ['log'], 'cli': ['log']}


def test_levels_example():
    assert levels(BUILD) == [['log'], ['cli', 'lib'], ['app']]


def test_levels_empty_and_flat():
    assert levels({}) == []
    assert levels({'b': [], 'a': [], 'c': []}) == [['a', 'b', 'c']]


def test_levels_use_longest_chain():
    graph = {'top': ['a', 'd'], 'a': ['b'], 'b': ['c'], 'd': []}
    assert levels(graph) == [['c', 'd'], ['b'], ['a'], ['top']]


def test_levels_include_dependency_only_nodes():
    assert levels({'x': ['b', 'a']}) == [['a', 'b'], ['x']]


def test_levels_cycle():
    graph = {'a': ['b'], 'b': ['c'], 'c': ['b'], 'd': []}
    with pytest.raises(CycleError) as info:
        levels(graph)
    assert_valid_cycle(graph, info.value.cycle)


def test_levels_random_properties():
    rng = random.Random(21)
    for _ in range(200):
        graph = random_dag(rng)
        deps = deps_of(graph)
        layers = levels(graph)
        level = {n: k for k, layer in enumerate(layers) for n in layer}
        assert sorted(level) == sorted(deps)
        assert all(layer == sorted(layer) and layer for layer in layers)
        for node, needs in deps.items():
            expected = 1 + max((level[d] for d in needs), default=-1)
            assert level[node] == expected


def test_subgraph_only_needed_nodes():
    graph = {'app': ['lib'], 'lib': ['log'], 'cli': ['log', 'args'], 'docs': []}
    assert subgraph_order(graph, ['lib']) == ['log', 'lib']
    assert subgraph_order(graph, ['cli']) == ['args', 'log', 'cli']
    assert subgraph_order(graph, ['app', 'docs']) == ['docs', 'log', 'lib', 'app']


def test_subgraph_order_uses_tie_break_on_the_subgraph():
    graph = {'b': ['z'], 'a': ['y'], 'y': [], 'z': [], 'c': []}
    assert subgraph_order(graph, ['b', 'a']) == ['y', 'a', 'z', 'b']


def test_subgraph_targets_any_iterable_with_repeats():
    assert subgraph_order(BUILD, iter(['lib', 'lib', 'log'])) == ['log', 'lib']
    assert subgraph_order(BUILD, ()) == []


def test_subgraph_target_can_be_dependency_only_node():
    assert subgraph_order(BUILD, ['log']) == ['log']


def test_subgraph_unknown_target():
    with pytest.raises(KeyError):
        subgraph_order(BUILD, ['lib', 'nope'])


def test_subgraph_ignores_unrelated_cycle():
    graph = {'app': ['lib'], 'lib': [], 'x': ['y'], 'y': ['x']}
    assert subgraph_order(graph, ['app']) == ['lib', 'app']


def test_subgraph_reports_needed_cycle():
    graph = {'app': ['lib'], 'lib': ['core'], 'core': ['lib'], 'other': []}
    with pytest.raises(CycleError) as info:
        subgraph_order(graph, ['app'])
    assert sorted(info.value.cycle) == ['core', 'lib']
    assert_valid_cycle(graph, info.value.cycle)


def test_subgraph_does_not_modify_graph():
    graph = {'a': ['b'], 'b': []}
    subgraph_order(graph, ['a'])
    levels(graph)
    assert graph == {'a': ['b'], 'b': []}


def test_subgraph_random_matches_restricted_toposort():
    rng = random.Random(22)
    for _ in range(200):
        graph = random_dag(rng)
        deps = deps_of(graph)
        targets = rng.sample(sorted(deps), rng.randrange(0, min(4, len(deps)) + 1))
        needed, stack = set(), list(targets)
        while stack:
            n = stack.pop()
            if n not in needed:
                needed.add(n)
                stack.extend(deps[n])
        expected = toposort({n: deps[n] for n in needed})
        assert subgraph_order(graph, targets) == expected
