"""Tests for OpenMinion 0.1 BuildingBlockProbeRunner, doc scrubbing, and CLI probe."""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from cortensor_verifier.cli import main
from cortensor_verifier.models import ProbeCheckResult
from cortensor_verifier.probe import (
    EXPECTED_PROBE_IDS,
    BuildingBlockProbeRunner,
    ProbeSuiteReport,
    assert_no_plaintext_secrets,
    build_empirical_dx_findings,
    export_probe_docs,
)
from tests.conftest import (
    LoopbackLLMServer,
    RecordedRequest,
    _maybe_internal_classifier_step,
    _render_step_response,
    error_step,
    json_step,
    text_step,
    tool_calls_step,
)


def _extract_closure_action_summary(messages: list[Any]) -> str:
    """Recover action_summary / closure_action_summary from ClosureJudgment prompts."""
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        content = str(msg.get("content", "") or "")
        match = re.search(r'"closure_action_summary"\s*:\s*"((?:\\.|[^"\\])*)"', content)
        if match:
            try:
                decoded = json.loads(f'"{match.group(1)}"')
                if isinstance(decoded, str) and decoded.strip():
                    return decoded.strip()
            except json.JSONDecodeError:
                pass
        ctx_match = re.search(
            r"(?ms)^action_summary:\s*(.+?)(?=\nclosure_action_outputs:|\nclosure_intent_outcomes:|\n\[|\Z)",
            content,
        )
        if ctx_match:
            extracted = ctx_match.group(1).strip()
            if extracted:
                return extracted
    return "Tool execution completed cleanly."


def _probe_internal_classifier_step(request_body: dict[str, Any]) -> dict[str, Any] | None:
    """Handle FreshnessContract, FinalizationStatus, AND ClosureJudgment classifiers."""
    base_step = _maybe_internal_classifier_step(request_body)
    if base_step is not None:
        return base_step

    tool_choice = request_body.get("tool_choice")
    if not isinstance(tool_choice, dict):
        return None
    fn = tool_choice.get("function")
    if not isinstance(fn, dict) or fn.get("name") != "submit_output":
        return None

    tools = request_body.get("tools") or []
    schema_title = ""
    if tools and isinstance(tools[0], dict):
        schema_title = str(
            tools[0].get("function", {}).get("parameters", {}).get("title", "")
        )
    if schema_title == "ClosureJudgment":
        summary = _extract_closure_action_summary(request_body.get("messages", []))
        return {
            "type": "tool_calls",
            "calls": [
                {
                    "id": "call_closure_1",
                    "name": "submit_output",
                    "arguments": {
                        "satisfied": True,
                        "reason": "Tool execution completed cleanly.",
                        "next_action": "close",
                        "final_answer": summary,
                    },
                }
            ],
        }
    return None


def _smart_probe_step(request_body: dict[str, Any]) -> dict[str, Any]:
    """Deterministically act as an OpenAI-compatible model for the 10 probe scenarios."""
    messages = [m for m in request_body.get("messages", []) if isinstance(m, dict)]
    user_messages = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
    last_user = user_messages[-1] if user_messages else ""
    tool_msgs = [m for m in messages if m.get("role") == "tool"]

    tools = request_body.get("tools") or []
    available_tools = {
        str(t.get("function", {}).get("name", ""))
        for t in tools
        if isinstance(t, dict) and isinstance(t.get("function"), dict)
    }

    if "PROBE_STRUCTURED_NEGATIVE" in last_user:
        return text_step("MALFORMED_NON_JSON_PROBE")

    if "PROBE_STRUCTURED" in last_user:
        return json_step(
            {
                "status": "OK",
                "block": "structured_pydantic_output",
                "score": 0.99,
            }
        )

    if "PROBE_SUBAGENT" in last_user:
        if not tool_msgs and "probe_subagent_tool" in available_tools:
            return tool_calls_step(
                {
                    "id": "call_subagent_tool_1",
                    "name": "probe_subagent_tool",
                    "arguments": {"item": "subagent-check"},
                }
            )
        return json_step(
            {
                "status": "OK",
                "block": "subagent_delegation",
                "score": 0.97,
            }
        )

    if "PROBE_TOOLS_FORCED" in last_user:
        if not tool_msgs and "probe_echo_tag" in available_tools:
            return tool_calls_step(
                {
                    "id": "call_forced_echo_1",
                    "name": "probe_echo_tag",
                    "arguments": {"tag": "forced-c3"},
                }
            )
        content = str(tool_msgs[-1].get("content", "")) if tool_msgs else "missing"
        return text_step(f"FORCED_TOOL_OK: {content}")

    if "PROBE_TOOLS_AUTO" in last_user:
        if not tool_msgs and "probe_lookup_fact" in available_tools:
            return tool_calls_step(
                {
                    "id": "call_auto_lookup_1",
                    "name": "probe_lookup_fact",
                    "arguments": {"topic": "cortensor-poi"},
                }
            )
        content = str(tool_msgs[-1].get("content", "")) if tool_msgs else "missing"
        return text_step(f"AUTO_TOOL_OK: {content}")

    if "PROBE_POLICY_ALLOW" in last_user or "PROBE_POLICY_DENY" in last_user:
        att_id = "att-allow" if "PROBE_POLICY_ALLOW" in last_user else "att-deny"
        if not tool_msgs and "probe_publish_attestation" in available_tools:
            return tool_calls_step(
                {
                    "id": "call_policy_gate_1",
                    "name": "probe_publish_attestation",
                    "arguments": {"attestation_id": att_id},
                }
            )
        content = str(tool_msgs[-1].get("content", "")) if tool_msgs else "no_tool_result"
        return text_step(f"POLICY_GATE_OBSERVED: {content}")

    if "PROBE_SESSION_STORE" in last_user:
        return text_step("Session marker SESSION_TOKEN_ALPHA_42 stored.")

    if "PROBE_SESSION_RECALL" in last_user:
        prior_text = "\n".join(
            str(m.get("content", ""))
            for m in messages[:-1]
            if m.get("role") in {"user", "assistant"}
        )
        if "SESSION_TOKEN_ALPHA_42" in prior_text:
            return text_step("RECALLED: SESSION_TOKEN_ALPHA_42")
        return text_step("RECALLED: NONE")

    if "PROBE_HANDOFF" in last_user:
        if "transfer_to_specialist" in available_tools and not tool_msgs:
            return tool_calls_step(
                {
                    "id": "call_handoff_specialist_1",
                    "name": "transfer_to_specialist",
                    "arguments": {"message": "Verify handoff claim payload."},
                }
            )
        if "transfer_to_specialist" in available_tools and tool_msgs:
            return text_step(f"HANDOFF_COMPLETE: {tool_msgs[-1].get('content', '')}")
        return text_step("SPECIALIST_ACK: Handoff task verified.")

    if "Verify handoff claim payload" in last_user:
        return text_step("SPECIALIST_ACK: Handoff task verified.")

    if "PROBE_STREAM_TURN" in last_user:
        return text_step("STREAM_TELEMETRY_OK: Turn completed cleanly.")

    if "PROBE_ISOLATION" in last_user:
        return text_step("ISOLATION_OK")

    return text_step("PROBE_STUB_OK")


def _render_sse_chunks(payload: dict[str, Any]) -> bytes:
    """Convert a standard OpenAI chat completion payload into SSE text/event-stream bytes."""
    model = str(payload.get("model") or "stub-model")
    comp_id = str(payload.get("id") or "chatcmpl-sse-stub")
    choices = payload.get("choices") or [{}]
    message = choices[0].get("message", {}) if choices else {}
    finish_reason = choices[0].get("finish_reason") or "stop"
    usage = payload.get("usage") or {
        "prompt_tokens": 12,
        "completion_tokens": 15,
        "total_tokens": 27,
    }

    events: list[dict[str, Any]] = []
    content = message.get("content")
    tool_calls = message.get("tool_calls")

    if content:
        midpoint = max(1, len(content) // 2)
        for part in (content[:midpoint], content[midpoint:]):
            if not part:
                continue
            events.append(
                {
                    "id": comp_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": part}, "finish_reason": None}],
                }
            )
    elif tool_calls:
        for idx, tc in enumerate(tool_calls):
            events.append(
                {
                    "id": comp_id,
                    "object": "chat.completion.chunk",
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": idx,
                                        "id": tc.get("id", f"call_{idx}"),
                                        "type": "function",
                                        "function": {
                                            "name": tc["function"]["name"],
                                            "arguments": tc["function"]["arguments"],
                                        },
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ],
                }
            )

    events.append(
        {
            "id": comp_id,
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
            "usage": usage,
        }
    )

    lines = [f"data: {json.dumps(evt)}\n\n" for evt in events]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


class ProbeLoopbackServer(LoopbackLLMServer):
    """SSE, delay, and ClosureJudgment-aware subclass of LoopbackLLMServer."""

    def __init__(self, *, smart_dispatch: bool = True) -> None:
        self.smart_dispatch = smart_dispatch
        super().__init__()

    def _resolve_probe_step(self, parsed: dict[str, Any]) -> dict[str, Any]:
        classifier_step = _probe_internal_classifier_step(parsed)
        if classifier_step is not None:
            return classifier_step
        with self._lock:
            if self._queue:
                return self._queue.pop(0)
            if self._default_step is not None:
                return self._default_step
        if self.smart_dispatch:
            return _smart_probe_step(parsed)
        return self._next_step()

    def _start_server(self) -> ThreadingHTTPServer:
        parent = self

        class _ProbeHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    parsed = {"_raw": raw.decode("utf-8", errors="replace")}

                headers_lower = {k.lower(): v for k, v in self.headers.items()}
                parent.requests.append(
                    RecordedRequest(
                        method="POST",
                        path=self.path,
                        headers=headers_lower,
                        body=parsed,
                    )
                )

                step = parent._resolve_probe_step(parsed)
                delay_s = float(step.get("delay_seconds", 0.0) or 0.0)
                if delay_s > 0.0:
                    time.sleep(delay_s)

                status, payload = _render_step_response(step, parsed)
                wants_stream = bool(parsed.get("stream")) and status < 400
                try:
                    if wants_stream:
                        encoded = _render_sse_chunks(payload)
                        self.send_response(status)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Content-Length", str(len(encoded)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(encoded)
                    else:
                        encoded = json.dumps(payload).encode("utf-8")
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(encoded)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    return

            def do_GET(self) -> None:  # noqa: N802
                if self.path.rstrip("/") == "/v1/models":
                    payload = {
                        "object": "list",
                        "data": [{"id": "stub-model", "object": "model"}],
                    }
                    encoded = json.dumps(payload).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()

        return ThreadingHTTPServer(("127.0.0.1", 0), _ProbeHandler)


@pytest.fixture()
def probe_server() -> ProbeLoopbackServer:
    server = ProbeLoopbackServer()
    try:
        yield server
    finally:
        server.close()


def test_probe_runner_executes_all_ten_building_blocks_against_real_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    probe_server: ProbeLoopbackServer,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-probe-secret-value-123456")
    runner = BuildingBlockProbeRunner(
        preset="openai-compatible",
        base_url=probe_server.base_url,
        model="stub-model",
        api_key_env="OPENAI_API_KEY",
        home_root=tmp_path / "probe-home",
        data_root=tmp_path / "probe-state",
    )
    report = runner.run_all()

    assert isinstance(report, ProbeSuiteReport)
    assert report.total_probes == 10
    assert report.passed_probes == 10
    assert report.failed_probes == 0
    assert report.all_passed is True
    assert [item.probe_id for item in report.probes] == list(EXPECTED_PROBE_IDS)

    for item in report.probes:
        assert isinstance(item, ProbeCheckResult)
        assert item.passed is True
        assert item.latency_ms is not None and item.latency_ms >= 0.0
        assert item.detail

    by_id = {item.probe_id: item for item in report.probes}
    assert by_id["structured_pydantic_output"].metadata["negative_validation_error"] is True
    assert by_id["policy_confirmation_gate"].metadata["allow_executed"] is True
    assert by_id["policy_confirmation_gate"].metadata["deny_blocked"] is True
    assert by_id["session_continuity"].metadata["same_session_recalled"] is True
    assert by_id["session_continuity"].metadata["second_session_isolated"] is True
    assert by_id["session_continuity"].metadata["thread_id"]
    assert by_id["memory_bundle_portability"].metadata["item_count"] == 1
    assert by_id["subagent_delegation"].metadata["parent_transcript_inherited"] is False
    assert by_id["agent_handoff"].metadata["tool_name"] == "transfer_to_specialist"
    assert by_id["submit_turn_streaming_telemetry"].metadata["chunk_count"] >= 2
    assert by_id["submit_turn_streaming_telemetry"].metadata["duration_ms"] > 0
    assert by_id["submit_turn_streaming_telemetry"].metadata["stats_input_tokens"] > 0
    assert by_id["submit_turn_streaming_telemetry"].metadata["stats_output_tokens"] > 0
    assert by_id["error_and_timeout_contracts"].metadata["http_500_attempts"] >= 2
    assert by_id["error_and_timeout_contracts"].metadata["timeout_raised"] is True
    assert by_id["error_and_timeout_contracts"].metadata["http_connection_reuse_enabled"] is False

    forced_reqs = [
        req
        for req in probe_server.requests
        if any(
            isinstance(m, dict)
            and m.get("role") == "user"
            and "PROBE_TOOLS_FORCED" in str(m.get("content", ""))
            for m in req.body.get("messages", [])
        )
    ]
    assert forced_reqs
    forced_tool_names = {
        t["function"]["name"]
        for t in forced_reqs[0].body.get("tools", [])
        if isinstance(t, dict) and isinstance(t.get("function"), dict)
    }
    assert "probe_echo_tag" in forced_tool_names
    assert "probe_lookup_fact" not in forced_tool_names

    handoff_reqs = [
        req
        for req in probe_server.requests
        if any(
            isinstance(t, dict)
            and isinstance(t.get("function"), dict)
            and t["function"].get("name") == "transfer_to_specialist"
            for t in req.body.get("tools", [])
        )
    ]
    assert handoff_reqs


def test_probe_loopback_server_handles_sse_streaming_and_closure_judgment(
    probe_server: ProbeLoopbackServer,
) -> None:
    from openminion.modules.llm.providers.openai.adapter import OpenAIProvider
    from openminion.modules.llm.schemas import LLMRequest, Message

    provider = OpenAIProvider()
    try:
        # With service_vendor='openai', OpenAIProvider.stream preserves usage on done events.
        events_with_vendor = list(
            provider.stream(
                LLMRequest(messages=[Message(role="user", content="PROBE_STREAM_TURN")]),
                {
                    "model": "stub-model",
                    "base_url": probe_server.base_url,
                    "api_key": "test-sse-key",
                    "http_connection_reuse_enabled": False,
                    "provider_identity": {"service_vendor": "openai"},
                },
            )
        )
        # Default loopback (preserve_response_facts=False) still streams text deltas + done.
        events_default = list(
            provider.stream(
                LLMRequest(messages=[Message(role="user", content="PROBE_STREAM_TURN")]),
                {
                    "model": "stub-model",
                    "base_url": probe_server.base_url,
                    "api_key": "test-sse-key",
                    "http_connection_reuse_enabled": False,
                },
            )
        )
    finally:
        provider.close()

    delta_text = "".join(evt.delta_text or "" for evt in events_with_vendor if evt.type == "delta")
    assert "STREAM_TELEMETRY_OK" in delta_text
    assert any(
        evt.type == "done" and evt.usage is not None and evt.usage.input_tokens == 12
        for evt in events_with_vendor
    )
    assert "STREAM_TELEMETRY_OK" in "".join(
        evt.delta_text or "" for evt in events_default if evt.type == "delta"
    )
    assert any(evt.type == "done" for evt in events_default)

    closure_json_step = _probe_internal_classifier_step(
        {
            "tool_choice": {"type": "function", "function": {"name": "submit_output"}},
            "tools": [{"function": {"parameters": {"title": "ClosureJudgment"}}}],
            "messages": [
                {
                    "role": "user",
                    "content": '{"closure_action_summary": "{\\"status\\": \\"OK\\"}"}',
                }
            ],
        }
    )
    assert closure_json_step is not None
    assert closure_json_step["calls"][0]["arguments"]["final_answer"] == '{"status": "OK"}'

    closure_ctx_step = _probe_internal_classifier_step(
        {
            "tool_choice": {"type": "function", "function": {"name": "submit_output"}},
            "tools": [{"function": {"parameters": {"title": "ClosureJudgment"}}}],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "[JUDGE CONTEXT]\n"
                        "candidate_reason: act_adaptive_final_text\n"
                        'action_summary: {"status": "OK", "block": "subagent_delegation", "score": 0.97}\n'
                        "closure_action_outputs: {}"
                    ),
                }
            ],
        }
    )
    assert closure_ctx_step is not None
    args = closure_ctx_step["calls"][0]["arguments"]
    assert args["satisfied"] is True
    assert args["next_action"] == "close"
    assert args["final_answer"] == '{"status": "OK", "block": "subagent_delegation", "score": 0.97}'


def test_probe_doc_export_scrubs_secrets_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_token = "sk-top-secret-live-token-987654"
    monkeypatch.setenv("OPENAI_API_KEY", secret_token)
    probes = [
        ProbeCheckResult(
            probe_id=pid,
            name=f"Probe {pid}",
            passed=True,
            detail=f"Observed secret={secret_token} Bearer {secret_token} during check.",
            latency_ms=12.5,
            metadata={"callback_count": 2, "http_500_attempts": 6, "chunk_count": 12},
        )
        for pid in EXPECTED_PROBE_IDS
    ]
    report = ProbeSuiteReport(
        sdk_version="0.1.21",
        preset="openai-compatible",
        model="stub-model",
        base_url_host="http://127.0.0.1:49999/v1",
        calibration_status="[Loopback Stub Baseline — awaiting C4 live LLM calibration]",
        generated_at="2026-11-14T00:00:00+00:00",
        total_probes=len(probes),
        passed_probes=len(probes),
        failed_probes=0,
        total_latency_ms=125.0,
        probes=probes,
        dx_findings=build_empirical_dx_findings(probes),
    )
    docs_dir = tmp_path / "docs"
    tested_path, learned_path = export_probe_docs(
        report,
        docs_dir=docs_dir,
        secret_env_names=["OPENAI_API_KEY"],
    )

    assert tested_path.exists() and learned_path.exists()
    tested_text = tested_path.read_text(encoding="utf-8")
    learned_text = learned_path.read_text(encoding="utf-8")
    assert "[Loopback Stub Baseline — awaiting C4 live LLM calibration]" in tested_text
    assert "[Loopback Stub Baseline — awaiting C4 live LLM calibration]" in learned_text
    assert secret_token not in tested_text
    assert secret_token not in learned_text
    assert "[REDACTED_SECRET]" in tested_text
    assert "FreshnessContract" in learned_text
    assert "ClosureJudgment" in learned_text
    assert "http_connection_reuse_enabled" in learned_text

    with pytest.raises(ValueError, match="unredacted"):
        assert_no_plaintext_secrets(
            f"Leaked key: {secret_token}",
            extra_secrets=[secret_token],
        )


def test_cli_probe_exports_sanitized_docs_and_json_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    probe_server: ProbeLoopbackServer,
) -> None:
    secret_value = "sk-cli-probe-secret-token-xyz123"
    monkeypatch.setenv("OPENAI_API_KEY", secret_value)

    home_root = tmp_path / "cli-probe-home"
    data_root = tmp_path / "cli-probe-state"
    docs_dir = tmp_path / "cli-docs"
    out_file = tmp_path / "probe-report.json"

    rc = main(
        [
            "probe",
            "--preset",
            "openai-compatible",
            "--base-url",
            probe_server.base_url,
            "--model",
            "stub-model",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--home-root",
            str(home_root),
            "--data-root",
            str(data_root),
            "--export-docs",
            "--docs-dir",
            str(docs_dir),
            "--output",
            str(out_file),
        ]
    )

    assert rc == 0
    stdout_report = ProbeSuiteReport.model_validate_json(capsys.readouterr().out)
    assert stdout_report.passed_probes == 10
    assert out_file.exists()
    assert (docs_dir / "BUILDING_BLOCKS_TESTED.md").exists()
    assert (docs_dir / "WHAT_WE_LEARNED.md").exists()

    agent_configs = list(home_root.rglob("agents.json"))
    assert agent_configs
    for artifact in [
        out_file,
        docs_dir / "BUILDING_BLOCKS_TESTED.md",
        docs_dir / "WHAT_WE_LEARNED.md",
        *agent_configs,
    ]:
        assert secret_value not in artifact.read_text(encoding="utf-8")


def test_cli_probe_returns_nonzero_when_probe_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fail-probe-token-0001")
    failing_server = ProbeLoopbackServer(smart_dispatch=False)
    failing_server.set_default(error_step(status=400, message="Forced non-retryable probe failure"))
    try:
        rc = main(
            [
                "probe",
                "--preset",
                "openai-compatible",
                "--base-url",
                failing_server.base_url,
                "--model",
                "stub-model",
                "--api-key-env",
                "OPENAI_API_KEY",
                "--home-root",
                str(tmp_path / "fail-home"),
                "--data-root",
                str(tmp_path / "fail-state"),
                "--probes",
                "agent_runtime_isolation",
                "--max-retries",
                "1",
            ]
        )
    finally:
        failing_server.close()

    assert rc != 0
    captured = capsys.readouterr()
    parsed = ProbeSuiteReport.model_validate_json(captured.out)
    assert parsed.total_probes == 1
    assert parsed.failed_probes == 1
