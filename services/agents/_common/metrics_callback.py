"""
LangChain callback handler that records OTel metrics for every LLM call.

Always active — no Langfuse dependency. Attach via MetricsCallbackHandler.make()
so BaseCallbackHandler is imported lazily (only when agent containers run).

Usage in base_agent.py:
    from services.agents._common.metrics_callback import MetricsCallbackHandler

    _metrics_cb = MetricsCallbackHandler.make(self.AGENT_ID)
    await graph.ainvoke(..., config={"callbacks": [_metrics_cb, ...]})
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from services.agent.metrics import record_llm_call


class MetricsCallbackHandler:
    """
    Records artha_llm_call_duration_seconds for every LLM/chat-model call.

    Use MetricsCallbackHandler.make(agent_id) to get an instance that is
    also a LangChain BaseCallbackHandler — the base class is bound lazily
    so importing this module never triggers a langchain import at module load.
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        # run_id → (perf_counter_start, model_name)
        self._start: dict[str, tuple[float, str]] = {}

    @classmethod
    def make(cls, agent_id: str) -> "MetricsCallbackHandler":
        """
        Return an instance that inherits from both MetricsCallbackHandler
        and langchain_core BaseCallbackHandler (imported here, not at module load).
        """
        from langchain_core.callbacks import BaseCallbackHandler  # noqa: PLC0415

        bound_cls = type("_MetricsCBBound", (cls, BaseCallbackHandler), {})
        instance = object.__new__(bound_cls)
        BaseCallbackHandler.__init__(instance)
        cls.__init__(instance, agent_id)
        return instance

    # ── LangChain callbacks ───────────────────────────────────────────────────

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or (serialized.get("id") or ["unknown"])[-1]
        )
        self._start[str(run_id)] = (time.perf_counter(), model)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model = (serialized.get("id") or ["unknown"])[-1]
        self._start[str(run_id)] = (time.perf_counter(), model)

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        info = self._start.pop(str(run_id), None)
        if info is not None:
            t0, model = info
            record_llm_call(self._agent_id, model, time.perf_counter() - t0)

    def on_llm_error(self, error: Any, *, run_id: UUID, **kwargs: Any) -> None:
        info = self._start.pop(str(run_id), None)
        if info is not None:
            t0, model = info
            record_llm_call(self._agent_id, model, time.perf_counter() - t0)
