# Cortensor Hackathon #5 PR Submission Draft

> **Target Upstream Repository**: `cortensor/community-projects` (`apps/cortensor-openminion-verifier`)  
> **Source Repository**: `huadeng408/cortensor-openminion-verifier`  
> **SDK Version**: `openminion==0.1.21`

---

## Operator Pre-Submission Checklist (Do Before Opening Upstream PR)

- [ ] **Flip Visibility Manually**: `huadeng408/cortensor-openminion-verifier` is currently kept **`PRIVATE`**. Switch it to `PUBLIC` manually in GitHub Settings right before submitting the upstream PR (or copy the clean tracked tree into your fork of `cortensor/community-projects`).
- [ ] **Verify Clean Env & Secret Scan**: Confirm `.env`, `.openminion/`, `.openminion-state/`, and API keys remain untracked and zero secrets appear in git history (`assert_no_plaintext_secrets` passed across working tree and fixtures).
- [ ] **Attach Demo Video**: Render and attach `artifacts/cortensor_hackathon5_demo.mp4` (`1920x1080`, `75s`, captioned H.264 MP4) in the PR description body via GitHub's video upload dropzone.
- [ ] **Run Final Test Check**: Verify `.\.venv\Scripts\python.exe -m pytest -q` passes (`0 failed`) on `main`.

---

## Copy-Paste PR Body for `cortensor/community-projects`

### Summary

Adds **`cortensor-openminion-verifier`** (`apps/cortensor-openminion-verifier`), an isolated **Redundant Consensus Verifier & Building-Block Probe Suite** built on **`openminion==0.1.21`**.

Given a prediction-market / oracle **`ClaimDossier`**, the application coordinates:
1. Two isolated **`subagent()`** verifier passes (**`corroborator`** and **`skeptic`**) restricted to `min_scope="READ_ONLY"` `@tool` evidence tools (`parent_transcript_inherited=False`).
2. Consensus synthesis (**`synthesize_consensus()`**) into a **`ConsensusVerdict`** with portable **`MemoryBundle`** persistence scoped per `session_id`.
3. Approval-gated external publication via **`Handoff`** (`transfer_to_publisher`) enforcing fail-closed `pause`, explicit `deny`, or single-use **`allow_once`** (`PolicyGrantInput(max_uses=1)` + replay protection).
4. A 10-probe **`BuildingBlockProbeRunner`** suite verified against both ephemeral loopback servers and live OpenAI-compatible inference.

### OpenMinion 0.1 Building Blocks Exercised (`10/10` Verified)

1. **`agent_runtime_isolation`**: Isolated `home_root` / `data_root` SQLite DBs + scrubbed secret-free `agents.json`.
2. **`structured_pydantic_output`**: Strict `BaseModel` validation + `AgentOutputValidationError` negative contract.
3. **`tool_and_forced_tools`**: Custom `@tool` dispatch + deterministic `forced_tools=(...)` execution.
4. **`policy_confirmation_gate`**: `@tool(dangerous=True, min_scope="WRITE_SAFE")` gated via `approval_callback` (`allow` & `deny`).
5. **`session_continuity`**: Multi-turn `thread_id` continuity within `session_id` + zero cross-session leakage.
6. **`memory_bundle_portability`**: `export_bundle` -> `save_bundle` -> `load_bundle` -> `import_bundle` roundtrip.
7. **`subagent_delegation`**: Isolated `SubagentRunContext` delegation without closing parent runtime.
8. **`agent_handoff`**: Coordinator-to-specialist peer transfer via `Handoff` (`transfer_to_specialist` / `transfer_to_publisher`).
9. **`submit_turn_streaming_telemetry`**: Real `APIRuntime.submit_turn()` streaming `TurnChunk` collection + `TurnResponse.stats` vs `TurnTelemetry`.
10. **`error_and_timeout_contracts`**: `http_connection_reuse_enabled=False` Windows policy, HTTP 500 `ProviderError` retry behavior, and `TurnTimeoutError`.

See full live matrix in [`docs/BUILDING_BLOCKS_TESTED.md`](BUILDING_BLOCKS_TESTED.md).

### Key Empirical DX Findings (`9` Findings from Live `openminion==0.1.21` Calibration)

Full technical breakdown with source references and workarounds is documented in [`docs/WHAT_WE_LEARNED.md`](WHAT_WE_LEARNED.md):

1. **Out-of-Band Classifier Turns**: `FreshnessContract` / `FinalizationStatus` / `ClosureJudgment` (`tool_choice="submit_output"`) require preserving `action_summary` / `closure_action_summary`.
2. **Explicit `thread_id` Requirement**: `Agent.run(session_id=...)` allocates a fresh thread unless `thread_id=turn1.thread_id` is also forwarded.
3. **Provider Protocol Split**: `AnthropicProvider` (`/messages` + `x-api-key`) vs `OpenAIProvider` & `CortensorProvider` (`/chat/completions` or `/api/v2/completions` + Bearer auth).
4. **Sync/Awaitable `approval_callback` vs `submit_turn` Streams**: `submit_turn()` uses `approval_transport="turn_stream"` and `handle.resolve_approval(...)`.
5. **Windows Worktree Isolation & Socket Reuse Policy**: Explicit `home_root`/`data_root` + `http_connection_reuse_enabled=False` prevents SQLite collisions and stale keep-alive errors.
6. **Retry Multiplication & `TurnTelemetry` Mismatch**: `LLMCTLBridgeProvider` retries (`max_retries=2`) multiply with `BrainRunner`'s outer retry loop (`provider_retry_max_attempts=2` -> 6 attempts on HTTP 500); `TurnTelemetry` reads `metadata.get("usage_prompt_tokens")` (`0`) whereas `TurnResponse.stats` reports actual usage (`11,841` input / `430` output in probe #9).
7. **90s Turn-Timeout Default & `Handoff` Forwarding Gap**: `Agent.run()` defaults `timeout_seconds` to `90.0s`, and `build_delegate_tool()` (`openminion/api/handoff.py:169`) calls `handoff.target.run(message)` without forwarding `timeout_seconds` or `approval_callback`, requiring target-runtime `PolicyGrantInput` and prompt efficiency under 90s; additionally, live coordinators paraphrase peer responses rather than echoing raw markers verbatim.
8. **Structured Output Envelope Collision**: `runtime.run_turn()` prepends `f"{agent_id}: "` and `BrainRunner`'s `respond(answer, freshness)` wrapper can collide with `_extract_json_object()` unless strict RFC-8259 raw JSON constraints are reiterated at the end of the prompt.
9. **Shared Session / Parallel Tool-Call `task_update` Collision**: `resolve_entry_task_update()` raises `ValueError` when sequential `subagent()` calls share a raw `session_id` or batch parallel tool calls; per-pass isolated runtime `session_id`s + explicit `MemoryBundle` citation handoff eliminate the crash.

### Calibration Telemetry Summary (`[Live LLM Calibrated]`)

- **10/10 Building-Block Probes (`grok-4.7`)**: `10/10` `PASS` (`failed=0`), `604,418.99 ms` total latency (`https://<configured-openai-compatible-relay>/v1`).
- **Dual-Pass Audit (`grok-4.6`, `delphi-btc-etf-2024`)**: Verdict `SUPPORTED`, `agreement_score=0.98`, `mean_confidence=0.94`, passes `corroborator (0.96)` & `skeptic (0.92)`, `3` read-only tool calls, `Handoff allow_once` `published=True`, `20` requests / `118,193` total tokens / `394,205 ms` recorded in [`fixtures/calibrated_sample_run.json`](../fixtures/calibrated_sample_run.json).

### Reproducibility & Demo Video

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
cortensor-verifier render-demo --sample-json fixtures/calibrated_sample_run.json --duration-seconds 75 --fps 10 -o artifacts/cortensor_hackathon5_demo.mp4
```

- **Demo Walkthrough Video (`1920x1080`, `75s`, captioned H.264 MP4)**: _[Attach rendered `artifacts/cortensor_hackathon5_demo.mp4` here when opening the upstream PR]_
