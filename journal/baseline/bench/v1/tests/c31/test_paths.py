import copy
import random

import pytest

from paths import dijkstra, shortest_path

G = {
    'a': {'b': 7, 'c': 9, 'f': 14},
    'b': {'a': 7, 'c': 10, 'd': 15},
    'c': {'a': 9, 'b': 10, 'd': 11, 'f': 2},
    'd': {'b': 15, 'c': 11, 'e': 6},
    'e': {'d': 6, 'f': 9},
    'f': {'a': 14, 'c': 2, 'e': 9},
}


def test_classic_distances():
    dist, prev = dijkstra(G, 'a')
    assert dist == {'a': 0, 'b': 7, 'c': 9, 'd': 20, 'e': 20, 'f': 11}
    assert prev == {'a': None, 'b': 'a', 'c': 'a', 'd': 'c', 'e': 'f', 'f': 'c'}


def test_shortest_path():
    assert shortest_path(G, 'a', 'e') == ['a', 'c', 'f', 'e']
    assert shortest_path(G, 'a', 'd') == ['a', 'c', 'd']
    assert shortest_path(G, 'e', 'e') == ['e']


def test_longer_path_with_fewer_hops_loses():
    g = {'s': {'t': 10, 'x': 1}, 'x': {'y': 1}, 'y': {'t': 1}}
    assert shortest_path(g, 's', 't') == ['s', 'x', 'y', 't']
    assert dijkstra(g, 's')[0]['t'] == 3


def test_target_only_nodes_are_nodes():
    g = {'a': {'b': 2, 'c': 5}, 'b': {'c': 1}}
    dist, prev = dijkstra(g, 'a')
    assert dist == {'a': 0, 'b': 2, 'c': 3}
    assert prev['c'] == 'b'
    assert shortest_path(g, 'a', 'c') == ['a', 'b', 'c']
    dist, prev = dijkstra(g, 'c')  # a sink as the source
    assert dist == {'a': None, 'b': None, 'c': 0}


def test_unreachable_is_none():
    g = {'a': {'b': 1}, 'c': {'d': 1}}
    dist, prev = dijkstra(g, 'a')
    assert dist['c'] is None and dist['d'] is None
    assert prev['c'] is None and prev['d'] is None
    assert prev['a'] is None
    assert shortest_path(g, 'a', 'd') is None


def test_zero_and_float_weights():
    g = {'a': {'b': 0, 'c': 1.5}, 'b': {'c': 0.25}}
    dist, _ = dijkstra(g, 'a')
    assert dist == {'a': 0, 'b': 0, 'c': 0.25}


def test_unknown_nodes_raise_key_error():
    with pytest.raises(KeyError):
        dijkstra(G, 'zz')
    with pytest.raises(KeyError):
        shortest_path(G, 'a', 'zz')
    with pytest.raises(KeyError):
        shortest_path(G, 'zz', 'a')


def test_negative_weight_anywhere_raises():
    g = {'a': {'b': 1}, 'c': {'d': -1}}
    with pytest.raises(ValueError):
        dijkstra(g, 'a')
    with pytest.raises(ValueError):
        shortest_path(g, 'a', 'b')


def test_uncomparable_nodes():
    a, b, c = object(), object(), object()
    g = {a: {b: 1, c: 1}, b: {c: 1}}
    dist, _ = dijkstra(g, a)
    assert dist[c] == 1


def test_graph_not_modified():
    g = copy.deepcopy(G)
    dijkstra(g, 'a')
    shortest_path(g, 'a', 'e')
    assert g == G


def bellman_ford(g, src):
    nodes = set(g) | {v for e in g.values() for v in e}
    dist = {n: None for n in nodes}
    dist[src] = 0
    for _ in range(len(nodes)):
        for u, edges in g.items():
            if dist[u] is None:
                continue
            for v, w in edges.items():
                if dist[v] is None or dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w
    return dist


def test_random_graphs_match_bellman_ford():
    rng = random.Random(31)
    for _ in range(60):
        n = rng.randrange(2, 12)
        g = {}
        for _ in range(rng.randrange(0, 30)):
            u, v = rng.randrange(n), rng.randrange(n)
            g.setdefault(u, {})[v] = rng.randrange(0, 20)
        g.setdefault(0, {})
        dist, prev = dijkstra(g, 0)
        assert dist == bellman_ford(g, 0)
        for node, d in dist.items():
            if d is None or node == 0:
                continue
            p = shortest_path(g, 0, node)
            assert p[0] == 0 and p[-1] == node
            assert sum(g[x][y] for x, y in zip(p, p[1:])) == d
            assert g[prev[node]][node] + dist[prev[node]] == d
