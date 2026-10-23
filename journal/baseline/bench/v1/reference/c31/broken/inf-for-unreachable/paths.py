import heapq
import itertools


def _nodes(graph):
    nodes = dict.fromkeys(graph)
    for edges in graph.values():
        nodes.update(dict.fromkeys(edges))
    return list(nodes)


def _check(graph):
    for u, edges in graph.items():
        for v, w in edges.items():
            if w < 0:
                raise ValueError(f'negative weight on edge {u!r} -> {v!r}')


def dijkstra(graph, src):
    nodes = _nodes(graph)
    if src not in nodes:
        raise KeyError(src)
    _check(graph)
    dist = dict.fromkeys(nodes)
    prev = dict.fromkeys(nodes)
    dist[src] = 0
    done = set()
    tie = itertools.count()
    heap = [(0, next(tie), src)]
    while heap:
        d, _, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        for v, w in graph.get(u, {}).items():
            nd = d + w
            if v not in done and (dist[v] is None or nd < dist[v]):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, next(tie), v))
    for k in dist:
        if dist[k] is None:
            dist[k] = float('inf')
    return dist, prev


def shortest_path(graph, src, dst):
    nodes = _nodes(graph)
    if dst not in nodes:
        raise KeyError(dst)
    dist, prev = dijkstra(graph, src)
    if dist[dst] == float('inf'):
        return None
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    path.reverse()
    return path
