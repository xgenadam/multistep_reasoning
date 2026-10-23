"""Topological sort, parallel levels and target subgraphs, with cycle reporting."""
import heapq


class CycleError(ValueError):
    def __init__(self, cycle: list[str]):
        super().__init__('dependency cycle: ' + ' -> '.join(cycle + cycle[:1]))
        self.cycle = cycle


def _normalise(graph) -> dict[str, set[str]]:
    deps: dict[str, set[str]] = {}
    for node, needs in graph.items():
        deps.setdefault(node, set()).update(needs)
        for dep in deps[node]:
            deps.setdefault(dep, set())
    return deps


def _find_cycle(deps: dict[str, set[str]], nodes: set[str]) -> list[str]:
    """A cycle among `nodes`, every one of which is on or leads to a cycle."""
    start = min(nodes)
    path, index = [], {}
    node = start
    while node not in index:
        index[node] = len(path)
        path.append(node)
        node = min(d for d in deps[node] if d in nodes)
    return path[index[node]:]


def toposort(graph) -> list[str]:
    deps = _normalise(graph)
    waiting = {node: len(needs) for node, needs in deps.items()}
    dependents: dict[str, list[str]] = {node: [] for node in deps}
    for node, needs in deps.items():
        for dep in needs:
            dependents[dep].append(node)
    ready = [node for node, count in waiting.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for parent in dependents[node]:
            waiting[parent] -= 1
            if waiting[parent] == 0:
                heapq.heappush(ready, parent)
    if len(order) < len(deps):
        stuck = set(deps) - set(order)
        raise CycleError(_find_cycle(deps, stuck))
    return order


def levels(graph) -> list[list[str]]:
    deps = _normalise(graph)
    level: dict[str, int] = {}
    for node in toposort(graph):  # raises CycleError on a cycle
        level[node] = 1 if deps[node] else 0
    layers: list[list[str]] = [[] for _ in range(max(level.values(), default=-1) + 1)]
    for node, k in level.items():
        layers[k].append(node)
    return [sorted(layer) for layer in layers]


def subgraph_order(graph, targets) -> list[str]:
    deps = _normalise(graph)
    needed: set[str] = set()
    stack = []
    for target in targets:
        if target not in deps:
            raise KeyError(target)
        stack.append(target)
    while stack:
        node = stack.pop()
        if node in needed:
            continue
        needed.add(node)
        stack.extend(deps[node] - needed)
    return toposort({node: deps[node] for node in needed})
