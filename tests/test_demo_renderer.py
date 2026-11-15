"""Behavioral tests for captioned 1080p MP4 demo rendering and render-demo CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
import imageio.v2 as imageio
import numpy as np
import pytest

from cortensor_verifier.cli import main
from cortensor_verifier.demo_renderer import (
    _SCENE_CAPTIONS,
    DEFAULT_DEMO_DURATION_SECONDS,
    DEMO_HEIGHT,
    DEMO_WIDTH,
    TOTAL_SCENES,
    _create_fonts,
    _fit_caption_lines,
    _render_scene_canvas,
    render_demo_video,
)
from cortensor_verifier.probe import EXPECTED_PROBE_IDS


def _sample_payload() -> dict[str, Any]:
    return {
        "calibration_meta": {
            "sdk_version": "0.1.21",
            "preset": "openai-compatible",
            "model": "grok-4.6",
            "base_url_host": "https://<configured-openai-compatible-relay>/v1",
            "calibration_status": "[Live LLM Calibrated]",
            "generated_at": "2026-11-14T15:30:00+00:00",
        },
        "audit_bundle": {
            "claim_id": "delphi-btc-etf-2024",
            "preset": "openai-compatible",
            "dossier": {
                "claim_id": "delphi-btc-etf-2024",
                "title": "US Spot Bitcoin ETP Approval (January 2024)",
                "claim": (
                    "The U.S. SEC approved the listing and trading of multiple spot Bitcoin "
                    "exchange-traded products on January 10, 2024."
                ),
                "market_question": "Did the U.S. SEC approve spot Bitcoin ETPs on January 10, 2024?",
                "resolution_criteria": (
                    "Resolve SUPPORTED only if official SEC approval orders or Chair statement "
                    "confirm approval dated 2024-01-10."
                ),
                "source_hints": ["sec-spot-btc-2024-01-10", "federal-register-34-99306"],
                "tags": ["delphi", "regulation"],
                "metadata": {"market_id": "delphi-mkt-2024-001"},
            },
            "consensus": {
                "claim_id": "delphi-btc-etf-2024",
                "final_verdict": "SUPPORTED",
                "agreement_score": 0.99,
                "mean_confidence": 0.96,
                "disagreement_summary": "Corroborator and skeptic agreed on SUPPORTED.",
                "requires_human_review": False,
                "passes": [
                    {
                        "verdict": "SUPPORTED",
                        "confidence": 0.97,
                        "rationale": "SEC order 34-99306 and Chair statement confirm 2024-01-10 approval.",
                        "pass_role": "corroborator",
                        "citations": [
                            {
                                "source_id": "sec-spot-btc-2024-01-10",
                                "title": "Statement on the Approval of Spot Bitcoin Exchange-Traded Products",
                                "excerpt": "approved the listing and trading on January 10, 2024",
                            }
                        ],
                    },
                    {
                        "verdict": "SUPPORTED",
                        "confidence": 0.95,
                        "rationale": "Checked official filings; no contradictory SEC rescission found.",
                        "pass_role": "skeptic",
                        "citations": [
                            {
                                "source_id": "federal-register-34-99306",
                                "title": "SEC Release No. 34-99306 Order",
                                "excerpt": "Order Granting Accelerated Approval dated January 10, 2024",
                            }
                        ],
                    },
                ],
            },
            "tool_calls": ["load_delphi_market_fixture", "search_public_evidence", "fetch_source_excerpt"],
            "session_id": "cal-btc-etf-01",
            "publication": {
                "requested": True,
                "published": True,
                "publication_status": "published",
                "claim_id": "delphi-btc-etf-2024",
                "final_verdict": "SUPPORTED",
                "approval_mode": "allow_once",
                "thread_id": "thread-cal-pub-01",
                "approval_id": "appr-cal-01",
                "log_path": ".openminion-state/published_verdicts.jsonl",
            },
            "metadata": {
                "telemetry": {
                    "requests": 7,
                    "prompt_tokens": 1820,
                    "completion_tokens": 410,
                    "total_tokens": 2230,
                    "total_latency_ms": 42100,
                }
            },
        },
        "probe_report": {
            "suite_name": "openminion-0.1-building-blocks",
            "sdk_version": "0.1.21",
            "preset": "openai-compatible",
            "model": "grok-4.6",
            "base_url_host": "https://<configured-openai-compatible-relay>/v1",
            "calibration_status": "[Live LLM Calibrated]",
            "generated_at": "2026-11-14T15:30:00+00:00",
            "total_probes": len(EXPECTED_PROBE_IDS),
            "passed_probes": len(EXPECTED_PROBE_IDS),
            "failed_probes": 0,
            "total_latency_ms": 185000.0,
            "probes": [
                {
                    "probe_id": pid,
                    "name": f"Block {idx}: {pid}",
                    "passed": True,
                    "detail": f"Verified {pid} against real openminion runtime.",
                    "latency_ms": 1200.0 + idx * 100.0,
                    "metadata": {},
                }
                for idx, pid in enumerate(EXPECTED_PROBE_IDS, start=1)
            ],
            "dx_findings": [
                {
                    "title": "Explicit thread_id Required for Session Continuity",
                    "observation": "Must forward both session_id and thread_id across Agent.run turns.",
                },
                {
                    "title": "90s Turn-Timeout Default & Handoff Paraphrasing",
                    "observation": "Forward explicit timeout_seconds to Agent.run and subagent.",
                },
            ],
        },
    }


def test_default_duration_bounds_and_validation() -> None:
    assert 60 <= DEFAULT_DEMO_DURATION_SECONDS <= 300
    assert (DEMO_WIDTH, DEMO_HEIGHT) == (1920, 1080)

    sample = _sample_payload()
    with pytest.raises(ValueError, match="between 60 and 300"):
        render_demo_video(
            output_path=Path("unused-too-short.mp4"),
            audit_bundle=sample["audit_bundle"],
            probe_report=sample["probe_report"],
            duration_seconds=15,
            fps=4,
        )

    with pytest.raises(ValueError, match="between 60 and 300"):
        render_demo_video(
            output_path=Path("unused-too-long.mp4"),
            audit_bundle=sample["audit_bundle"],
            probe_report=sample["probe_report"],
            duration_seconds=360,
            fps=4,
        )


def test_render_demo_video_outputs_1080p_mp4_with_scene_progression(tmp_path: Path) -> None:
    sample = _sample_payload()
    out_mp4 = tmp_path / "cortensor_demo.mp4"

    result = render_demo_video(
        output_path=out_mp4,
        audit_bundle=sample["audit_bundle"],
        probe_report=sample["probe_report"],
        duration_seconds=60,
        fps=1,
    )

    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 10_000
    assert result.width == 1920
    assert result.height == 1080
    assert result.duration_seconds == pytest.approx(60.0)
    assert result.scene_count == 7

    reader = imageio.get_reader(out_mp4, format="ffmpeg")
    try:
        frames = [frame for frame in reader]
    finally:
        reader.close()

    assert len(frames) == 60
    first = frames[0]
    last = frames[-1]
    assert first.shape == (1080, 1920, 3)
    assert last.shape == (1080, 1920, 3)
    assert float(first.std()) > 10.0
    assert float(last.std()) > 10.0
    assert not (first == last).all()


def test_render_demo_video_fails_closed_on_plaintext_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_token = "sk-demo-forbidden-leak-99887766"
    monkeypatch.setenv("OPENAI_API_KEY", secret_token)
    sample = _sample_payload()
    sample["audit_bundle"]["consensus"]["disagreement_summary"] = (
        f"Accidental secret bearer {secret_token} should block video rendering."
    )

    with pytest.raises(ValueError, match="unredacted"):
        render_demo_video(
            output_path=tmp_path / "blocked.mp4",
            audit_bundle=sample["audit_bundle"],
            probe_report=sample["probe_report"],
            duration_seconds=60,
            fps=1,
            secret_env_names=["OPENAI_API_KEY"],
        )


def test_cli_render_demo_works_across_external_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    out_mp4 = tmp_path / "cli_demo.mp4"
    external_dir = tmp_path / "elsewhere"
    external_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(external_dir)

    rc = main(
        [
            "render-demo",
            "-o",
            str(out_mp4),
            "--duration-seconds",
            "60",
            "--fps",
            "1",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["width"] == 1920
    assert payload["height"] == 1080
    assert payload["scene_count"] == 7
    assert out_mp4.exists() and out_mp4.stat().st_size > 10_000


def test_demo_renderer_wraps_all_scene_captions_within_card_bounds() -> None:
    sample = _sample_payload()
    fonts = _create_fonts()
    assert len(_SCENE_CAPTIONS) == TOTAL_SCENES

    for scene_idx in range(TOTAL_SCENES):
        canvas = _render_scene_canvas(
            scene_idx,
            fonts=fonts,
            audit=sample["audit_bundle"],
            probe=sample["probe_report"],
        )
        arr = np.asarray(canvas)

        # Caption card box is (56, 916, DEMO_WIDTH - 56, 996); text must stay inside x in [76, 1840]
        # and y in [919, 993]. Bright text (#E2E8F0) has max RGB >> 110 (border #334155 is <= 85).
        right_overflow = arr[920:993, DEMO_WIDTH - 80 + 1 :, :].max(axis=2) > 110
        assert not right_overflow.any(), (
            f"Scene {scene_idx + 1} caption overflowed right margin x={DEMO_WIDTH - 80} "
            f"(caption={_SCENE_CAPTIONS[scene_idx]!r})"
        )

        left_overflow = arr[920:993, 60:76, :].max(axis=2) > 110
        assert not left_overflow.any(), f"Scene {scene_idx + 1} caption overflowed left margin."

        bottom_overflow = arr[997:1011, 56 : DEMO_WIDTH - 56, :].max(axis=2) > 90
        assert not bottom_overflow.any(), f"Scene {scene_idx + 1} caption overflowed below y=996."

        # Also ensure upper visualization cards never bleed into the y=697..709 gap above the console.
        upper_gap_bleed = arr[698:709, 56 : DEMO_WIDTH - 56, :].max(axis=2) > 90
        assert not upper_gap_bleed.any(), f"Scene {scene_idx + 1} upper panel bled past y=696."

    # Verify _fit_caption_lines wraps overly long captions to <= 2 lines within max_width.
    probe_draw = ImageDraw.Draw(Image.new("RGB", (DEMO_WIDTH, DEMO_HEIGHT), "#0A0F1C"))
    long_caption = " ".join(["cortensor-openminion-verifier"] * 12)
    wrapped = _fit_caption_lines(
        probe_draw,
        long_caption,
        fonts.small,
        max_width=DEMO_WIDTH - 160,
        max_lines=2,
    )
    assert len(wrapped) == 2
    assert all(probe_draw.textlength(line, font=fonts.small) <= DEMO_WIDTH - 160 for line in wrapped)



def test_demo_renderer_animates_live_terminal_execution_within_scene(tmp_path: Path) -> None:
    sample = _sample_payload()
    out_mp4 = tmp_path / "live_terminal_demo.mp4"

    result = render_demo_video(
        output_path=out_mp4,
        audit_bundle=sample["audit_bundle"],
        probe_report=sample["probe_report"],
        duration_seconds=70,
        fps=2,
    )
    assert result.frame_count == 140

    reader = imageio.get_reader(out_mp4, format="ffmpeg")
    try:
        frames = [frame for frame in reader]
    finally:
        reader.close()
    assert len(frames) == 140

    # Scene frame windows for duration=70, fps=2 (140 frames total):
    # Scene 1 (idx 0): 0..13, Scene 2 (idx 1): 14..31, Scene 3 (idx 2): 32..53, Scene 7 (idx 6): 119..139
    intra_scene_pairs = [
        ("scene_1", 0, 12),
        ("scene_2", 14, 28),
        ("scene_3", 32, 52),
        ("scene_7", 119, 138),
    ]
    for label, early_idx, late_idx in intra_scene_pairs:
        early_canvas = frames[early_idx][:900, :, :].astype(np.int16)
        late_canvas = frames[late_idx][:900, :, :].astype(np.int16)
        canvas_diff = int(np.sum(np.abs(early_canvas - late_canvas).max(axis=2) > 20))
        assert canvas_diff > 1500, (
            f"{label} frames {early_idx} vs {late_idx} lacked intra-scene animation "
            f"(changed_pixels={canvas_diff})"
        )

        early_console = frames[early_idx][710:896, 56 : DEMO_WIDTH - 56, :].astype(np.int16)
        late_console = frames[late_idx][710:896, 56 : DEMO_WIDTH - 56, :].astype(np.int16)
        console_diff = int(np.sum(np.abs(early_console - late_console).max(axis=2) > 20))
        assert console_diff > 500, (
            f"{label} frames {early_idx} vs {late_idx} lacked Live Terminal Console streaming "
            f"(console_changed_pixels={console_diff})"
        )

        # Verify both indices actually belong to the same scene (same caption bar).
        early_cap = frames[early_idx][922:990, 80 : DEMO_WIDTH - 80, :].astype(np.int16)
        late_cap = frames[late_idx][922:990, 80 : DEMO_WIDTH - 80, :].astype(np.int16)
        cap_diff = int(np.sum(np.abs(early_cap - late_cap).max(axis=2) > 30))
        assert cap_diff < 50, f"{label} frames {early_idx} vs {late_idx} crossed a scene boundary!"

        # Verify footer progress timer aligns cleanly within right margin x <= DEMO_WIDTH - 50.
        footer_right = frames[late_idx][1012:, DEMO_WIDTH - 50 :, :]
        assert footer_right.max() < 60, f"{label} footer timer overflowed right margin x={DEMO_WIDTH - 50}."

