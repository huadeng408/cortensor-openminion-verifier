# OpenMinion 0.1 Building Blocks Tested

> **Calibration Posture**: [Loopback Stub Baseline — awaiting C4 live LLM calibration]

## Execution Summary

- **SDK Version**: `openminion==0.1.21`
- **Preset**: `openai-compatible`
- **Model**: `stub-model`
- **Endpoint Host**: `http://127.0.0.1:59576/v1`
- **Generated At (UTC)**: `2026-11-14T14:47:46.387973+00:00`
- **Result**: `10/10` probes passed (`failed=0`)
- **Total Suite Latency**: `12026.09 ms`

## Probe Matrix (10 Core OpenMinion Building Blocks)

| # | Probe ID | Building Block | Status | Latency (ms) | Observed Evidence |
|---:|---|---|---|---:|---|
| 1 | `agent_runtime_isolation` | Agent & APIRuntime Isolation | **PASS** | 1841.56 | Isolated agents.json verified secret-free; SQLite DB isolated under data_root (14 db file(s)); run_id=eb2bcd34613440d1a4fe734bcdc630fd. |
| 2 | `structured_pydantic_output` | Structured Pydantic Output & Validation Error | **PASS** | 738.87 | Validated _ProbeStructuredOutput (status=OK, score=0.99) and verified AgentOutputValidationError negative contract. |
| 3 | `tool_and_forced_tools` | @tool Registration & forced_tools Execution | **PASS** | 1154.89 | Executed auto tool (probe_lookup_fact) and forced_tools=(probe_echo_tag) cleanly. |
| 4 | `policy_confirmation_gate` | Policy Gate (@tool dangerous=True Allow & Deny) | **PASS** | 818.22 | Dangerous @tool(dangerous=True, min_scope='WRITE_SAFE') triggered approval_callback: allow executed att-allow; deny blocked att-deny. |
| 5 | `session_continuity` | Session Continuity & Cross-Session Isolation | **PASS** | 794.27 | Session probe-sess-a-20669628 (thread probe-sess-a-20669628:9a06a41f2a034cd18dcc14d96507288e) recalled marker across turns; isolated session probe-sess-b-6104f8ed had zero leakage. |
| 6 | `memory_bundle_portability` | MemoryBundle Export, Save, Load & Import | **PASS** | 1.96 | Roundtripped MemoryBundle vmemory_bundle.v1 (1 item) via export_bundle -> save_bundle -> load_bundle -> import_bundle(direct/candidate). |
| 7 | `subagent_delegation` | subagent() & SubagentRunContext Delegation | **PASS** | 571.87 | Child subagent (probe-corroborator) ran with isolated SubagentRunContext (context_id=subagent-80637f7fc9e4) without closing parent runtime. |
| 8 | `agent_handoff` | Handoff Peer Agent Transfer Tool | **PASS** | 932.18 | Handoff registered 'transfer_to_specialist' and executed peer specialist turn cleanly. |
| 9 | `submit_turn_streaming_telemetry` | submit_turn() Streaming TurnChunk & TurnTelemetry | **PASS** | 325.93 | Collected 12 TurnChunk(s) (status, final_text); TurnTelemetry(duration_ms=328, tokens_in=0, tokens_out=0, retries=0, queue_wait_ms=0); stats(input_tokens=22, output_tokens=25). |
| 10 | `error_and_timeout_contracts` | ProviderError Retries, Timeout & Connection Reuse Policy | **PASS** | 4494.07 | Verified http_connection_reuse_enabled=False; HTTP 500 raised ProviderError after 6 attempt(s); slow stub (1.5s vs 1.0s timeout) raised TurnTimeoutError. |

## Per-Probe Telemetry & Metadata

### `agent_runtime_isolation` — Agent & APIRuntime Isolation
- **Passed**: `True` (`1841.56 ms`)
- **Detail**: Isolated agents.json verified secret-free; SQLite DB isolated under data_root (14 db file(s)); run_id=eb2bcd34613440d1a4fe734bcdc630fd.
- **Metadata**: `{"db_count": 14, "run_id": "eb2bcd34613440d1a4fe734bcdc630fd", "secret_free_config": true}`

### `structured_pydantic_output` — Structured Pydantic Output & Validation Error
- **Passed**: `True` (`738.87 ms`)
- **Detail**: Validated _ProbeStructuredOutput (status=OK, score=0.99) and verified AgentOutputValidationError negative contract.
- **Metadata**: `{"fallback_stub_used": false, "negative_validation_error": true, "score": 0.99, "status": "OK"}`

### `tool_and_forced_tools` — @tool Registration & forced_tools Execution
- **Passed**: `True` (`1154.89 ms`)
- **Detail**: Executed auto tool (probe_lookup_fact) and forced_tools=(probe_echo_tag) cleanly.
- **Metadata**: `{"forced_tool": "probe_echo_tag", "invocations": ["probe_lookup_fact:cortensor-poi", "probe_echo_tag:forced-c3"]}`

### `policy_confirmation_gate` — Policy Gate (@tool dangerous=True Allow & Deny)
- **Passed**: `True` (`818.22 ms`)
- **Detail**: Dangerous @tool(dangerous=True, min_scope='WRITE_SAFE') triggered approval_callback: allow executed att-allow; deny blocked att-deny.
- **Metadata**: `{"allow_executed": true, "callback_count": 2, "deny_blocked": true, "executed_ids": ["att-allow"]}`

### `session_continuity` — Session Continuity & Cross-Session Isolation
- **Passed**: `True` (`794.27 ms`)
- **Detail**: Session probe-sess-a-20669628 (thread probe-sess-a-20669628:9a06a41f2a034cd18dcc14d96507288e) recalled marker across turns; isolated session probe-sess-b-6104f8ed had zero leakage.
- **Metadata**: `{"same_session_recalled": true, "second_session_isolated": true, "session_a": "probe-sess-a-20669628", "session_b": "probe-sess-b-6104f8ed", "thread_id": "probe-sess-a-20669628:9a06a41f2a034cd18dcc14d96507288e"}`

### `memory_bundle_portability` — MemoryBundle Export, Save, Load & Import
- **Passed**: `True` (`1.96 ms`)
- **Detail**: Roundtripped MemoryBundle vmemory_bundle.v1 (1 item) via export_bundle -> save_bundle -> load_bundle -> import_bundle(direct/candidate).
- **Metadata**: `{"bundle_version": "memory_bundle.v1", "invalid_mode_rejected": true, "item_count": 1}`

### `subagent_delegation` — subagent() & SubagentRunContext Delegation
- **Passed**: `True` (`571.87 ms`)
- **Detail**: Child subagent (probe-corroborator) ran with isolated SubagentRunContext (context_id=subagent-80637f7fc9e4) without closing parent runtime.
- **Metadata**: `{"context_id": "subagent-80637f7fc9e4", "parent_transcript_inherited": false, "subagent_calls": ["subagent-check"], "tool_allowlist": ["probe_subagent_tool"]}`

### `agent_handoff` — Handoff Peer Agent Transfer Tool
- **Passed**: `True` (`932.18 ms`)
- **Detail**: Handoff registered 'transfer_to_specialist' and executed peer specialist turn cleanly.
- **Metadata**: `{"run_id": "1a88525b01e54e699091cc806fa93bed", "tool_name": "transfer_to_specialist"}`

### `submit_turn_streaming_telemetry` — submit_turn() Streaming TurnChunk & TurnTelemetry
- **Passed**: `True` (`325.93 ms`)
- **Detail**: Collected 12 TurnChunk(s) (status, final_text); TurnTelemetry(duration_ms=328, tokens_in=0, tokens_out=0, retries=0, queue_wait_ms=0); stats(input_tokens=22, output_tokens=25).
- **Metadata**: `{"chunk_count": 12, "chunk_kinds": ["status", "status", "status", "status", "status", "status", "status", "status", "status", "status", "final_text", "status"], "duration_ms": 328, "queue_wait_ms": 0, "retries": 0, "stats": {"cache_read_tokens": 0, "duration_ms": 207, "input_tokens": 22, "llm_calls": 2, "output_tokens": 25, "tool_calls": 0, "tool_errors": 0}, "stats_input_tokens": 22, "stats_output_tokens": 25, "telemetry_metadata_mismatch": true, "tokens_in": 0, "tokens_out": 0}`

### `error_and_timeout_contracts` — ProviderError Retries, Timeout & Connection Reuse Policy
- **Passed**: `True` (`4494.07 ms`)
- **Detail**: Verified http_connection_reuse_enabled=False; HTTP 500 raised ProviderError after 6 attempt(s); slow stub (1.5s vs 1.0s timeout) raised TurnTimeoutError.
- **Metadata**: `{"http_500_attempts": 6, "http_connection_reuse_enabled": false, "provider_error_raised": true, "timeout_exception": "TurnTimeoutError", "timeout_raised": true}`
