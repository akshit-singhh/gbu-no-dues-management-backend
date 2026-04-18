# app/core/datadog.py

import os
import sys
from typing import Any

from loguru import logger

_TRUTHY_VALUES = {"1", "true", "yes", "on"}

# Module-level flag — prevents spamming stderr on every log record
# if bind_trace_context hits a persistent error.
_TRACER_WARN_ISSUED = False


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY_VALUES


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def bootstrap_datadog() -> bool:
    """
    Enable Datadog auto-instrumentation when explicitly requested via env.

    Call this as early as possible in main.py — before importing FastAPI or
    any instrumented library — so ddtrace can patch them at import time.

    Returns True if tracing was successfully enabled, False otherwise.
    """
    if not _is_truthy(os.getenv("DD_TRACE_ENABLED", "false")):
        return False

    env_name = (os.getenv("DD_ENV") or os.getenv("ENV") or "production").lower()

    os.environ.setdefault("DD_SERVICE", "gbu-no-dues-backend")
    os.environ.setdefault("DD_ENV", env_name)

    # In production, DD_AGENT_HOST is expected to be set externally
    # (e.g. via Vercel env vars or the host's own DD_AGENT_HOST default).
    # We only set a localhost default for local development.
    if env_name == "development":
        os.environ.setdefault("DD_AGENT_HOST", "127.0.0.1")

    os.environ.setdefault("DD_TRACE_AGENT_PORT", "8126")
    os.environ.setdefault("DD_LOGS_INJECTION", "true")
    os.environ.setdefault("DD_RUNTIME_METRICS_ENABLED", "true")
    os.environ.setdefault("DD_TRACE_128_BIT_TRACEID_GENERATION_ENABLED", "true")

    try:
        import ddtrace.auto  # noqa: F401
    except Exception as exc:
        # Use sys.stderr directly — loguru may not be configured yet at
        # bootstrap time, and this failure must always surface.
        print(
            f"[APM] Datadog tracing requested but failed to initialize: {exc}",
            file=sys.stderr,
        )
        return False

    # By this point loguru should be configured — safe to use logger.
    # Fall back to stderr if not.
    try:
        logger.info("[APM] Datadog tracing enabled | env={} service=gbu-no-dues-backend", env_name)
    except Exception:
        print("[APM] Datadog tracing is enabled.", file=sys.stderr)

    return True


# ---------------------------------------------------------------------------
# Log-trace correlation
# ---------------------------------------------------------------------------

def bind_trace_context(record: dict[str, Any]) -> None:
    """
    Attach Datadog trace/span IDs to every Loguru log record so that logs
    and traces can be correlated in the Datadog UI.

    Register this as a Loguru patcher:
        logger.configure(patcher=bind_trace_context)

    Defaults to "0" / "0" when no active span exists (e.g. background tasks,
    startup events) so the fields are always present in the log schema.
    """
    global _TRACER_WARN_ISSUED

    record["extra"].setdefault("dd_trace_id", "0")
    record["extra"].setdefault("dd_span_id", "0")

    try:
        from ddtrace import tracer
    except ImportError:
        # ddtrace not installed — silently skip, defaults already set above
        return

    try:
        span = tracer.current_span()
        if not span:
            return

        # span.context can be None for finished or non-sampled spans
        ctx = getattr(span, "context", None)
        trace_id = str(getattr(ctx, "trace_id", 0) or 0) if ctx else "0"
        span_id = str(getattr(span, "span_id", 0) or 0)

        record["extra"]["dd_trace_id"] = trace_id
        record["extra"]["dd_span_id"] = span_id

    except Exception as exc:
        # Emit the warning once to stderr (safe even before loguru is ready)
        # then go silent — this runs on every log call and must never raise.
        if not _TRACER_WARN_ISSUED:
            _TRACER_WARN_ISSUED = True
            print(
                f"[APM] bind_trace_context failed, trace correlation disabled: {exc}",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# Span tagging
# ---------------------------------------------------------------------------

def tag_active_span(**tags: Any) -> None:
    """
    Attach request metadata to the currently active Datadog span.

    Failures on individual tags are logged as warnings and do not abort
    remaining tags — a bad value for one key won't suppress the others.

    Usage:
        tag_active_span(user_id=str(user.id), endpoint="/api/admin/login")
    """
    try:
        from ddtrace import tracer
    except ImportError:
        return

    try:
        span = tracer.current_span()
    except Exception as exc:
        logger.warning("[APM] Could not retrieve active span: {}", exc)
        return

    if not span:
        return

    for key, value in tags.items():
        if value is None:
            continue
        try:
            span.set_tag(key, value)
        except Exception as exc:
            # Log per-tag failure without aborting remaining tags
            logger.warning("[APM] Failed to set span tag '{}': {}", key, exc)


def _normalize_resource_path(path: str) -> str:
    """
    Normalize malformed duplicated paths seen behind some proxy setups.

    Example:
        /api/x/api/x -> /api/x
    """
    if not path:
        return "/"

    if not path.startswith("/"):
        path = f"/{path}"

    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and len(parts) % 2 == 0:
        half = len(parts) // 2
        if parts[:half] == parts[half:]:
            return "/" + "/".join(parts[:half])

    return path


def set_active_span_resource(method: str, path: str) -> None:
    """
    Force a canonical Datadog request resource name (METHOD /path).
    """
    try:
        from ddtrace import tracer
    except ImportError:
        return

    try:
        # Prefer request/root span so resource naming affects top-level APM rows.
        span = tracer.current_root_span() or tracer.current_span()
    except Exception as exc:
        logger.warning("[APM] Could not retrieve active span for resource set: {}", exc)
        return

    if not span:
        return

    normalized_path = _normalize_resource_path(path)
    try:
        span.resource = f"{method.upper()} {normalized_path}"
        # Keep a custom tag for debugging original raw path if needed.
        span.set_tag("app.request.path_normalized", normalized_path)
    except Exception as exc:
        logger.warning("[APM] Failed to set span resource: {}", exc)


def set_active_span_resource_for_request(method: str, raw_path: str, route_path: str | None = None) -> None:
    """
    Prefer route template when available (e.g. /api/users/{id}) and fall back
    to raw path. This keeps Datadog resources stable and concise.
    """
    preferred_path = route_path or raw_path
    normalized_preferred_path = _normalize_resource_path(preferred_path)

    set_active_span_resource(method, normalized_preferred_path)

    try:
        from ddtrace import tracer
    except ImportError:
        return

    try:
        span = tracer.current_root_span() or tracer.current_span()
    except Exception:
        return

    if not span:
        return

    try:
        if route_path:
            span.set_tag("http.route", normalized_preferred_path)
        span.set_tag("app.request.path_raw", _normalize_resource_path(raw_path))
    except Exception as exc:
        logger.warning("[APM] Failed to set request route tags: {}", exc)