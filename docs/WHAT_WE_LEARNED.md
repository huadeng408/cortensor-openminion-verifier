# What We Learned: OpenMinion 0.1 SDK Empirical DX Report

> **Calibration Posture**: [Live LLM Calibrated]

Generated directly from `BuildingBlockProbeRunner.run_all()` against `openminion==0.1.21` (`preset=openai-compatible`, `model=grok-4.7`, `endpoint=https://<configured-openai-compatible-relay>/v1`, `10/10` passed in `611888.99 ms`).

## Empirical SDK & DX Findings

### 1. Worktree-Isolated home_root / data_root Containment

`create_isolated_runtime()` bound isolated `home_root` and `data_root` SQLite/agents.json directories (`db_count=14`, `secret_free_config=True`, `run_id=2d700e1618cd402c803fd8c2f68ddb2d`), preventing mutation of developer home state on Windows.

### 2. Internal Classifiers (FreshnessContract / FinalizationStatus / ClosureJudgment) & Output Coercion

openminion==0.1.21 issues `tool_choice='submit_output'` internal classifier turns (`FreshnessContract`, `FinalizationStatus`, and `ClosureJudgment` where stubs/gateways must preserve `action_summary`). `Agent._coerce_output()` also strips the `f'{agent_id}: '` reply prefix via `_extract_json_object()`, producing typed schema output (`status=OK`, `score=0.99`, `negative_validation_error=True`, `fallback_stub_used=False`).

### 3. Read-Only @tool Binding & tool_choice='forced' Deterministic Dispatch

Binding `@tool(min_scope='READ_ONLY')` with `tool_choice='forced'` invoked `probe_echo_tag` (call_count=2, forced_invoked=True, invocations=['probe_lookup_fact:cortensor-poi', 'probe_echo_tag:forced-c3']) without filesystem writes.

### 4. approval_callback Boolean Gate & Fail-Closed approval_callback=None Pause/Resume

`@tool(dangerous=True, min_scope='WRITE_SAFE')` recorded `callback_count=2`, `allow_executed=True`, and `deny_blocked=True`. Passing `approval_callback=None` paused fail-closed (`pause_blocked=True`, `pending_confirmation_id=call-5a36ca6b-fe80-4d14-8500-59e5a01ea5ef-0`) and executed only after `Agent.run('allow_once', session_id=..., thread_id=...)` (`resume_executed=True`).

### 5. Explicit thread_id Required for Multi-Turn Agent.run(session_id=...) Continuity

Retaining context across turns on the same session required forwarding `thread_id=probe-sess-a-5b958e6d:e44db35cf831436fab48837c1f5f6be8` alongside `session_id`; a distinct session preserved isolation (`same_session_recalled=True`, `second_session_isolated=True`).

### 6. Cross-Runtime MemoryBundle Export/Import Portability

OpenMinion primitives `export_bundle()`, `save_bundle()`, `load_bundle()`, and `import_bundle()` (wrapped by `export_session_memory()`/`import_session_memory()`) serialized and restored bundle state (`bundle_version=memory_bundle.v1`, `item_count=1`, `invalid_mode_rejected=True`) into a separate APIRuntime SQLite store.

### 7. Isolated Subagent Passes, task_update Collisions & 90s Timeout Forwarding

Separate subagent runtime sessions avoid `resolve_entry_task_update()` `Missing/Duplicate task_update` crashes (`openminion/modules/brain/loop/context/task_context.py:153-191`) when dispatching sequential passes, while explicit `timeout_seconds` prevents falling back to the `90.0s` default (`context_id=subagent-bf6c16b7d24d`, `parent_transcript_inherited=False`, `tool_allowlist=['probe_subagent_tool']`, `subagent_calls=['subagent-check']`).

### 8. Peer Handoff Delegation & build_delegate_tool() Timeout/Approval Gap

Peer handoff reached specialist `transfer_to_specialist` (`handoff_invocations=1`, `verbatim_ack=False`). Notably, `openminion/api/handoff.py:169` invokes `handoff.target.run(message)` without caller `timeout_seconds` or `approval_callback`, so target runtimes need explicit `PolicyGrantInput(max_uses=1)` for autonomous confirmation-gated publication.

### 9. APIRuntime.submit_turn() TurnChunks & TurnTelemetry vs TurnResponse.stats

Collected 12 TurnChunk(s) with `TurnTelemetry(duration_ms=6281, tokens_in=0, tokens_out=0, retries=0, queue_wait_ms=0)` vs `TurnResponse.stats(input_tokens=11841, output_tokens=430)`; `telemetry_metadata_mismatch=True`.

### 10. Provider Wire Formats, Layered HTTP 500 Retries & http_connection_reuse_enabled=False

With `http_connection_reuse_enabled=False`, HTTP 500 produced 6 attempts (`provider_retry_max_attempts=2` * transport retries) before raising `ProviderError`, and slow responses hit `TurnTimeoutError`. Wire checks verified `AnthropicProvider` (`x-api-key` + `anthropic-version` -> `/anthropic/v1/messages`), `CortensorProvider` (`Bearer` -> `/cortensor/api/v2/completions`), and `OpenAIProvider.stream()` SSE usage gating (`without_vendor=False`, `with_service_vendor_openai=True`).

## Observed Runtime Measurements

| Probe ID | Status | Latency (ms) | Key Telemetry |
|---|---|---:|---|
| `agent_runtime_isolation` | PASS | 6576.08 | `db_count=14, run_id=2d700e1618cd402c803fd8c2f68ddb2d, secret_free_config=True` |
| `structured_pydantic_output` | PASS | 207213.19 | `fallback_stub_used=False, negative_validation_error=True, score=0.99, status=OK` |
| `tool_and_forced_tools` | PASS | 77598.94 | `forced_tool=probe_echo_tag, invocations=['probe_lookup_fact:cortensor-poi', 'probe_echo_tag:forced-c3']` |
| `policy_confirmation_gate` | PASS | 76300.74 | `allow_executed=True, callback_count=2, deny_blocked=True, executed_ids=['att-allow', 'att-pause-resume'], pause_blocked=True, paused_thread_id=probe-policy-pause-18d3a53ede0:0274e1c9510a48b9b8727e9cfec5f271, pending_confirmation_id=call-5a36ca6b-fe80-4d14-8500-59e5a01ea5ef-0, resume_executed=True` |
| `session_continuity` | PASS | 92405.48 | `same_session_recalled=True, second_session_isolated=True, session_a=probe-sess-a-5b958e6d, session_b=probe-sess-b-c3d87288, thread_id=probe-sess-a-5b958e6d:e44db35cf831436fab48837c1f5f6be8` |
| `memory_bundle_portability` | PASS | 1.99 | `bundle_version=memory_bundle.v1, invalid_mode_rejected=True, item_count=1` |
| `subagent_delegation` | PASS | 30651.67 | `context_id=subagent-bf6c16b7d24d, parent_transcript_inherited=False, subagent_calls=['subagent-check'], tool_allowlist=['probe_subagent_tool']` |
| `agent_handoff` | PASS | 110097.21 | `handoff_invocations=1, run_id=31660b20ead3480d837e72c95be70f96, tool_name=transfer_to_specialist, verbatim_ack=False` |
| `submit_turn_streaming_telemetry` | PASS | 6278.02 | `chunk_count=12, chunk_kinds=['status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'final_text', 'status'], duration_ms=6281, queue_wait_ms=0, retries=0, stats={'cache_read_tokens': 1152, 'duration_ms': 6149, 'input_tokens': 11841, 'llm_calls': 1, 'output_tokens': 430, 'tool_calls': 0, 'tool_errors': 0}, stats_input_tokens=11841, stats_output_tokens=430, telemetry_metadata_mismatch=True, tokens_in=0, tokens_out=0` |
| `error_and_timeout_contracts` | PASS | 4765.67 | `http_500_attempts=6, http_connection_reuse_enabled=False, provider_error_raised=True, provider_wire_formats={'anthropic_path': '/anthropic/v1/messages', 'anthropic_x_api_key': True, 'anthropic_version_header': True, 'cortensor_path': '/cortensor/api/v2/completions', 'cortensor_bearer_auth': True, 'openai_sse_usage_without_vendor': False, 'openai_sse_usage_with_vendor': True}, timeout_exception=TurnTimeoutError, timeout_raised=True` |
