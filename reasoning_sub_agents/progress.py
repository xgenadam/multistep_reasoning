"""Live pipeline status for UIs (Gradio trace box, chat yields)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class LiveState:
    phase: str = ''
    llm_label: str = ''
    llm_count: int = 0
    sub_tasks: list[dict] = field(default_factory=list)
    document_text: str = ''
    user_query: str = ''
    turn_debug: str = ''

    def snapshot(self) -> str:
        lines = [
            f'## this is the user\'s request\n{self.user_query or "(unknown)"}',
            f'## Phase\n{self.phase or "(starting)"}',
            f'## Current LLM call #{self.llm_count}\n{self.llm_label or "(idle)"}',
        ]
        if self.turn_debug.strip():
            lines.extend(['', '## turn pick (v5)', self.turn_debug.strip()])
        lines.extend([
            '',
            '## Sub-tasks',
        ])
        if not self.sub_tasks:
            lines.append('(none yet — still decomposing)')
        else:
            for idx, task in enumerate(self.sub_tasks, start=1):
                lines.append(f'{idx}. [{task.get("status", "?")}] {task.get("name", "?")}')
        if self.document_text.strip():
            lines.append('')
            lines.append('## Document (latest)')
            lines.append(self.document_text)
        else:
            lines.append('')
            lines.append('## Document (latest)')
            lines.append('(not written yet)')
        return '\n'.join(lines)


_live: ContextVar[LiveState | None] = ContextVar('multistep_live', default=None)
_on_change: ContextVar[Callable[[str], None] | None] = ContextVar(
    'multistep_live_cb', default=None
)


def live() -> LiveState | None:
    return _live.get()


def notify() -> None:
    callback = _on_change.get()
    state = _live.get()
    if callback is not None and state is not None:
        callback(state.snapshot())


@contextmanager
def live_session(
    on_change: Callable[[str], None] | None = None,
) -> Iterator[LiveState]:
    state = LiveState()
    live_token = _live.set(state)
    cb_token = _on_change.set(on_change)
    try:
        yield state
    finally:
        _live.reset(live_token)
        _on_change.reset(cb_token)


def set_user_query(text: str) -> None:
    state = live()
    if state is None:
        return
    state.user_query = text
    notify()


def set_turn_debug(text: str) -> None:
    state = live()
    if state is None:
        return
    state.turn_debug = text or ''
    notify()


def set_phase(phase: str) -> None:
    state = live()
    if state is None:
        return
    state.phase = phase
    notify()


def set_sub_tasks(names: list[str], status: str = 'queued') -> None:
    state = live()
    if state is None:
        return
    state.sub_tasks = [{'name': name, 'status': status} for name in names]
    notify()


def set_document(text: str) -> None:
    """Publish the current composed document for the live trace (not the chat)."""
    state = live()
    if state is None:
        return
    state.document_text = text or ''
    notify()


def set_task_status(name: str, status: str) -> None:
    state = live()
    if state is None:
        return
    for task in state.sub_tasks:
        if task.get('name') == name:
            task['status'] = status
            break
    notify()


# The kinds of model call (0-14's harness labels). llm_step sites name theirs,
# so per-step settings (thinking, D-013) key on the same set.
STEP_KINDS = (
    'decompose',
    'decompose_critique',
    'executor_turn',
    'oracle',
    'compose',
    'consolidate',
    'summary',
)
_step_kind: ContextVar[str | None] = ContextVar('multistep_step_kind', default=None)


def current_step_kind() -> str | None:
    """The kind named by the innermost llm_step, or None outside one."""
    return _step_kind.get()


@contextmanager
def llm_step(label: str, kind: str | None = None) -> Iterator[None]:
    if kind is not None and kind not in STEP_KINDS:
        raise ValueError(f'unknown step kind {kind!r}; expected one of {STEP_KINDS}')
    state = live()
    if state is not None:
        state.llm_label = label
        notify()
    kind_token = _step_kind.set(kind)
    try:
        yield
    finally:
        _step_kind.reset(kind_token)


def begin_llm(default_label: str = 'LLM call') -> None:
    """Called from llama_utils at the start of every model generate."""
    state = live()
    if state is None:
        return
    if not state.llm_label:
        state.llm_label = default_label
    state.llm_count += 1
    notify()
