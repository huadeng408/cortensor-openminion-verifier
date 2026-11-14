# What We Learned: OpenMinion 0.1 SDK Empirical DX Report

> **Calibration Posture**: [Live LLM Calibrated]

Generated directly from `BuildingBlockProbeRunner.run_all()` against `openminion==0.1.21` (`preset=openai-compatible`, `model=grok-4.7`, `endpoint=https://<configured-openai-compatible-relay>/v1`, `10/10` passed in `604418.99 ms`).

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

On HTTP 500 with `provider_retry_max_attempts=2`, observed 6 HTTP attempts because `LLMCTLBridgeProvider` adds inner transport retries (`max_retries=2`) inside `BrainRunner`'s outer retry loop. `submit_turn()` captured 12 TurnChunk(s) with `TurnTelemetry(duration_ms=6281, tokens_in=0, tokens_out=0)` vs `TurnResponse.stats(input_tokens=11841, output_tokens=430)`: `daemon.py` reads `metadata.get('usage_prompt_tokens')`, whereas the runtime populates `total_input_tokens_used` and `stats`. Additionally, `OpenAIProvider.stream()` skips SSE `usage` chunks unless `provider_identity={'service_vendor': 'openai'}` enables `preserve_response_facts`.

### 7. 90s Turn-Timeout Default, Handoff Forwarding Gap & Live Paraphrasing

`Agent.run(..., timeout_seconds=None)` defaults internal turn timeout to `90.0s` regardless of `OpenMinionConfig` provider HTTP timeouts unless `timeout_seconds` is explicitly forwarded to BOTH `Agent.run(timeout_seconds=...)` and `subagent(timeout_seconds=...)`. Multi-tool reasoning turns routinely span multiple round-trips (`classifier + tool + finalization`). Furthermore, in `openminion/api/handoff.py:169`, `build_delegate_tool()` calls `handoff.target.run(message)` without forwarding caller `timeout_seconds` or `approval_callback`, leaving peer handoff targets on the `90.0s` default turn timeout and requiring `PolicyGrantInput` on the target runtime for `allow_once` gating. Additionally, live LLMs execute `Handoff` (`transfer_to_specialist`) cleanly and paraphrase the specialist confirmation in coordinator prose rather than echoing synthetic marker tokens verbatim.

### 8. Structured Output Envelope Collision (`respond(answer, freshness)` + `agent_id:` Prefix)

In `openminion==0.1.21`, `runtime.run_turn()` formats `body` with an `f'{agent_id}: '` prefix, causing `Agent._coerce_output()`'s initial `output_type.model_validate_json(text)` to fail and rely on `_extract_json_object(text)`. Meanwhile, `BrainRunner`'s entry prompt instructs direct replies using `respond(answer=..., freshness=...)`; some live models occasionally emit that outer envelope as assistant text (`agent: {"answer": "{...}", "freshness": {...}}`), causing `_extract_json_object()` to extract the outer `freshness` wrapper instead of the inner JSON payload and raise `AgentOutputValidationError`. Explicitly commanding single-line RFC-8259 double-quoted JSON and avoiding unquoted pseudo-schemas improves compliance.

### 9. Shared Session & Parallel Tool-Call `task_update` Collision (`resolve_entry_task_update`)

In `openminion/modules/brain/loop/context/task_context.py:153-191`, `resolve_entry_task_update()` raises `ValueError` (`'Missing task_update'` or `'Exactly one task_update is allowed per entry response'`), turning the reply into the fallback clarification `'I could not safely update the task conditions...'` whenever an active session receives sequential `subagent()` calls sharing the same raw `session_id` or when a model batches multiple tool calls carrying duplicate `task_update` sidecars. Giving each subagent pass an isolated runtime `session_id` while persisting cross-turn citations in explicit `MemoryBundle` state avoids the crash.

## Observed Runtime Measurements

| Probe ID | Status | Latency (ms) | Key Telemetry |
|---|---|---:|---|
| `agent_runtime_isolation` | PASS | 6576.08 | `db_count=14, run_id=2d700e1618cd402c803fd8c2f68ddb2d, secret_free_config=True` |
| `structured_pydantic_output` | PASS | 207213.19 | `fallback_stub_used=False, negative_validation_error=True, score=0.99, status=OK` |
| `tool_and_forced_tools` | PASS | 77598.94 | `forced_tool=probe_echo_tag, invocations=['probe_lookup_fact:cortensor-poi', 'probe_echo_tag:forced-c3']` |
| `policy_confirmation_gate` | PASS | 68637.14 | `allow_executed=True, callback_count=2, deny_blocked=True, executed_ids=['att-allow']` |
| `session_continuity` | PASS | 92405.48 | `same_session_recalled=True, second_session_isolated=True, session_a=probe-sess-a-5b958e6d, session_b=probe-sess-b-c3d87288, thread_id=probe-sess-a-5b958e6d:e44db35cf831436fab48837c1f5f6be8` |
| `memory_bundle_portability` | PASS | 1.99 | `bundle_version=memory_bundle.v1, invalid_mode_rejected=True, item_count=1` |
| `subagent_delegation` | PASS | 30651.67 | `context_id=subagent-bf6c16b7d24d, parent_transcript_inherited=False, subagent_calls=['subagent-check'], tool_allowlist=['probe_subagent_tool']` |
| `agent_handoff` | PASS | 110097.21 | `handoff_invocations=1, run_id=31660b20ead3480d837e72c95be70f96, tool_name=transfer_to_specialist, verbatim_ack=False` |
| `submit_turn_streaming_telemetry` | PASS | 6278.02 | `chunk_count=12, chunk_kinds=['status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'status', 'final_text', 'status'], duration_ms=6281, queue_wait_ms=0, retries=0, stats={'cache_read_tokens': 1152, 'duration_ms': 6149, 'input_tokens': 11841, 'llm_calls': 1, 'output_tokens': 430, 'tool_calls': 0, 'tool_errors': 0}, stats_input_tokens=11841, stats_output_tokens=430, telemetry_metadata_mismatch=True, tokens_in=0, tokens_out=0` |
| `error_and_timeout_contracts` | PASS | 4595.94 | `http_500_attempts=6, http_connection_reuse_enabled=False, provider_error_raised=True, timeout_exception=TurnTimeoutError, timeout_raised=True` |
