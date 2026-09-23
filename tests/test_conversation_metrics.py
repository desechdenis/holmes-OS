from __future__ import annotations

from jarvis.engine.conversation_metrics import (
    begin_metrics,
    end_metrics,
    metric_stage,
    record_tokens,
)


def test_conversation_metrics_collect_stages_and_tokens() -> None:
    metrics, token = begin_metrics()
    try:
        with metric_stage("ha_context"):
            pass
        record_tokens(prompt=321, response=17)
    finally:
        end_metrics(token)

    assert metrics.stages_ms["ha_context"] >= 0
    assert metrics.prompt_tokens == 321
    assert metrics.response_tokens == 17
