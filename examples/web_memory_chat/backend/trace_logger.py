# -*- coding: utf-8 -*-
"""Observability logging for the web-memory-chat backend.

Two layers of tracing:
  A) HTTP interceptor — logs outgoing HTTP requests (LLM API, Embedding, etc.)
  B) Framework-level structured logs — tags each operation with its layer

Configure what to show by editing TRACE_CONFIG below.
"""
from __future__ import annotations

import functools
import time
from datetime import datetime
from typing import Any


# ============================================================================
# TRACE CONFIGURATION — toggle each source on/off here
# ============================================================================
TRACE_CONFIG = {
    # ── Layer B: our structured trace tags ──
    "FRAMEWORK": True,    # agent lifecycle, chat start/done, session save
    "LLM_API":   True,    # outgoing LLM chat/completions calls
    "TOOL":      True,    # tool calls (brave_search, record/retrieve_memory)
    "REME":      True,    # ReMe memory init, record, retrieve
    "EMBEDDING": True,    # embedding API calls
    "PGVECTOR":  True,    # pgvector operations

    # ── Layer A: HTTP-level request/response ──
    "HTTP":      True,   # other HTTP calls not classified above

    # ── Third-party INFO logs (the noisy ones) ──
    "UVICORN":   True,    # Uvicorn request log  (INFO: 127.0.0.1 GET /...)
    "FLOWLLM":   True,   # flowllm internal logs (base_flow, timer, ops)
    "AGENTSCOPE": True,   # AgentScope logs (session, memory entry points)
    "AGENT_THINKING": True,  # Print agent's thinking/reasoning text
    "LLM_API_BODY":  True,   # Print full request/response body for LLM calls
}


# ============================================================================
# Formatting
# ============================================================================
_COLORS = {
    "FRAMEWORK": "\033[36m",   # cyan
    "LLM_API":   "\033[33m",   # yellow
    "TOOL":      "\033[32m",   # green
    "REME":      "\033[35m",   # magenta
    "EMBEDDING": "\033[34m",   # blue
    "PGVECTOR":  "\033[94m",   # light blue
    "HTTP":      "\033[90m",   # gray
    "RESET":     "\033[0m",
}


def _fmt(layer: str, action: str, **kwargs: Any) -> str:
    color = _COLORS.get(layer, "")
    reset = _COLORS["RESET"]
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    parts = " ".join(f"{k}={v}" for k, v in kwargs.items() if v is not None)
    return f"{color}[{ts}] [{layer:>9s}] {action}  {parts}{reset}"


# ============================================================================
# Logger with per-layer enable/disable
# ============================================================================
class _Logger:
    def _print(self, layer: str, action: str, **kw: Any) -> None:
        if TRACE_CONFIG.get(layer, False):
            print(_fmt(layer, action, **kw))

    def framework(self, action: str, **kw: Any) -> None:
        self._print("FRAMEWORK", action, **kw)

    def llm_api(self, action: str, **kw: Any) -> None:
        self._print("LLM_API", action, **kw)

    def tool(self, action: str, **kw: Any) -> None:
        self._print("TOOL", action, **kw)

    def reme(self, action: str, **kw: Any) -> None:
        self._print("REME", action, **kw)

    def embedding(self, action: str, **kw: Any) -> None:
        self._print("EMBEDDING", action, **kw)

    def pgvector(self, action: str, **kw: Any) -> None:
        self._print("PGVECTOR", action, **kw)

    def http(self, action: str, **kw: Any) -> None:
        self._print("HTTP", action, **kw)


log = _Logger()


# ============================================================================
# Layer A: HTTP interceptor (monkey-patches httpx)
# ============================================================================
def _classify_url(url: str) -> tuple[str, str]:
    if "/chat/completions" in url:
        return "LLM_API", "chat/completions"
    if "/embeddings/multimodal" in url:
        return "EMBEDDING", "embeddings/multimodal"
    if "/embeddings" in url:
        return "EMBEDDING", "embeddings"
    if "api.search.brave.com" in url:
        return "TOOL", "brave_search"
    return "HTTP", url.split("?")[0][-60:]


def install_http_tracing() -> None:
    """Monkey-patch httpx to log outgoing HTTP requests/responses."""
    import httpx

    _orig_async_send = httpx.AsyncClient.send
    _orig_sync_send = httpx.Client.send

    @functools.wraps(_orig_async_send)
    async def _traced_async_send(self: Any, request: Any, **kw: Any) -> Any:
        url = str(request.url)
        layer, label = _classify_url(url)
        if not TRACE_CONFIG.get(layer, False):
            return await _orig_async_send(self, request, **kw)

        t0 = time.monotonic()
        extra = _extract_request_info(request)
        log_fn = getattr(log, layer.lower(), log.http)
        log_fn(f">>> {label}", **extra)

        # Print request body for LLM API calls
        if layer == "LLM_API" and TRACE_CONFIG.get("LLM_API_BODY"):
            _print_request_body(request)

        response = await _orig_async_send(self, request, **kw)
        elapsed = (time.monotonic() - t0) * 1000
        log_fn(f"<<< {label}", status=response.status_code,
               time=f"{elapsed:.0f}ms")

        # Print response body for non-streaming LLM API calls
        if layer == "LLM_API" and TRACE_CONFIG.get("LLM_API_BODY"):
            _print_response_body(response)

        return response

    @functools.wraps(_orig_sync_send)
    def _traced_sync_send(self: Any, request: Any, **kw: Any) -> Any:
        url = str(request.url)
        layer, label = _classify_url(url)
        if not TRACE_CONFIG.get(layer, False):
            return _orig_sync_send(self, request, **kw)

        t0 = time.monotonic()
        extra = _extract_request_info(request)
        log_fn = getattr(log, layer.lower(), log.http)
        log_fn(f">>> {label}", **extra)

        if layer == "LLM_API" and TRACE_CONFIG.get("LLM_API_BODY"):
            _print_request_body(request)

        response = _orig_sync_send(self, request, **kw)
        elapsed = (time.monotonic() - t0) * 1000
        log_fn(f"<<< {label}", status=response.status_code,
               time=f"{elapsed:.0f}ms")

        if layer == "LLM_API" and TRACE_CONFIG.get("LLM_API_BODY"):
            _print_response_body(response)

        return response

    httpx.AsyncClient.send = _traced_async_send
    httpx.Client.send = _traced_sync_send
    log.framework("HTTP tracing installed")


def _print_request_body(request: Any) -> None:
    """Print LLM API request body (messages, tools, etc.)."""
    import json
    color = _COLORS.get("LLM_API", "")
    reset = _COLORS["RESET"]
    try:
        body = json.loads(request.content)
        # Print messages
        messages = body.get("messages", [])
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        btype = block.get("type", "")
                        if btype == "text":
                            parts.append(block.get("text", ""))
                        elif btype == "tool_use":
                            parts.append(f"[tool_use: {block.get('name')}({json.dumps(block.get('input', {}), ensure_ascii=False)})]")
                        elif btype == "tool_result":
                            parts.append(f"[tool_result: {str(block.get('output', block.get('content', '')))}]")
                        else:
                            parts.append(f"[{btype}: {json.dumps(block, ensure_ascii=False)}]")
                content = " | ".join(parts)
            elif not isinstance(content, str):
                content = str(content)
            print(f"{color}    [{role}] {content}{reset}")
        # Print tools if present
        tools = body.get("tools", [])
        if tools:
            names = [t.get("function", {}).get("name", "?") for t in tools]
            print(f"{color}    [tools] {', '.join(names)}{reset}")
        # Print stream flag
        if body.get("stream"):
            print(f"{color}    [stream=true]{reset}")
    except Exception:
        pass


def _print_response_body(response: Any) -> None:
    """Print LLM API response body for non-streaming, or wrap stream."""
    import json as _json
    color = _COLORS.get("LLM_API", "")
    reset = _COLORS["RESET"]
    try:
        ct = response.headers.get("content-type", "")
        if "event-stream" in ct or "stream" in ct:
            # Wrap the stream to collect and print after exhaustion
            _wrap_streaming_response(response)
            return
        body = _json.loads(response.content)
        _print_parsed_response(body, color, reset)
    except Exception:
        pass


def _print_parsed_response(
    body: dict, color: str, reset: str,
) -> None:
    """Print a parsed (non-streaming) LLM response."""
    choices = body.get("choices", [])
    usage = body.get("usage", {})
    for choice in choices:
        msg = choice.get("message", {})
        role = msg.get("role", "?")
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            print(f"{color}    [thinking] {reasoning}{reset}")
        if content:
            print(f"{color}    [{role}] {content}{reset}")
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            fn = tc.get("function", {})
            print(f"{color}    [tool_call] {fn.get('name', '?')}"
                  f"({fn.get('arguments', '')}){reset}")
    if usage:
        print(f"{color}    [usage] prompt={usage.get('prompt_tokens', '?')} "
              f"completion={usage.get('completion_tokens', '?')} "
              f"total={usage.get('total_tokens', '?')}{reset}")


def _wrap_streaming_response(response: Any) -> None:
    """Wrap httpx streaming response to collect SSE chunks and print
    the final assembled result after the stream is fully consumed."""
    import json as _json
    color = _COLORS.get("LLM_API", "")
    reset = _COLORS["RESET"]

    # Patch aiter_bytes to intercept chunks
    _orig_aiter_bytes = response.aiter_bytes

    collected = {
        "content": [],
        "reasoning": [],
        "tool_calls": {},   # index -> {name, arguments}
        "usage": {},
    }

    def _parse_chunk(raw: bytes) -> None:
        try:
            for line in raw.decode("utf-8", errors="replace").split("\n"):
                line = line.strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                data = _json.loads(line[6:])
                for choice in data.get("choices", []):
                    delta = choice.get("delta", {})
                    c = delta.get("content")
                    if c:
                        collected["content"].append(c)
                    r = delta.get("reasoning_content")
                    if r:
                        collected["reasoning"].append(r)
                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in collected["tool_calls"]:
                            collected["tool_calls"][idx] = {
                                "name": "", "arguments": "",
                            }
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            collected["tool_calls"][idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            collected["tool_calls"][idx]["arguments"] += fn["arguments"]
                u = data.get("usage")
                if u:
                    collected["usage"].update(u)
        except Exception:
            pass

    def _print_collected() -> None:
        if collected["reasoning"]:
            print(f"{color}    [thinking] "
                  f"{''.join(collected['reasoning'])}{reset}")
        if collected["content"]:
            print(f"{color}    [assistant] "
                  f"{''.join(collected['content'])}{reset}")
        for tc in sorted(collected["tool_calls"].values(),
                         key=lambda x: x.get("name", "")):
            print(f"{color}    [tool_call] {tc['name']}"
                  f"({tc['arguments']}){reset}")
        u = collected["usage"]
        if u:
            print(f"{color}    [usage] "
                  f"prompt={u.get('prompt_tokens', '?')} "
                  f"completion={u.get('completion_tokens', '?')} "
                  f"total={u.get('total_tokens', '?')}{reset}")

    async def _traced_aiter_bytes(*args: Any, **kwargs: Any):  # type: ignore
        async for chunk in _orig_aiter_bytes(*args, **kwargs):
            _parse_chunk(chunk)
            yield chunk
        _print_collected()

    response.aiter_bytes = _traced_aiter_bytes


def _extract_request_info(request: Any) -> dict[str, Any]:
    """Extract useful info from an httpx request for logging."""
    extra: dict[str, Any] = {"method": request.method}
    if request.content:
        try:
            import json
            body = json.loads(request.content)
            if "model" in body:
                extra["model"] = body["model"]
            if "messages" in body:
                extra["messages"] = len(body["messages"])
            if "input" in body and isinstance(body["input"], list):
                extra["inputs"] = len(body["input"])
        except Exception:
            pass
    url = str(request.url)
    if "q=" in url:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        if "q" in qs:
            extra["query"] = qs["q"][0]
    return extra


# ============================================================================
# Intercept third-party logs (flowllm loguru + uvicorn + agentscope)
# ============================================================================
_loguru_our_sink_id: int | None = None


def install_loguru_tracing() -> None:
    """Take over loguru so ALL output goes through our filtered sink.

    flowllm / ReMeApp add their own loguru sinks each time they
    initialise.  We monkey-patch ``loguru.logger.add`` so that any
    future sink added by third-party code is silently discarded.
    Only our own sink (identified by ``_loguru_our_sink_id``) survives.
    """
    global _loguru_our_sink_id
    try:
        from loguru import logger as loguru_logger
    except ImportError:
        return

    if _loguru_our_sink_id is not None:
        return  # already installed

    # 1) Remove every existing sink (default + flowllm's)
    loguru_logger.remove()

    # 2) Add our own sink
    def _sink(message: Any) -> None:
        record = message.record
        module = record.get("name", "")
        text = record.get("message", "").strip()
        if not text:
            return

        if not TRACE_CONFIG.get("FLOWLLM"):
            return

        # Classify by source module — order matters (specific before general)
        if "embedding" in module or "embedding" in text.lower():
            log.embedding(text)
        elif "pgvector" in module or "vector_store" in module:
            log.pgvector(text)
        elif "base_flow" in module or "timer" in module or "flow" in text[:30]:
            log.reme(f"[flow] {text}")
        elif "_op" in module:
            log.reme(f"[op] {text}")
        elif "config" in module or "parser" in module:
            log.reme(f"[config] {text}")
        elif "openai_compatible_llm" in module:
            log.llm_api(f"[internal] {text}")
        else:
            log.reme(text)

    _loguru_our_sink_id = loguru_logger.add(_sink, level="INFO")

    # 3) Monkey-patch logger.add AND logger.remove so future calls
    #    (by flowllm/ReMeApp init_logger) are no-ops.
    #    Without patching remove(), flowllm's init_logger() would
    #    remove our sink, then its add() (also no-op) leaves nothing.
    import types
    _fake_id_counter = [1000]

    loguru_logger.add = types.MethodType(
        lambda self, *a, **kw: (_fake_id_counter.__setitem__(0, _fake_id_counter[0] + 1) or _fake_id_counter[0]),
        loguru_logger,
    )
    loguru_logger.remove = types.MethodType(
        lambda self, *a, **kw: None,
        loguru_logger,
    )

    log.framework("flowllm/ReMe log tracing installed")


def install_uvicorn_filter() -> None:
    """Control Uvicorn's INFO request logs via TRACE_CONFIG['UVICORN']."""
    import logging

    class _UvicornFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return TRACE_CONFIG.get("UVICORN", True)

    for name in ("uvicorn.access", "uvicorn"):
        uv_logger = logging.getLogger(name)
        uv_logger.addFilter(_UvicornFilter())


def install_agentscope_filter() -> None:
    """Control AgentScope's INFO logs via TRACE_CONFIG['AGENTSCOPE']."""
    import logging

    class _ASFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return TRACE_CONFIG.get("AGENTSCOPE", True)

    for name in ("agentscope",):
        as_logger = logging.getLogger(name)
        as_logger.addFilter(_ASFilter())
