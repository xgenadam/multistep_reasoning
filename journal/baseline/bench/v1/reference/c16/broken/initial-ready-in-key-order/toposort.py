"""Topological sort with a lexicographic tie-break and cycle reporting."""
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
    order = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for parent in dependents[node]:
            waiting[parent] -= 1
            if waiting[parent] == 0:
                ready.append(parent)
    if len(order) < len(deps):
        stuck = set(deps) - set(order)
        raise CycleError(_find_cycle(deps, stuck))
    return order
