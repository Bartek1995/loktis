"""
Tests for the structured diagnostics module.
"""
import logging
import re
import unittest
from unittest.mock import patch

from location_analysis.diagnostics import (
    AnalysisSummary,
    AnalysisTraceContext,
    ProviderStats,
    StructuredLogger,
    generate_trace_id,
    get_diag_logger,
    _sanitize_meta,
)


class TestGenerateTraceId(unittest.TestCase):
    """Test generate_trace_id() produces unique 10-char IDs."""

    def test_default_length(self):
        tid = generate_trace_id()
        self.assertEqual(len(tid), 10)

    def test_custom_length(self):
        tid = generate_trace_id(20)
        self.assertEqual(len(tid), 20)

    def test_only_alphanumeric(self):
        tid = generate_trace_id()
        self.assertTrue(tid.isalnum())
        self.assertEqual(tid, tid.lower(), "Trace ID should be lowercase")

    def test_unique(self):
        ids = {generate_trace_id() for _ in range(200)}
        self.assertEqual(len(ids), 200, "Trace IDs should be unique")


class TestStructuredLoggerFormat(unittest.TestCase):
    """Test StructuredLogger emits correct key=value format."""

    def setUp(self):
        self.ctx = AnalysisTraceContext(trace_id="test123abc")
        self.slog = StructuredLogger("test.logger", self.ctx)

    def test_info_emits_kv_line(self):
        with self.assertLogs("test.logger", level="INFO") as cm:
            self.slog.info(stage="geo", op="fetch", status="ok", message="hello")

        self.assertEqual(len(cm.output), 1)
        line = cm.output[0]
        # Should contain key=value pairs
        self.assertIn('trace_id="test123abc"', line)
        self.assertIn('stage="geo"', line)
        self.assertIn('op="fetch"', line)
        self.assertIn('status="ok"', line)
        self.assertIn('msg="hello"', line)
        self.assertIn("level=", line)
        self.assertIn("ts=", line)

    def test_warning_emits_level(self):
        with self.assertLogs("test.logger", level="WARNING") as cm:
            self.slog.warning(stage="filter", op="check", message="low coverage")

        line = cm.output[0]
        self.assertIn('level="WARNING"', line)

    def test_debug_emits_at_debug_level(self):
        with self.assertLogs("test.logger", level="DEBUG") as cm:
            self.slog.debug(stage="scoring", op="calc", meta={"x": 42})

        line = cm.output[0]
        self.assertIn('level="DEBUG"', line)
        self.assertIn('"x":42', line)

    def test_error_with_exc_and_hint(self):
        with self.assertLogs("test.logger", level="ERROR") as cm:
            self.slog.error(
                stage="pipeline",
                op="crash",
                message="boom",
                exc="RuntimeError",
                hint="Check logs",
            )

        line = cm.output[0]
        self.assertIn('exc="RuntimeError"', line)
        self.assertIn('hint="Check logs"', line)

    def test_meta_is_sanitized(self):
        with self.assertLogs("test.logger", level="INFO") as cm:
            self.slog.info(stage="test", meta={"api_key": "SECRET", "count": 5})

        line = cm.output[0]
        # api_key should be filtered out
        self.assertNotIn("SECRET", line)
        # count should be present
        self.assertIn('"count":5', line)


class TestDevModeErrorFormatting(unittest.TestCase):
    """Test dev-mode error formatting with !!! prefix."""

    def test_error_has_prefix_in_debug_mode(self):
        ctx = AnalysisTraceContext(trace_id="devtest001")
        slog = StructuredLogger("test.dev", ctx)

        with patch("location_analysis.diagnostics._is_debug_mode", return_value=True):
            with self.assertLogs("test.dev", level="ERROR") as cm:
                slog.error(stage="test", op="fail", message="boom")

        line = cm.output[0]
        # The raw message (after log prefix) should start with !!!
        # assertLogs captures "ERROR:test.dev:!!! ts=..."
        self.assertIn("!!!", line)

    def test_error_no_prefix_in_prod_mode(self):
        ctx = AnalysisTraceContext(trace_id="prodtest01")
        slog = StructuredLogger("test.prod", ctx)

        with patch("location_analysis.diagnostics._is_debug_mode", return_value=False):
            with self.assertLogs("test.prod", level="ERROR") as cm:
                slog.error(stage="test", op="fail", message="boom")

        line = cm.output[0]
        # The raw message should NOT have !!! prefix
        # Extract the actual logged message part (after "ERROR:test.prod:")
        msg_part = line.split(":", 2)[-1] if ":" in line else line
        self.assertFalse(msg_part.lstrip().startswith("!!!"))


class TestAnalysisSummary(unittest.TestCase):
    """Test AnalysisSummary accumulates stats and emits summary."""

    def test_record_request(self):
        summary = AnalysisSummary()
        summary.record_request("overpass", "ok", 150.0)
        summary.record_request("overpass", "ok", 200.0)
        summary.record_request("overpass", "error", 50.0)

        stats = summary.providers["overpass"]
        self.assertEqual(stats.requests, 3)
        self.assertEqual(stats.errors, 1)
        self.assertAlmostEqual(stats.max_ms, 200.0)

    def test_record_stage(self):
        summary = AnalysisSummary()
        summary.record_stage("geo", 300.5)
        summary.record_stage("scoring", 50.2)

        self.assertAlmostEqual(summary.stage_durations_ms["geo"], 300.5)
        self.assertAlmostEqual(summary.stage_durations_ms["scoring"], 50.2)

    def test_to_meta(self):
        summary = AnalysisSummary()
        summary.record_request("google", "ok", 100.0)
        summary.record_request("google", "timeout", 5000.0)
        summary.record_stage("geo", 600.0)

        meta = summary.to_meta()
        self.assertEqual(meta["provider_google_requests"], 2)
        self.assertEqual(meta["provider_google_timeouts"], 1)
        self.assertAlmostEqual(meta["provider_google_max_ms"], 5000.0)
        self.assertAlmostEqual(meta["stage_geo_ms"], 600.0)

    def test_emit_summary_log(self):
        ctx = AnalysisTraceContext(trace_id="sumtest001")
        slog = StructuredLogger("test.summary", ctx)
        summary = ctx.summary
        summary.record_request("overpass", "ok", 100.0)
        summary.record_stage("geo", 500.0)

        with self.assertLogs("test.summary", level="INFO") as cm:
            summary.emit(slog, ctx, status="ok")

        line = cm.output[0]
        self.assertIn('stage="summary"', line)
        self.assertIn('op="analysis_complete"', line)
        self.assertIn("total_duration_ms", line)


class TestCheckpointWarning(unittest.TestCase):
    """Test checkpoint WARNING when all items filtered out."""

    def test_checkpoint_warns_when_all_removed(self):
        ctx = AnalysisTraceContext(trace_id="chktest001")
        slog = StructuredLogger("test.checkpoint", ctx)

        with self.assertLogs("test.checkpoint", level="WARNING") as cm:
            slog.checkpoint(
                stage="filter",
                category="food",
                count_raw=10,
                count_kept=0,
            )

        line = cm.output[0]
        self.assertIn('level="WARNING"', line)
        self.assertIn("filters removed all food", line)

    def test_checkpoint_info_when_some_kept(self):
        ctx = AnalysisTraceContext(trace_id="chktest002")
        slog = StructuredLogger("test.checkpoint", ctx)

        with self.assertLogs("test.checkpoint", level="INFO") as cm:
            slog.checkpoint(
                stage="filter",
                category="shops",
                count_raw=20,
                count_kept=15,
            )

        line = cm.output[0]
        self.assertIn('level="INFO"', line)


class TestTraceContext(unittest.TestCase):
    """Test AnalysisTraceContext stage and request tracking."""

    def test_stage_timing(self):
        ctx = AnalysisTraceContext()
        ctx.start_stage("geo")
        # Simulate enough work so rounding doesn't zero it out
        import time
        time.sleep(0.05)
        duration = ctx.end_stage("geo")
        self.assertGreater(duration, 0)
        self.assertIn("geo", ctx.summary.stage_durations_ms)

    def test_request_token_tracking(self):
        ctx = AnalysisTraceContext()
        token = ctx.start_request("overpass", "batch_query", "geo")
        self.assertIsInstance(token, str)
        import time
        time.sleep(0.05)
        duration = ctx.end_request(token)
        self.assertGreater(duration, 0)

    def test_total_duration(self):
        ctx = AnalysisTraceContext()
        import time
        time.sleep(0.05)
        self.assertGreater(ctx.total_duration_ms, 0)


class TestSecretFiltering(unittest.TestCase):
    """Test that secret keys are never logged."""

    def test_api_key_filtered(self):
        result = _sanitize_meta({"api_key": "sk-123456", "count": 5})
        self.assertNotIn("api_key", result)
        self.assertEqual(result["count"], 5)

    def test_token_filtered(self):
        result = _sanitize_meta({"auth_token": "abc", "status": "ok"})
        self.assertNotIn("auth_token", result)
        self.assertEqual(result["status"], "ok")

    def test_password_filtered(self):
        result = _sanitize_meta({"password": "secret", "name": "test"})
        self.assertNotIn("password", result)

    def test_nested_secrets_filtered(self):
        result = _sanitize_meta({"config": {"api_key": "secret", "timeout": 30}})
        self.assertNotIn("api_key", result.get("config", {}))
        self.assertEqual(result["config"]["timeout"], 30)


class TestDegradedLogging(unittest.TestCase):
    """Test degraded() method for DEGRADED_PROVIDER / FALLBACK_USED warnings."""

    def test_degraded_emits_warning(self):
        ctx = AnalysisTraceContext(trace_id="degtest001")
        slog = StructuredLogger("test.degraded", ctx)

        with self.assertLogs("test.degraded", level="WARNING") as cm:
            slog.degraded(
                kind="FALLBACK_USED",
                provider="google",
                reason="Overpass timed out",
                stage="geo",
            )

        line = cm.output[0]
        self.assertIn('op="FALLBACK_USED"', line)
        self.assertIn('provider="google"', line)
        self.assertIn('status="degraded"', line)


class TestReqStartEnd(unittest.TestCase):
    """Test req_start/req_end for external API request tracking."""

    def test_req_start_end_records_stats(self):
        ctx = AnalysisTraceContext(trace_id="reqtest001")
        slog = StructuredLogger("test.req", ctx)

        with self.assertLogs("test.req", level="DEBUG"):
            token = slog.req_start(provider="overpass", op="query", stage="geo")

        with self.assertLogs("test.req", level="INFO"):
            slog.req_end(
                provider="overpass",
                op="query",
                stage="geo",
                status="ok",
                request_token=token,
                http_status=200,
            )

        stats = ctx.summary.providers.get("overpass")
        self.assertIsNotNone(stats)
        self.assertEqual(stats.requests, 1)

    def test_req_end_error_records_error(self):
        ctx = AnalysisTraceContext(trace_id="reqtest002")
        slog = StructuredLogger("test.req_err", ctx)

        with self.assertLogs("test.req_err", level="DEBUG"):
            token = slog.req_start(provider="google", op="search", stage="geo")

        with self.assertLogs("test.req_err", level="ERROR"):
            slog.req_end(
                provider="google",
                op="search",
                stage="geo",
                status="error",
                request_token=token,
                http_status=500,
                error_class="http",
                message="Server error",
            )

        stats = ctx.summary.providers["google"]
        self.assertEqual(stats.errors, 1)


if __name__ == "__main__":
    unittest.main()
