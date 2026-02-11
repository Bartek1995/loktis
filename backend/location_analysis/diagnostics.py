"""Structured diagnostics for the location-analysis pipeline."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import string
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, Optional

TRACE_ID_LENGTH = 10
_TRACE_ALPHABET = string.ascii_lowercase + string.digits
_MAX_META_VALUE_LEN = 300
_META_JSON_SEPARATORS = (",", ":")
_SAFE_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
_SECRET_KEY_RE = re.compile(
    r"(api[-_]?key|token|secret|password|authorization|cookie|credential|private[-_]?key)",
    re.IGNORECASE,
)


def generate_trace_id(length: int = TRACE_ID_LENGTH) -> str:
    """Generate a short alphanumeric trace id."""
    return "".join(secrets.choice(_TRACE_ALPHABET) for _ in range(length))


def _is_debug_mode() -> bool:
    """Detect debug mode from env or Django settings."""
    env = os.getenv("DEBUG")
    if env is not None:
        return env.strip().lower() in {"1", "true", "yes", "on"}
    try:
        from django.conf import settings

        return bool(getattr(settings, "DEBUG", False))
    except Exception:
        return False


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _sanitize_key(key: str) -> str:
    if _SAFE_KEY_PATTERN.match(key):
        return key
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", key).strip("_") or "meta"


def _sanitize_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    text = str(value).replace("\n", "\\n")
    if len(text) > _MAX_META_VALUE_LEN:
        return f"{text[:_MAX_META_VALUE_LEN]}..."
    return text


def _sanitize_meta(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    safe: Dict[str, Any] = {}
    for key, value in meta.items():
        key_str = _sanitize_key(str(key))
        if _SECRET_KEY_RE.search(key_str):
            continue
        if isinstance(value, dict):
            nested = _sanitize_meta(value)
            if nested:
                safe[key_str] = nested
            continue
        if isinstance(value, (list, tuple, set)):
            safe[key_str] = [_sanitize_scalar(v) for v in list(value)[:50]]
            continue
        safe[key_str] = _sanitize_scalar(value)
    return safe


def _to_kv(key: str, value: Any) -> str:
    if isinstance(value, str):
        return f"{key}={json.dumps(value, ensure_ascii=True)}"
    return f"{key}={json.dumps(value, ensure_ascii=True, separators=_META_JSON_SEPARATORS)}"


def _provider_metric_name(provider: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", provider).strip("_").lower() or "unknown"


@dataclass
class ProviderStats:
    requests: int = 0
    errors: int = 0
    timeouts: int = 0
    rate_limited: int = 0
    max_ms: float = 0.0

    def record(self, status: str, duration_ms: float) -> None:
        self.requests += 1
        self.max_ms = max(self.max_ms, max(0.0, duration_ms))
        if status == "error":
            self.errors += 1
        elif status == "timeout":
            self.timeouts += 1
        elif status == "rate_limited":
            self.rate_limited += 1


@dataclass
class AnalysisSummary:
    """Accumulates request and stage stats, then emits one final log."""

    providers: Dict[str, ProviderStats] = field(default_factory=dict)
    stage_durations_ms: Dict[str, float] = field(default_factory=dict)

    def record_request(self, provider: str, status: str, duration_ms: float = 0.0) -> None:
        stats = self.providers.setdefault(provider or "unknown", ProviderStats())
        stats.record(status=status, duration_ms=duration_ms)

    def record_stage(self, stage: str, duration_ms: float) -> None:
        if not stage:
            return
        self.stage_durations_ms[stage] = round(max(0.0, duration_ms), 1)

    def to_meta(self) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        for provider, stats in self.providers.items():
            metric = _provider_metric_name(provider)
            meta[f"provider_{metric}_requests"] = stats.requests
            meta[f"provider_{metric}_errors"] = stats.errors
            meta[f"provider_{metric}_timeouts"] = stats.timeouts
            meta[f"provider_{metric}_rate_limited"] = stats.rate_limited
            meta[f"provider_{metric}_max_ms"] = round(stats.max_ms, 1)
        for stage, duration in self.stage_durations_ms.items():
            meta[f"stage_{_provider_metric_name(stage)}_ms"] = round(duration, 1)
        return meta

    def emit(
        self,
        logger: "StructuredLogger",
        context: "AnalysisTraceContext",
        *,
        status: str = "ok",
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        merged = self.to_meta()
        if extra_meta:
            merged.update(_sanitize_meta(extra_meta))
        merged["total_duration_ms"] = context.total_duration_ms
        logger.info(
            stage="summary",
            op="analysis_complete",
            status=status,
            duration_ms=context.total_duration_ms,
            meta=merged,
        )


@dataclass
class AnalysisTraceContext:
    """Per-analysis trace context shared across modules."""

    trace_id: str = field(default_factory=generate_trace_id)
    analysis_id: Optional[str] = None
    started_monotonic: float = field(default_factory=time.monotonic)
    summary: AnalysisSummary = field(default_factory=AnalysisSummary)
    _stage_starts: Dict[str, float] = field(default_factory=dict, repr=False)
    _request_starts: Dict[str, float] = field(default_factory=dict, repr=False)
    _request_counter: int = field(default=0, repr=False)

    @property
    def total_duration_ms(self) -> float:
        return round((time.monotonic() - self.started_monotonic) * 1000, 1)

    def start_stage(self, stage: str) -> None:
        if stage:
            self._stage_starts[stage] = time.monotonic()

    def end_stage(self, stage: str) -> float:
        start = self._stage_starts.pop(stage, None)
        if start is None:
            return 0.0
        duration_ms = (time.monotonic() - start) * 1000
        self.summary.record_stage(stage, duration_ms)
        return round(duration_ms, 1)

    def start_request(self, provider: str, op: str, stage: str = "") -> str:
        self._request_counter += 1
        token = f"{provider}:{op}:{stage}:{self._request_counter}"
        self._request_starts[token] = time.monotonic()
        return token

    def end_request(self, token: Optional[str]) -> float:
        if not token:
            return 0.0
        start = self._request_starts.pop(token, None)
        if start is None:
            return 0.0
        return round((time.monotonic() - start) * 1000, 1)


class StructuredLogger:
    """Single-line key=value logger with trace metadata."""

    def __init__(self, name: str, ctx: Optional[AnalysisTraceContext] = None):
        self._logger = logging.getLogger(name)
        self.ctx = ctx or AnalysisTraceContext()

    def _emit(
        self,
        level: str,
        *,
        stage: str = "",
        provider: str = "",
        op: str = "",
        status: str = "",
        duration_ms: Optional[float] = None,
        message: str = "",
        error_class: str = "",
        http_status: Optional[int] = None,
        provider_code: str = "",
        exc: str = "",
        hint: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        fields: Dict[str, Any] = {
            "ts": _now_iso(),
            "level": level,
            "trace_id": self.ctx.trace_id,
        }
        if self.ctx.analysis_id:
            fields["analysis_id"] = self.ctx.analysis_id
        if stage:
            fields["stage"] = stage
        if provider:
            fields["provider"] = provider
        if op:
            fields["op"] = op
        if status:
            fields["status"] = status
        if duration_ms is not None:
            fields["duration_ms"] = round(max(0.0, float(duration_ms)), 1)
        if http_status is not None:
            fields["http_status"] = int(http_status)
        if provider_code:
            fields["provider_code"] = provider_code
        if error_class:
            fields["error_class"] = error_class
        if message:
            fields["msg"] = message
        if exc:
            fields["exc"] = exc
        if hint:
            fields["hint"] = hint

        safe_meta = _sanitize_meta(meta)
        if safe_meta:
            fields["meta"] = safe_meta

        line = " ".join(_to_kv(k, v) for k, v in fields.items())
        if level == "ERROR" and _is_debug_mode():
            line = f"!!! {line}"

        self._logger.log(getattr(logging, level, logging.INFO), line)

    def info(
        self,
        *,
        stage: str = "",
        provider: str = "",
        op: str = "",
        status: str = "ok",
        duration_ms: Optional[float] = None,
        message: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._emit(
            "INFO",
            stage=stage,
            provider=provider,
            op=op,
            status=status,
            duration_ms=duration_ms,
            message=message,
            meta=meta,
        )

    def warning(
        self,
        *,
        stage: str = "",
        provider: str = "",
        op: str = "",
        status: str = "warn",
        duration_ms: Optional[float] = None,
        message: str = "",
        error_class: str = "",
        http_status: Optional[int] = None,
        provider_code: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._emit(
            "WARNING",
            stage=stage,
            provider=provider,
            op=op,
            status=status,
            duration_ms=duration_ms,
            message=message,
            error_class=error_class,
            http_status=http_status,
            provider_code=provider_code,
            meta=meta,
        )

    def error(
        self,
        *,
        stage: str = "",
        provider: str = "",
        op: str = "",
        status: str = "error",
        duration_ms: Optional[float] = None,
        message: str = "",
        error_class: str = "",
        http_status: Optional[int] = None,
        provider_code: str = "",
        exc: str = "",
        hint: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._emit(
            "ERROR",
            stage=stage,
            provider=provider,
            op=op,
            status=status,
            duration_ms=duration_ms,
            message=message,
            error_class=error_class,
            http_status=http_status,
            provider_code=provider_code,
            exc=exc,
            hint=hint,
            meta=meta,
        )

    def debug(
        self,
        *,
        stage: str = "",
        provider: str = "",
        op: str = "",
        status: str = "",
        duration_ms: Optional[float] = None,
        message: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._emit(
            "DEBUG",
            stage=stage,
            provider=provider,
            op=op,
            status=status,
            duration_ms=duration_ms,
            message=message,
            meta=meta,
        )

    def req_start(
        self,
        *,
        provider: str,
        op: str,
        stage: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        token = self.ctx.start_request(provider=provider, op=op, stage=stage)
        self.debug(stage=stage, provider=provider, op=op, status="start", meta=meta)
        return token

    def req_end(
        self,
        *,
        provider: str,
        op: str,
        stage: str = "",
        status: str = "ok",
        request_token: Optional[str] = None,
        duration_ms: Optional[float] = None,
        http_status: Optional[int] = None,
        provider_code: str = "",
        retry_count: Optional[int] = None,
        error_class: str = "",
        message: str = "",
        exc: str = "",
        hint: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        duration = duration_ms
        if duration is None:
            duration = self.ctx.end_request(request_token)
        duration = round(max(0.0, float(duration or 0.0)), 1)
        self.ctx.summary.record_request(provider, status, duration)

        request_meta = dict(meta or {})
        if retry_count is not None:
            request_meta["retry_count"] = retry_count

        if status in {"error", "timeout"}:
            self.error(
                stage=stage,
                provider=provider,
                op=op,
                status=status,
                duration_ms=duration,
                http_status=http_status,
                provider_code=provider_code,
                error_class=error_class,
                message=message,
                exc=exc,
                hint=hint,
                meta=request_meta,
            )
        elif status in {"retry", "rate_limited", "degraded"}:
            self.warning(
                stage=stage,
                provider=provider,
                op=op,
                status=status,
                duration_ms=duration,
                http_status=http_status,
                provider_code=provider_code,
                error_class=error_class,
                message=message,
                meta=request_meta,
            )
        else:
            self.info(
                stage=stage,
                provider=provider,
                op=op,
                status=status,
                duration_ms=duration,
                message=message,
                meta=request_meta,
            )

    def checkpoint(
        self,
        *,
        stage: str,
        category: str,
        count_raw: int = 0,
        count_kept: int = 0,
        count_render: Optional[int] = None,
        provider: str = "",
        op: str = "checkpoint",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = dict(meta or {})
        payload["category"] = category
        payload["count_raw"] = count_raw
        payload["count_kept"] = count_kept
        if count_render is not None:
            payload["count_render"] = count_render

        if count_raw > 0 and count_kept == 0:
            self.warning(
                stage=stage,
                provider=provider,
                op=op,
                status="empty",
                message=f"filters removed all {category}",
                error_class="logic",
                meta=payload,
            )
        else:
            self.info(stage=stage, provider=provider, op=op, status="ok", meta=payload)

    def degraded(
        self,
        *,
        kind: str,
        provider: str,
        reason: str,
        stage: str = "",
        impact: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = dict(meta or {})
        if impact:
            payload["impact"] = impact
        self.warning(
            stage=stage,
            provider=provider,
            op=kind,
            status="degraded",
            message=reason,
            meta=payload,
        )


def get_diag_logger(name: str, ctx: Optional[AnalysisTraceContext] = None) -> StructuredLogger:
    return StructuredLogger(name=name, ctx=ctx)
