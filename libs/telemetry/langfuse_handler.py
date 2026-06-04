"""
Langfuse integration for LLM-level observability.

Uses Langfuse v2 SDK (client.trace / client.span / client.generation) which is
compatible with the Langfuse v2 server shipped in docker-compose.yml.

A custom _LangfuseCallbackHandler is wired into every LangGraph execution so
LLM calls and tool calls appear as nested spans under the orchestrator trace —
without depending on the broken langfuse.callback path (which requires the
old langchain v0 import style).

Key behaviours:
- Spans are created lazily on the first LLM/tool start, so roles that are
  skipped (e.g. compactor when no compaction runs) leave no empty spans.
- Token usage falls back to response.generations[*].message.usage_metadata
  (LangChain v0.2+) when llm_output.token_usage is absent (e.g. Ollama).
- Message content is truncated at _PAYLOAD_MAX_CHARS to avoid Langfuse
  bandwidth / storage bloat from large tool results.
- score_trace() attaches a named numeric score to any trace (e.g. confidence).
- end_callback_span() closes a handler's role-level span with final output.

Usage:
    lf_trace = create_trace(trace_id=str(trace_id), name="...", user_id=..., input=...)

    handler = get_callback_handler(trace_id=str(trace_id), node_name="executor", ...)
    await graph.ainvoke({"messages": messages}, config={"callbacks": [handler]})

    end_callback_span(handler, output={"answer": "...", "confidence": 0.82})
    score_trace(str(trace_id), name="confidence", value=0.82)

    if lf_trace is not None:
        lf_trace.update(output={...})
    flush()
"""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import structlog

log = structlog.get_logger(__name__)

_client: Any = None
_client_ready: bool = False


def _record_export_error(operation: str) -> None:
    try:
        from services.agent.metrics import record_langfuse_export_error  # noqa: PLC0415
        record_langfuse_export_error(operation)
    except Exception:
        pass

# Truncate serialised string fields to this length to keep payloads small.
_PAYLOAD_MAX_CHARS: int = int(os.getenv("LANGFUSE_PAYLOAD_MAX_CHARS", "4096"))


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
    """Best-effort conversion of LangChain objects to JSON-safe structures.

    String fields are truncated at _PAYLOAD_MAX_CHARS to prevent oversized payloads.
    """
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, str):
        return obj[:_PAYLOAD_MAX_CHARS] if len(obj) > _PAYLOAD_MAX_CHARS else obj
    if isinstance(obj, (int, float)):
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
    return str(obj)[:_PAYLOAD_MAX_CHARS]


class _LangfuseCallbackHandler:
    """
    LangGraph/LangChain callback handler backed by Langfuse v2 REST API.

    The role-level span is created lazily on the first LLM or tool start call,
    so skipped roles (e.g. compactor when the message list is short) leave no
    empty spans in the Langfuse UI.
    """

    _base_cls: type | None = None

    @classmethod
    def _get_base(cls) -> type:
        if cls._base_cls is None:
            from langchain_core.callbacks import BaseCallbackHandler  # noqa: PLC0415
            cls._base_cls = BaseCallbackHandler
        return cls._base_cls

    def __init__(
        self,
        trace: Any,
        span_name: str,
        agent_id: str,
        span_metadata: dict[str, Any] | None = None,
    ) -> None:
        base = self._get_base()
        if not isinstance(self, base):
            self.__class__ = type(
                "_LangfuseCallbackHandlerBound",
                (self.__class__, base),
                {},
            )
            base.__init__(self)  # type: ignore[arg-type]

        self._trace = trace
        self._span_name = span_name
        self._agent_id = agent_id
        self._span_metadata = span_metadata or {}
        # Lazily created on first LLM/tool event
        self._span: Any = None
        # run_id → StatefulGenerationClient
        self._generations: dict[str, Any] = {}
        # run_id → StatefulSpanClient  (tool spans)
        self._tool_spans: dict[str, Any] = {}

    def _ensure_span(self) -> Any:
        """Create the role-level span on first use."""
        if self._span is None:
            try:
                self._span = self._trace.span(
                    name=self._span_name,
                    metadata=self._span_metadata,
                )
            except Exception as exc:
                log.warning("langfuse.span_create_error", error=str(exc))
        return self._span

    def end_span(self, output: Any = None) -> None:
        """Close the role-level span with optional output. No-op if span was never opened."""
        if self._span is not None:
            try:
                self._span.end(output=_serialize(output))
            except Exception as exc:
                log.warning("langfuse.span_end_error", error=str(exc))

    # ── LLM / chat-model callbacks ────────────────────────────────────────────

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model_name = (
            serialized.get("kwargs", {}).get("model_name")
            or serialized.get("kwargs", {}).get("model")
            or (serialized.get("id") or ["unknown"])[-1]
        )
        span = self._ensure_span()
        if span is None:
            return
        try:
            gen = span.generation(
                id=str(run_id),
                name=model_name,
                model=model_name,
                input=_serialize(messages),
            )
            self._generations[str(run_id)] = gen
        except Exception as exc:
            log.warning("langfuse.on_chat_model_start_error", error=str(exc))
            _record_export_error("on_chat_model_start")

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        model_name = (serialized.get("id") or ["unknown"])[-1]
        span = self._ensure_span()
        if span is None:
            return
        try:
            gen = span.generation(
                id=str(run_id),
                name=model_name,
                model=model_name,
                input=_serialize(prompts),
            )
            self._generations[str(run_id)] = gen
        except Exception as exc:
            log.warning("langfuse.on_llm_start_error", error=str(exc))
            _record_export_error("on_llm_start")

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            gen = self._generations.pop(str(run_id), None)
            if gen is None:
                return
            llm_out = response.llm_output or {}
            usage_raw = llm_out.get("token_usage") or llm_out.get("usage", {})

            # Fallback: LangChain v0.2+ puts usage in generations[0][0].message.usage_metadata
            if not usage_raw and response.generations:
                first_row = response.generations[0]
                if first_row:
                    g0 = first_row[0]
                    msg = getattr(g0, "message", None)
                    if msg is not None:
                        usage_raw = getattr(msg, "usage_metadata", {}) or {}

            usage = None
            if usage_raw:
                try:
                    from langfuse.model import ModelUsage  # noqa: PLC0415
                    usage = ModelUsage(
                        input=usage_raw.get("prompt_tokens") or usage_raw.get("input_tokens"),
                        output=usage_raw.get("completion_tokens") or usage_raw.get("output_tokens"),
                        total=usage_raw.get("total_tokens"),
                    )
                except Exception:
                    pass

            output_text: Any = None
            tool_calls_data: Any = None
            if response.generations:
                first = response.generations[0]
                if first:
                    g = first[0]
                    output_text = getattr(g, "text", None) or None

                    msg = getattr(g, "message", None)
                    if msg is not None:
                        # Capture structured tool-call decisions (name + args) for audit
                        raw_calls = getattr(msg, "tool_calls", None)
                        if raw_calls:
                            tool_calls_data = _serialize(raw_calls)

                        # Capture Claude extended-thinking blocks if present
                        content_blocks = getattr(msg, "content", None)
                        if isinstance(content_blocks, list):
                            thinking_text = "\n\n".join(
                                b.get("thinking", "")
                                for b in content_blocks
                                if isinstance(b, dict) and b.get("type") == "thinking"
                            )
                            if thinking_text:
                                output_text = (
                                    f"[thinking]\n{thinking_text}\n\n{output_text}"
                                    if output_text
                                    else f"[thinking]\n{thinking_text}"
                                )

                    if output_text is None:
                        output_text = _serialize(g)

            gen.end(
                output=output_text,
                usage=usage,
                metadata={"tool_calls": tool_calls_data} if tool_calls_data else None,
            )
        except Exception as exc:
            log.warning("langfuse.on_llm_end_error", error=str(exc))
            _record_export_error("on_llm_end")

    def on_llm_error(self, error: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            gen = self._generations.pop(str(run_id), None)
            if gen:
                gen.end(level="ERROR", status_message=str(error))
        except Exception as exc:
            log.warning("langfuse.on_llm_error_error", error=str(exc))
            _record_export_error("on_llm_error")

    # ── Tool callbacks ────────────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        span = self._ensure_span()
        if span is None:
            return
        try:
            name = serialized.get("name") or (serialized.get("id") or ["tool"])[-1]
            tool_span = span.span(
                id=str(run_id),
                name=name,
                input={"input": input_str[:_PAYLOAD_MAX_CHARS]},
            )
            self._tool_spans[str(run_id)] = tool_span
        except Exception as exc:
            log.warning("langfuse.on_tool_start_error", error=str(exc))
            _record_export_error("on_tool_start")

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            tool_span = self._tool_spans.pop(str(run_id), None)
            if tool_span:
                tool_span.end(output=_serialize(output))
        except Exception as exc:
            log.warning("langfuse.on_tool_end_error", error=str(exc))
            _record_export_error("on_tool_end")

    def on_tool_error(self, error: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            tool_span = self._tool_spans.pop(str(run_id), None)
            if tool_span:
                tool_span.end(level="ERROR", status_message=str(error))
        except Exception as exc:
            log.warning("langfuse.on_tool_error_error", error=str(exc))
            _record_export_error("on_tool_error")


def get_callback_handler(
    trace_id: str,
    user_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    node_name: str | None = None,
) -> Any | None:
    """
    Return a LangGraph CallbackHandler linked to *trace_id*.

    The role-level span is created lazily on the first LLM/tool event, so
    roles that are bypassed (e.g. compactor when no compaction fires) leave
    no empty spans in the Langfuse UI.

    Returns None if Langfuse is not configured.
    """
    client = _get_client()
    if client is None:
        return None

    try:
        agent_id = (metadata or {}).get("agent_id", "agent")
        span_name = f"{agent_id}/{node_name}" if node_name else agent_id
        span_metadata = {**(metadata or {}), "node": node_name or "unknown"}
        trace = client.trace(id=trace_id)
        return _LangfuseCallbackHandler(
            trace=trace,
            span_name=span_name,
            agent_id=span_name,
            span_metadata=span_metadata,
        )
    except Exception as exc:
        log.warning("langfuse.callback_handler_error", error=str(exc))
        return None


def end_callback_span(handler: Any | None, output: Any = None) -> None:
    """Close a handler's role-level span with optional output. Safe to call on None."""
    if handler is not None and hasattr(handler, "end_span"):
        handler.end_span(output=output)


def score_trace(trace_id: str, name: str, value: float, comment: str | None = None) -> None:
    """
    Attach a named numeric score to an existing Langfuse trace.

    Useful for surfacing agent-level confidence, critic penalty, etc. so you
    can filter/slice runs in the Langfuse dashboard without drilling into spans.
    No-op if Langfuse is not configured.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )
    except Exception as exc:
        log.warning("langfuse.score_trace_error", trace_id=trace_id, name=name, error=str(exc))
        _record_export_error("score_trace")


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
        _record_export_error("create_trace")
        return None


def flush() -> None:
    """
    Flush all pending Langfuse events synchronously.

    Call once per request at the orchestrator level — not per-agent — so that
    parallel agent calls don't each block on a sync flush to Langfuse.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:
        log.warning("langfuse.flush_error", error=str(exc))
        _record_export_error("flush")
