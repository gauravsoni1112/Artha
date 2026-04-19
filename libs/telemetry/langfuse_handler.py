"""
Langfuse integration for LLM-level observability.

Uses Langfuse v2 SDK (client.trace / client.span / client.generation) which is
compatible with the Langfuse v2 server shipped in docker-compose.yml.

A custom _LangfuseCallbackHandler is wired into every LangGraph execution so
LLM calls and tool calls appear as nested spans under the orchestrator trace —
without depending on the broken langfuse.callback path (which requires the
old langchain v0 import style).

Usage:
    from libs.telemetry.langfuse_handler import get_callback_handler, create_trace

    lf_trace = create_trace(
        trace_id=str(trace_id),
        name="orchestrator.recommendation",
        user_id=str(owner_id),
        input={"query": query},
    )

    handler = get_callback_handler(trace_id=str(trace_id), ...)
    await graph.ainvoke(
        {"messages": messages},
        config={"callbacks": [h for h in [handler] if h is not None]},
    )

    if lf_trace is not None:
        lf_trace.update(output={"confidence": ..., "gaps": ...})
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import structlog

log = structlog.get_logger(__name__)

_client: Any = None
_client_ready: bool = False


def _get_client() -> Any | None:
    global _client, _client_ready
    if _client_ready:
        return _client

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    if not public_key or not secret_key:
        return None

    try:
        from langfuse import Langfuse  # noqa: PLC0415

        _client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
        )
        _client_ready = True
        log.info("langfuse.client_initialised", host=os.getenv("LANGFUSE_HOST"))
    except ImportError:
        log.warning("langfuse.not_installed", hint="pip install langfuse")
    except Exception as exc:
        log.warning("langfuse.init_failed", error=str(exc))

    return _client


def _serialize(obj: Any) -> Any:
    """Best-effort conversion of LangChain objects to JSON-safe structures."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    # BaseMessage and similar pydantic models
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump())
    if hasattr(obj, "dict"):
        try:
            return _serialize(obj.dict())
        except Exception:
            pass
    return str(obj)


class _LangfuseCallbackHandler:
    """
    LangGraph/LangChain callback handler backed by Langfuse v2 REST API.

    Inherits from langchain_core.callbacks.BaseCallbackHandler so it is
    accepted by graph.ainvoke(config={"callbacks": [...]}).  Does NOT use
    langfuse.callback (which requires old langchain v0 imports).
    """

    # Import base class lazily so the module loads even without langchain_core.
    _base_cls: type | None = None

    @classmethod
    def _get_base(cls) -> type:
        if cls._base_cls is None:
            from langchain_core.callbacks import BaseCallbackHandler  # noqa: PLC0415
            cls._base_cls = BaseCallbackHandler
        return cls._base_cls

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    def __init__(self, agent_span: Any, agent_id: str) -> None:
        # Dynamically make this a proper subclass of BaseCallbackHandler.
        base = self._get_base()
        if not isinstance(self, base):
            self.__class__ = type(
                "_LangfuseCallbackHandlerBound",
                (self.__class__, base),
                {},
            )
            base.__init__(self)  # type: ignore[arg-type]

        self._span = agent_span
        self._agent_id = agent_id
        # run_id → StatefulGenerationClient
        self._generations: dict[str, Any] = {}
        # run_id → StatefulSpanClient  (tool spans)
        self._tool_spans: dict[str, Any] = {}

    # ── LLM / chat-model callbacks ────────────────────────────────────────────

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        try:
            model_name = (
                serialized.get("kwargs", {}).get("model_name")
                or serialized.get("kwargs", {}).get("model")
                or (serialized.get("id") or ["unknown"])[-1]
            )
            gen = self._span.generation(
                id=str(run_id),
                name=model_name,
                model=model_name,
                input=_serialize(messages),
            )
            self._generations[str(run_id)] = gen
        except Exception as exc:
            log.warning("langfuse.on_chat_model_start_error", error=str(exc))

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        try:
            model_name = (serialized.get("id") or ["unknown"])[-1]
            gen = self._span.generation(
                id=str(run_id),
                name=model_name,
                model=model_name,
                input=prompts,
            )
            self._generations[str(run_id)] = gen
        except Exception as exc:
            log.warning("langfuse.on_llm_start_error", error=str(exc))

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            gen = self._generations.pop(str(run_id), None)
            if gen is None:
                return
            llm_out = response.llm_output or {}
            usage_raw = llm_out.get("token_usage") or llm_out.get("usage", {})
            from langfuse.model import ModelUsage  # noqa: PLC0415

            usage = ModelUsage(
                input=usage_raw.get("prompt_tokens"),
                output=usage_raw.get("completion_tokens"),
                total=usage_raw.get("total_tokens"),
            ) if usage_raw else None

            # Extract text from first generation
            output_text: Any = None
            if response.generations:
                first = response.generations[0]
                if first:
                    g = first[0]
                    output_text = getattr(g, "text", None) or _serialize(g)

            gen.end(output=output_text, usage=usage)
        except Exception as exc:
            log.warning("langfuse.on_llm_end_error", error=str(exc))

    def on_llm_error(self, error: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            gen = self._generations.pop(str(run_id), None)
            if gen:
                gen.end(level="ERROR", status_message=str(error))
        except Exception as exc:
            log.warning("langfuse.on_llm_error_error", error=str(exc))

    # ── Tool callbacks ────────────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        try:
            name = serialized.get("name") or (serialized.get("id") or ["tool"])[-1]
            span = self._span.span(
                id=str(run_id),
                name=name,
                input={"input": input_str},
            )
            self._tool_spans[str(run_id)] = span
        except Exception as exc:
            log.warning("langfuse.on_tool_start_error", error=str(exc))

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            span = self._tool_spans.pop(str(run_id), None)
            if span:
                span.end(output=_serialize(output))
        except Exception as exc:
            log.warning("langfuse.on_tool_end_error", error=str(exc))

    def on_tool_error(self, error: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            span = self._tool_spans.pop(str(run_id), None)
            if span:
                span.end(level="ERROR", status_message=str(error))
        except Exception as exc:
            log.warning("langfuse.on_tool_error_error", error=str(exc))


def get_callback_handler(
    trace_id: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """
    Return a LangGraph CallbackHandler linked to *trace_id*.

    Every LLM call and tool call inside the invocation is recorded as a child
    span of the orchestrator trace.  Returns None if Langfuse is not configured.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        agent_id = (metadata or {}).get("agent_id", "agent")
        # Re-open the existing trace (no network call; just a client-side handle).
        trace = client.trace(id=trace_id)
        # Create an agent-level span so LLM/tool spans nest under it.
        agent_span = trace.span(
            name=agent_id,
            metadata=metadata or {},
        )
        return _LangfuseCallbackHandler(agent_span=agent_span, agent_id=agent_id)
    except Exception as exc:
        log.warning("langfuse.callback_handler_error", error=str(exc))
        return None


def create_trace(
    trace_id: str,
    name: str,
    user_id: str | None = None,
    input: Any = None,  # noqa: A002
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """
    Open a top-level Langfuse trace.

    All agent CallbackHandlers that share the same *trace_id* will appear as
    children of this trace in the Langfuse UI.

    Returns a StatefulTraceClient (supports .update(output=...)) or None.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        return client.trace(
            id=trace_id,
            name=name,
            user_id=user_id,
            input=input,
            metadata=metadata or {},
        )
    except Exception as exc:
        log.warning("langfuse.trace_create_error", error=str(exc))
        return None


def flush() -> None:
    """
    Flush all pending Langfuse events synchronously.

    Call at the end of each request and during shutdown so spans appear in the
    dashboard immediately rather than waiting for the background batch timer.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:
        log.warning("langfuse.flush_error", error=str(exc))
