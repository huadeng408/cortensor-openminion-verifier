# What We Learned: OpenMinion 0.1 SDK Empirical DX Report

> **Calibration Posture**: [Loopback Stub Baseline — awaiting C4 live LLM calibration]

Generated directly from `BuildingBlockProbeRunner.run_all()` against `openminion==0.1.21` (`preset=openai-compatible`, `model=stub-model`, `endpoint=http://127.0.0.1:59576/v1`, `10/10` passed in `12026.09 ms`).

## Empirical SDK & DX Findings

### 1. Internal Structured Classifier Turns (FreshnessContract / FinalizationStatus / ClosureJudgment)

openminion==0.1.21 emits out-of-band tool_choice='submit_output' requests with JSON schema titles `FreshnessContract`, `FinalizationStatus`, and `ClosureJudgment`. In closure evaluation, `[JUDGE CONTEXT]` supplies `action_summary:` while `final_close_message()` prefers `ClosureJudgment.final_answer` over `action_result.summary`, so gateways/stubs handling `ClosureJudgment` must preserve `action_summary` / `closure_action_summary` or risk overwriting structured JSON answers.

### 2. Explicit thread_id Required for Multi-Turn Agent.run(session_id=...) Continuity

Calling `Agent.run(..., session_id=session_a)` returns an allocated `thread_id` (`metadata['thread_id']`); without passing `thread_id=turn1.thread_id` on subsequent calls, `openminion==0.1.21` starts a fresh conversation thread even with matching `session_id`. Forwarding both `session_id` and `thread_id` retains transcript history while separate `session_id` values remain isolated.

### 3. AnthropicProvider (/v1/messages + x-api-key) vs OpenAI-Compatible & Cortensor Adapters

`AnthropicProvider` sends POST `{base_url}/messages` with `x-api-key` and `anthropic-version` headers (`accept: text/event-stream` for streaming), whereas `OpenAIProvider` and `CortensorProvider` use Bearer auth (`Authorization: Bearer ...`) against `/chat/completions` or `/api/v2/completions`.

### 4. Inline Boolean approval_callback vs Async RuntimeTurnHandle.resolve_approval()

`Agent.run(..., approval_callback=...)` bridges a synchronous/awaitable boolean guard onto the brain worker thread (observed 2 callback invocations across allow & deny gates on `@tool(dangerous=True, min_scope='WRITE_SAFE')`). In contrast, `APIRuntime.submit_turn()` sets `approval_transport='turn_stream'` and requires stream consumers to resolve `approval` chunks via `handle.resolve_approval(approval_id=..., decision='allow_once'|'deny')` with bounded wait timeouts.

### 5. Windows SQLite Worktree Isolation & http_connection_reuse_enabled=False

Passing explicit `home_root` and `data_root` isolates `.openminion/agents.json` and SQLite/Alembic state per worktree on Windows. Disabling `http_connection_reuse_enabled=False` avoids persistent `httpx.Client` socket reuse (`http_client_for_config()` returns `None` and falls back to `urllib.request.urlopen`), preventing stale keep-alive errors across ephemeral or loopback endpoints.

### 6. Layered Retry Multiplication, SSE Usage Gating & TurnTelemetry vs stats

On HTTP 500 with `provider_retry_max_attempts=2`, observed 6 HTTP attempts because `LLMCTLBridgeProvider` adds inner transport retries (`max_retries=2`) inside `BrainRunner`'s outer retry loop. `submit_turn()` captured 12 TurnChunk(s) with `TurnTelemetry(duration_ms=328, tokens_in=0, tokens_out=0)` vs `TurnResponse.stats(input_tokens=22, output_tokens=25)`: `daemon.py` reads `metadata.get('usage_prompt_tokens')`, whereas the runtime populates `total_input_tokens_used` and `stats`. Additionally, `OpenAIProvider.stream()` skips SSE `usage` chunks unless `provider_identity={'service_vendor': 'openai'}` enables `preserve_response_facts`.

## Observed Runtime Measurements

| Probe ID | Status | Latency (ms) | Key Telemetry |
|---|---|---:|---|
| `agent_runtime_isolation` | PASS | 1841.56 | `db_count=14, run_id=eb2bcd34613440d1a4fe734bcdc630fd, secret_free_config=True` |
| `structured_pydantic_output` | PASS | 738.87 | `fallback_stub_used=False, negative_validation_error=True, score=0.99, status=OK` |
| `tool_and_forced_tools` | PASS | 1154.89 | `forced_tool=probe_echo_tag, invocations=['probe_lookup_fact:cortensor-poi', 'probe_echo_tag:forced-c3']` |
| `policy_confirmation_gate` | PASS | 818.22 | `allow_executed=True, callback_count=2, deny_blocked=True, executed_ids=['att-allow']` |
| `session_continuity` | PASS | 794.27 | `same_session_recalled=True, second_session_isolated=True, session_a=probe-sess-a-20669628, session_b=probe-sess-b-6104f8ed, thread_id=probe-sess-a-20669628:9a06a41f2a034cd18dcc14d96507288e` |
| `memory_bundle_portability` | PASS | 1.96 | `bundle_version=memory_bundle.v1, invalid_mode_rejected=True, item_count=1` |
| `subagent_delegation` | PASS | 571.87 | `context_id=subagent-80637f7fc9e4, parent_transcript_inherited=False, subagent_calls=['subagent-check'], tool_allowlist=['probe_subagent_tool']` |
| `agent_handoff` | PASS | 932.18 | `run_id=1a88525b01e54e699091cc806fa93bed, tool_name=transfer_to_specialist` |
| `submit_turn_streaming_telemetry` | PASS | 325.93 | `chunk_count=12, chunk_kinds=['status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'final_text', 'status'], duration_ms=328, queue_wait_ms=0, retries=0, stats={'input_tokens': 22, 'output_tokens': 25, 'cache_read_tokens': 0, 'llm_calls': 2, 'tool_calls': 0, 'tool_errors': 0, 'duration_ms': 207}, stats_input_tokens=22, stats_output_tokens=25, telemetry_metadata_mismatch=True, tokens_in=0, tokens_out=0` |
| `error_and_timeout_contracts` | PASS | 4494.07 | `http_500_attempts=6, http_connection_reuse_enabled=False, provider_error_raised=True, timeout_exception=TurnTimeoutError, timeout_raised=True` |
