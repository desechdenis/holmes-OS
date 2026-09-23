"""Mesures légères, liées à une requête conversation par ContextVar."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class ConversationMetrics:
    started_at: float = field(default_factory=perf_counter)
    stages_ms: dict[str, float] = field(default_factory=dict)
    prompt_tokens: int = 0
    response_tokens: int = 0


_CURRENT: ContextVar[ConversationMetrics | None] = ContextVar(
    "holmes_conversation_metrics", default=None
)


def begin_metrics() -> tuple[ConversationMetrics, Token[ConversationMetrics | None]]:
    metrics = ConversationMetrics()
    return metrics, _CURRENT.set(metrics)


def end_metrics(token: Token[ConversationMetrics | None]) -> None:
    _CURRENT.reset(token)


@contextmanager
def metric_stage(name: str) -> Iterator[None]:
    metrics = _CURRENT.get()
    started = perf_counter()
    try:
        yield
    finally:
        if metrics is not None:
            elapsed_ms = (perf_counter() - started) * 1000
            metrics.stages_ms[name] = metrics.stages_ms.get(name, 0.0) + elapsed_ms


def record_tokens(*, prompt: int | None = None, response: int | None = None) -> None:
    metrics = _CURRENT.get()
    if metrics is None:
        return
    if prompt is not None:
        metrics.prompt_tokens = prompt
    if response is not None:
        metrics.response_tokens = response
