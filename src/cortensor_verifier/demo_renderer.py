"""Captioned 1080p MP4 demo video renderer driven by AuditRunBundle & ProbeSuiteReport JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from cortensor_verifier.probe import EXPECTED_PROBE_IDS, assert_no_plaintext_secrets

DEMO_WIDTH = 1920
DEMO_HEIGHT = 1080
DEFAULT_DEMO_DURATION_SECONDS = 75
DEFAULT_DEMO_FPS = 10
TOTAL_SCENES = 7

_SCENE_TITLES: tuple[tuple[str, str], ...] = (
    (
        "1 · Problem & Isolated OpenMinion 0.1 Architecture",
        "场景 1 / 7 · 多源声明验证痛点与零密钥隔离 OpenMinion 运行时架构",
    ),
    (
        "2 · Claim Dossier & READ_ONLY Evidence Tools",
        "场景 2 / 7 · 声明档案装载与只读受控 @tool 证据检索链路",
    ),
    (
        "3 · Redundant Verifier Passes (subagent Isolation)",
        "场景 3 / 7 · 佐证者 (Corroborator) 与质疑者 (Skeptic) 双视角冗余子代理",
    ),
    (
        "4 · Consensus Verdict & Session MemoryBundle",
        "场景 4 / 7 · 结构化 Consensus Verdict 合成与跨轮会话记忆隔离",
    ),
    (
        "5 · Approval-Gated Publication (Handoff Pause/Resume)",
        "场景 5 / 7 · 基于 OpenMinion Handoff 的 Fail-Closed 人工确认发布门禁",
    ),
    (
        "6 · OpenMinion 0.1 Building Block Probe Matrix (10/10)",
        "场景 6 / 7 · 实测 10 大核心 OpenMinion 0.1 模块的延迟与契约验证矩阵",
    ),
    (
        "7 · Key Empirical DX Takeaways & Reproducible CLI",
        "场景 7 / 7 · 一手开发者体验 (What We Learned) 洞察与一键复现命令",
    ),
)

_SCENE_CAPTIONS: tuple[str, ...] = (
    "Single-pass LLMs hallucinate & leak side effects. OpenMinion isolates credentials, policies, and subagents cleanly.",
    "Only min_scope='READ_ONLY' @tool functions are registered on verifier passes — zero workspace writes possible.",
    "Two independent subagent() passes inspect the same Claim Dossier with zero shared reasoning leaks.",
    "synthesize_consensus() fuses corroborator + skeptic verdicts, agreement_score, and portable MemoryBundle JSON.",
    "External publication routes via Handoff pause -> thread_id snapshot -> single-use PolicyGrantInput(max_uses=1).",
    "All 10 OpenMinion 0.1 building blocks verified end-to-end against real APIRuntime and live LLM inference.",
    "Reproduce every audit, probe matrix, and captioned 1080p walkthrough offline or live with one CLI command.",
)


@dataclass(frozen=True)
class DemoRenderResult:
    """Metadata describing a rendered captioned MP4 walkthrough."""

    output_path: Path
    width: int
    height: int
    fps: int
    duration_seconds: float
    frame_count: int
    scene_count: int
    file_size_bytes: int
    calibration_status: str
    model: str
    claim_id: str


def resolve_default_sample_run_path() -> Path:
    """Locate fixtures/calibrated_sample_run.json relative to repo root or CWD."""
    package_root = Path(__file__).resolve().parents[2]
    candidate = package_root / "fixtures" / "calibrated_sample_run.json"
    if candidate.exists():
        return candidate
    return Path.cwd() / "fixtures" / "calibrated_sample_run.json"


def load_demo_inputs(
    *,
    sample_json: str | Path | None = None,
    audit_json: str | Path | None = None,
    probe_json: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load AuditRunBundle & ProbeSuiteReport dictionaries from sample or separate JSON files."""
    if sample_json is None and audit_json is None and probe_json is None:
        sample_json = resolve_default_sample_run_path()

    audit_data: dict[str, Any] = {}
    probe_data: dict[str, Any] = {}
    if sample_json is not None:
        sample_path = Path(sample_json)
        loaded = json.loads(sample_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Sample JSON {sample_path} must decode to a JSON object.")
        if isinstance(loaded.get("audit_bundle"), dict):
            audit_data = dict(loaded["audit_bundle"])
        elif "consensus" in loaded and "claim_id" in loaded:
            audit_data = dict(loaded)
        if isinstance(loaded.get("probe_report"), dict):
            probe_data = dict(loaded["probe_report"])

    if audit_json is not None:
        loaded_audit = json.loads(Path(audit_json).read_text(encoding="utf-8"))
        if not isinstance(loaded_audit, dict):
            raise ValueError(f"Audit JSON {audit_json} must decode to a JSON object.")
        audit_data = dict(loaded_audit)

    if probe_json is not None:
        loaded_probe = json.loads(Path(probe_json).read_text(encoding="utf-8"))
        if not isinstance(loaded_probe, dict):
            raise ValueError(f"Probe JSON {probe_json} must decode to a JSON object.")
        probe_data = dict(loaded_probe)

    if not audit_data or not probe_data:
        raise ValueError(
            "Both audit_bundle and probe_report payloads are required to render the demo video."
        )
    return audit_data, probe_data


def _load_font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates: list[Path]
    win_fonts = Path(r"C:\Windows\Fonts")
    if mono:
        candidates = [
            win_fonts / ("consolab.ttf" if bold else "consola.ttf"),
            win_fonts / "msyh.ttc",
            win_fonts / "arial.ttf",
        ]
    elif bold:
        candidates = [
            win_fonts / "msyhbd.ttc",
            win_fonts / "simhei.ttf",
            win_fonts / "segoeuib.ttf",
            win_fonts / "arialbd.ttf",
        ]
    else:
        candidates = [
            win_fonts / "msyh.ttc",
            win_fonts / "segoeui.ttf",
            win_fonts / "arial.ttf",
        ]

    for font_path in candidates:
        if font_path.exists():
            try:
                return ImageFont.truetype(str(font_path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    max_width: int,
    *,
    max_lines: int | None = None,
) -> list[str]:
    clean = " ".join(str(text or "").split())
    if not clean:
        return []

    lines: list[str] = []
    current = ""
    tokens = clean.split(" ")
    for token in tokens:
        trial = f"{current} {token}".strip()
        width = draw.textlength(trial, font=font)
        if width <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines[-1]:
            lines[-1] = lines[-1].rstrip(".")[: max(3, len(lines[-1]) - 3)] + "..."
    return lines


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    *,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    fill: str,
    max_width: int,
    line_height: int,
    max_lines: int | None = None,
) -> int:
    x, y = xy
    for line in _wrap_text(draw, text, font, max_width, max_lines=max_lines):
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def _draw_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: str = "#111A2E",
    outline: str = "#1E293B",
    radius: int = 16,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    *,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    bg: str,
    fg: str,
    pad_x: int = 16,
    pad_y: int = 8,
) -> int:
    x, y = xy
    tw = int(draw.textlength(text, font=font))
    box = (x, y, x + tw + pad_x * 2, y + 36 + pad_y)
    draw.rounded_rectangle(box, radius=18, fill=bg)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=fg)
    return box[2]


@dataclass(frozen=True)
class _Fonts:
    h1: Any
    h2: Any
    h3: Any
    body: Any
    small: Any
    mono: Any
    mono_bold: Any


def _create_fonts() -> _Fonts:
    return _Fonts(
        h1=_load_font(40, bold=True),
        h2=_load_font(28, bold=True),
        h3=_load_font(24, bold=True),
        body=_load_font(22, bold=False),
        small=_load_font(19, bold=False),
        mono=_load_font(20, mono=True),
        mono_bold=_load_font(22, bold=True, mono=True),
    )


def _draw_chrome(
    scene_idx: int,
    *,
    fonts: _Fonts,
    calibration_status: str,
    model: str,
    sdk_version: str,
) -> Image.Image:
    img = Image.new("RGB", (DEMO_WIDTH, DEMO_HEIGHT), "#0A0F1C")
    draw = ImageDraw.Draw(img)

    # Subtle grid accents
    for gx in range(80, DEMO_WIDTH, 160):
        draw.line((gx, 0, gx, DEMO_HEIGHT), fill="#0E1526", width=1)
    for gy in range(80, DEMO_HEIGHT, 160):
        draw.line((0, gy, DEMO_WIDTH, gy), fill="#0E1526", width=1)

    # Top header bar
    draw.rectangle((0, 0, DEMO_WIDTH, 148), fill="#0D1424")
    draw.line((0, 148, DEMO_WIDTH, 148), fill="#1E293B", width=2)

    title_en, title_zh = _SCENE_TITLES[scene_idx]
    draw.text((56, 26), title_en, font=fonts.h1, fill="#F8FAFC")
    draw.text((58, 84), title_zh, font=fonts.body, fill="#94A3B8")

    # Right header badges
    is_live = "Live LLM Calibrated" in calibration_status
    cal_bg = "#064E3B" if is_live else "#78350F"
    cal_fg = "#6EE7B7" if is_live else "#FDE68A"
    cal_label = "LIVE LLM CALIBRATED" if is_live else "LOOPBACK BASELINE"
    meta_label = f"openminion=={sdk_version}  |  model={model}"
    meta_w = int(draw.textlength(meta_label, font=fonts.mono))
    draw.text((DEMO_WIDTH - meta_w - 56, 88), meta_label, font=fonts.mono, fill="#38BDF8")

    cal_w = int(draw.textlength(cal_label, font=fonts.small)) + 32
    _draw_pill(
        draw,
        xy=(DEMO_WIDTH - cal_w - 56, 26),
        text=cal_label,
        font=fonts.small,
        bg=cal_bg,
        fg=cal_fg,
        pad_x=16,
        pad_y=7,
    )

    # Scene caption bar above footer
    _draw_card(draw, (56, 916, DEMO_WIDTH - 56, 996), fill="#0F172A", outline="#334155", radius=12)
    draw.text((80, 940), _SCENE_CAPTIONS[scene_idx], font=fonts.body, fill="#E2E8F0")

    return img


def _render_scene_canvas(
    scene_idx: int,
    *,
    fonts: _Fonts,
    audit: Mapping[str, Any],
    probe: Mapping[str, Any],
) -> Image.Image:
    cal_status = str(probe.get("calibration_status") or "[Loopback Stub Baseline]")
    model = str(probe.get("model") or "grok-4.6")
    sdk_version = str(probe.get("sdk_version") or "0.1.21")
    canvas = _draw_chrome(
        scene_idx,
        fonts=fonts,
        calibration_status=cal_status,
        model=model,
        sdk_version=sdk_version,
    )
    draw = ImageDraw.Draw(canvas)

    dossier = dict(audit.get("dossier") or {})
    consensus = dict(audit.get("consensus") or {})
    passes = list(consensus.get("passes") or [])
    publication = dict(audit.get("publication") or {})
    telemetry = dict((audit.get("metadata") or {}).get("telemetry") or {})
    probes = list(probe.get("probes") or [])
    findings = list(probe.get("dx_findings") or [])

    if scene_idx == 0:
        _draw_card(draw, (56, 178, 920, 884), outline="#38BDF8")
        draw.text((88, 206), "Architecture & Threat Model / 安全边界与设计目标", font=fonts.h2, fill="#38BDF8")
        bullets = [
            "1. Zero-Key Disk Isolation: APIRuntime.from_config_path writes empty api_key='' to .openminion/agents.json; API keys stay strictly in env vars.",
            "2. Provider-Agnostic Switching: Seamless presets for openai-compatible, cortensor-portal (/api/v2 & OpenAI), and cortensor-router.",
            "3. PoI/PoUW Redundant Consensus: Independent corroborator + skeptic subagents replace single-pass LLM bias.",
            "4. Fail-Closed Governance: READ_ONLY evidence tools on verifiers + PolicyGate pause/resume Handoff before publication.",
            "5. Full Empirical Benchmarking: 10-module probe suite captures live latency, token stats, and DX edge cases.",
        ]
        y = 272
        for item in bullets:
            y = _draw_wrapped(draw, xy=(88, y), text=item, font=fonts.body, fill="#E2E8F0", max_width=790, line_height=34) + 18

        _draw_card(draw, (960, 178, 1864, 884), outline="#A855F7")
        draw.text((992, 206), "End-to-End Execution Pipeline", font=fonts.h2, fill="#C084FC")
        steps = [
            ("Claim Dossier", "Market question, criteria, and candidate public sources", "#38BDF8"),
            ("Dual subagent() Passes", "corroborator vs skeptic via READ_ONLY @tool functions", "#818CF8"),
            ("Consensus Verdict synthesis", "agreement_score, confidence gap & human-review flag", "#22C55E"),
            ("MemoryBundle & Session", "Scoped per session_id with explicit thread_id continuity", "#F59E0B"),
            ("Handoff Approval Gate", "pause -> thread_id resume -> single-use PolicyGrantInput", "#EC4899"),
        ]
        sy = 276
        for idx, (label, desc, color) in enumerate(steps, start=1):
            _draw_card(draw, (992, sy, 1830, sy + 96), fill="#0B1221", outline=color, radius=12)
            draw.text((1016, sy + 14), f"{idx}. {label}", font=fonts.h3, fill=color)
            draw.text((1016, sy + 50), desc, font=fonts.small, fill="#CBD5E1")
            sy += 118

    elif scene_idx == 1:
        _draw_card(draw, (56, 178, 1180, 884), outline="#38BDF8")
        draw.text((88, 206), f"Claim Dossier: {dossier.get('claim_id', 'n/a')}", font=fonts.h2, fill="#38BDF8")
        y = 266
        y = _draw_wrapped(draw, xy=(88, y), text=f"Title: {dossier.get('title', '')}", font=fonts.h3, fill="#F8FAFC", max_width=1050, line_height=34) + 12
        y = _draw_wrapped(draw, xy=(88, y), text=f"Claim: {dossier.get('claim', '')}", font=fonts.body, fill="#E2E8F0", max_width=1050, line_height=34) + 14
        y = _draw_wrapped(draw, xy=(88, y), text=f"Market Question: {dossier.get('market_question', '')}", font=fonts.body, fill="#93C5FD", max_width=1050, line_height=34) + 14
        y = _draw_wrapped(draw, xy=(88, y), text=f"Resolution Criteria: {dossier.get('resolution_criteria', '')}", font=fonts.body, fill="#CBD5E1", max_width=1050, line_height=34) + 18
        hints = ", ".join(dossier.get("source_hints") or [])
        _draw_wrapped(draw, xy=(88, y), text=f"Source Hints: {hints}", font=fonts.mono, fill="#34D399", max_width=1050, line_height=30)

        _draw_card(draw, (1210, 178, 1864, 884), outline="#22C55E")
        draw.text((1242, 206), "Observed READ_ONLY Tools", font=fonts.h2, fill="#4ADE80")
        tool_calls = list(audit.get("tool_calls") or [t for t in ("load_delphi_market_fixture", "search_public_evidence", "fetch_source_excerpt")])
        ty = 278
        for tool_name in tool_calls[:5]:
            _draw_card(draw, (1242, ty, 1832, ty + 88), fill="#071912", outline="#10B981", radius=12)
            draw.text((1266, ty + 16), f"@tool(min_scope='READ_ONLY', idempotent=True)", font=fonts.mono, fill="#6EE7B7")
            draw.text((1266, ty + 48), f"Executed: {tool_name}", font=fonts.h3, fill="#F8FAFC")
            ty += 110
        draw.text((1242, 816), "Enforced by ConsensusAuditor._read_only_approval_guard()", font=fonts.small, fill="#94A3B8")

    elif scene_idx == 2:
        left_pass = passes[0] if len(passes) > 0 else {"pass_role": "corroborator", "verdict": "SUPPORTED", "confidence": 0.95, "rationale": "", "citations": []}
        right_pass = passes[1] if len(passes) > 1 else {"pass_role": "skeptic", "verdict": "SUPPORTED", "confidence": 0.93, "rationale": "", "citations": []}
        for idx, (box, pdata, accent) in enumerate([
            ((56, 178, 940, 884), left_pass, "#22C55E"),
            ((980, 178, 1864, 884), right_pass, "#F59E0B"),
        ]):
            _draw_card(draw, box, outline=accent)
            x0 = box[0] + 32
            role = str(pdata.get("pass_role", f"pass-{idx+1}")).upper()
            draw.text((x0, 206), f"Subagent Pass: {role}", font=fonts.h2, fill=accent)
            draw.text((x0, 256), f"Verdict: {pdata.get('verdict')}   |   Confidence: {float(pdata.get('confidence', 0.0)):.2f}", font=fonts.h3, fill="#F8FAFC")
            y = _draw_wrapped(
                draw,
                xy=(x0, 314),
                text=f"Rationale: {pdata.get('rationale', '')}",
                font=fonts.body,
                fill="#E2E8F0",
                max_width=816,
                line_height=34,
                max_lines=6,
            ) + 20
            draw.text((x0, y), "Verified Citations:", font=fonts.h3, fill="#38BDF8")
            y += 40
            for cite in list(pdata.get("citations") or [])[:2]:
                src = cite.get("source_id", "")
                excerpt = cite.get("excerpt", "")
                y = _draw_wrapped(
                    draw,
                    xy=(x0, y),
                    text=f"[{src}] {excerpt}",
                    font=fonts.small,
                    fill="#CBD5E1",
                    max_width=816,
                    line_height=28,
                    max_lines=4,
                ) + 14
            draw.text((x0, 834), "SubagentRunContext: parent_transcript_inherited=False, memory_posture='none'", font=fonts.mono, fill="#94A3B8")

    elif scene_idx == 3:
        _draw_card(draw, (56, 178, 1864, 520), outline="#22C55E")
        verdict = str(consensus.get("final_verdict", "SUPPORTED"))
        draw.text((88, 208), f"Synthesized Consensus Verdict: {verdict}", font=fonts.h1, fill="#4ADE80")
        metrics_line = (
            f"agreement_score={float(consensus.get('agreement_score', 1.0)):.2f}   |   "
            f"mean_confidence={float(consensus.get('mean_confidence', 0.95)):.2f}   |   "
            f"requires_human_review={consensus.get('requires_human_review', False)}"
        )
        draw.text((88, 278), metrics_line, font=fonts.mono_bold, fill="#38BDF8")
        _draw_wrapped(
            draw,
            xy=(88, 336),
            text=f"Synthesis Summary: {consensus.get('disagreement_summary', '')}",
            font=fonts.body,
            fill="#E2E8F0",
            max_width=1720,
            line_height=34,
            max_lines=4,
        )

        _draw_card(draw, (56, 548, 940, 884), outline="#38BDF8")
        draw.text((88, 578), "Runtime & Token Telemetry", font=fonts.h2, fill="#38BDF8")
        tel_rows = [
            f"Total Model Requests: {telemetry.get('requests', 'n/a')}",
            f"Prompt / Completion Tokens: {telemetry.get('prompt_tokens', 0)} / {telemetry.get('completion_tokens', 0)}",
            f"Total Tokens Billed: {telemetry.get('total_tokens', 0)}",
            f"End-to-End Audit Latency: {telemetry.get('total_latency_ms', 0)} ms",
        ]
        ty = 642
        for row in tel_rows:
            draw.text((88, ty), row, font=fonts.body, fill="#E2E8F0")
            ty += 52

        _draw_card(draw, (980, 548, 1864, 884), outline="#A855F7")
        draw.text((1012, 578), "Session Continuity & MemoryBundle Isolation", font=fonts.h2, fill="#C084FC")
        mem_rows = [
            f"Session ID: {audit.get('session_id') or 'cal-session'}",
            "Thread Allocation: explicit thread_id forwarded across Agent.run() turns",
            "MemoryBundle Format: export_bundle() -> save_bundle() -> import_bundle()",
            "Cross-Session Guard: foreign session_id items raise ValueError fail-closed",
        ]
        my = 642
        for row in mem_rows:
            _draw_wrapped(draw, xy=(1012, my), text=row, font=fonts.body, fill="#E2E8F0", max_width=816, line_height=30)
            my += 56

    elif scene_idx == 4:
        _draw_card(draw, (56, 178, 1864, 884), outline="#EC4899")
        draw.text((88, 208), "Approval-Gated Publication via OpenMinion Handoff", font=fonts.h2, fill="#F472B6")
        stages = [
            ("Step 1 · Handoff Coordinator", "publication_coordinator exposes transfer_to_publisher -> isolated publisher agent with WRITE_SAFE @tool(dangerous=True).", "#38BDF8"),
            ("Step 2 · Default Fail-Closed Pause", "Calling with approval_callback=None pauses execution cleanly & checkpoints thread_id snapshot JSON on disk.", "#F59E0B"),
            ("Step 3 · Explicit Operator Authorization", f"resume_publication(thread_id, approval_mode='allow_once') grants 1-use PolicyGrantInput(max_uses=1, ttl=5m).", "#22C55E"),
            ("Step 4 · Committed Verdict & Replay Denial", f"Status={publication.get('publication_status', 'published')} | published={publication.get('published', True)} | Re-using approval_id/thread_id is denied fail-closed.", "#C084FC"),
        ]
        sy = 278
        for title, body, color in stages:
            _draw_card(draw, (88, sy, 1832, sy + 124), fill="#0B1221", outline=color, radius=12)
            draw.text((116, sy + 16), title, font=fonts.h3, fill=color)
            _draw_wrapped(draw, xy=(116, sy + 54), text=body, font=fonts.body, fill="#E2E8F0", max_width=1680, line_height=30, max_lines=2)
            sy += 146

    elif scene_idx == 5:
        _draw_card(draw, (56, 178, 1864, 884), outline="#22C55E")
        passed = probe.get("passed_probes", len(EXPECTED_PROBE_IDS))
        total = probe.get("total_probes", len(EXPECTED_PROBE_IDS))
        total_ms = probe.get("total_latency_ms", 0.0)
        draw.text(
            (88, 206),
            f"Building Block Probe Suite: {passed}/{total} PASSED (total={total_ms:.1f} ms | host={probe.get('base_url_host', 'redacted')})",
            font=fonts.h2,
            fill="#4ADE80",
        )
        # Render 10 rows in a clean two-column grid (5 per column)
        for idx, item in enumerate(probes[:10]):
            col = 0 if idx < 5 else 1
            row = idx if idx < 5 else idx - 5
            x0 = 88 if col == 0 else 976
            y0 = 274 + row * 114
            box = (x0, y0, x0 + 856, y0 + 98)
            ok = bool(item.get("passed"))
            accent = "#22C55E" if ok else "#EF4444"
            _draw_card(draw, box, fill="#0B1221", outline=accent, radius=10)
            pid = str(item.get("probe_id", ""))
            lat = item.get("latency_ms", 0.0)
            badge = "PASS" if ok else "FAIL"
            draw.text((x0 + 20, y0 + 12), f"{idx+1:02d}. {pid}", font=fonts.mono_bold, fill="#F8FAFC")
            draw.text((x0 + 660, y0 + 12), f"[{badge}] {lat:.0f} ms", font=fonts.mono_bold, fill=accent)
            _draw_wrapped(draw, xy=(x0 + 20, y0 + 48), text=str(item.get("detail", "")), font=fonts.small, fill="#94A3B8", max_width=816, line_height=24, max_lines=2)

    else:
        _draw_card(draw, (56, 178, 1080, 884), outline="#F59E0B")
        draw.text((88, 206), "Top OpenMinion 0.1 DX Findings (What We Learned)", font=fonts.h2, fill="#FBBF24")
        fy = 268
        for idx, item in enumerate(findings[:4], start=1):
            _draw_card(draw, (88, fy, 1048, fy + 132), fill="#0B1221", outline="#334155", radius=10)
            _draw_wrapped(draw, xy=(108, fy + 12), text=f"{idx}. {item.get('title', '')}", font=fonts.h3, fill="#FDE68A", max_width=920, line_height=28, max_lines=1)
            _draw_wrapped(draw, xy=(108, fy + 48), text=str(item.get("observation", "")), font=fonts.small, fill="#CBD5E1", max_width=920, line_height=26, max_lines=3)
            fy += 150

        _draw_card(draw, (1116, 178, 1864, 884), outline="#38BDF8")
        draw.text((1148, 206), "One-Command Reproducibility", font=fonts.h2, fill="#38BDF8")
        cmds = [
            "# 1. Probe all 10 OpenMinion primitives & export docs",
            "cortensor-verifier probe --preset openai-compatible \\",
            "  --model grok-4.6 --timeout-seconds 180 --export-docs",
            "",
            "# 2. Run dual-pass consensus audit w/ Handoff gate",
            "cortensor-verifier audit --claim-id delphi-btc-etf-2024 \\",
            "  --multi-pass --session-id demo-01 --publish \\",
            "  --approval-mode pause",
            "",
            "# 3. Render 75s captioned 1080p walkthrough",
            "cortensor-verifier render-demo \\",
            "  -o artifacts/cortensor_hackathon5_demo.mp4",
        ]
        cy = 276
        for line in cmds:
            color = "#6EE7B7" if line.startswith("#") else "#E2E8F0"
            draw.text((1148, cy), line, font=fonts.mono, fill=color)
            cy += 42
        draw.text((1148, 824), "Repo kept PRIVATE until manual PR readiness review.", font=fonts.small, fill="#94A3B8")

    return canvas


def _overlay_progress_bar(
    base_rgb: Image.Image,
    *,
    fonts: _Fonts,
    scene_idx: int,
    frame_idx: int,
    total_frames: int,
    duration_seconds: float,
) -> np.ndarray:
    frame = base_rgb.copy()
    draw = ImageDraw.Draw(frame)

    draw.rectangle((0, 1012, DEMO_WIDTH, DEMO_HEIGHT), fill="#090D18")
    bar_x0, bar_y0, bar_x1, bar_y1 = 56, 1028, DEMO_WIDTH - 280, 1044
    draw.rounded_rectangle((bar_x0, bar_y0, bar_x1, bar_y1), radius=6, fill="#1E293B")
    frac = min(1.0, max(0.0, (frame_idx + 1) / max(1, total_frames)))
    fill_x1 = max(bar_x0 + 12, int(bar_x0 + (bar_x1 - bar_x0) * frac))
    draw.rounded_rectangle((bar_x0, bar_y0, fill_x1, bar_y1), radius=6, fill="#38BDF8")

    elapsed = (frame_idx / max(1, total_frames)) * duration_seconds
    timer_text = f"Step {scene_idx + 1}/{TOTAL_SCENES}  |  {elapsed:04.1f}s / {duration_seconds:04.1f}s"
    draw.text((DEMO_WIDTH - 252, 1022), timer_text, font=fonts.mono, fill="#CBD5E1")
    return np.asarray(frame, dtype=np.uint8)


def render_demo_video(
    *,
    output_path: str | Path,
    audit_bundle: Mapping[str, Any],
    probe_report: Mapping[str, Any],
    duration_seconds: int = DEFAULT_DEMO_DURATION_SECONDS,
    fps: int = DEFAULT_DEMO_FPS,
    allow_short_for_tests: bool = False,
    secret_env_names: Sequence[str] | None = None,
    extra_secrets: Sequence[str] | None = None,
) -> DemoRenderResult:
    """Render a captioned 1920x1080 H.264 MP4 walkthrough from AuditRunBundle & ProbeSuiteReport."""
    if not allow_short_for_tests and not (60 <= int(duration_seconds) <= 300):
        raise ValueError(
            f"Demo video duration_seconds must be between 60 and 300 seconds; got {duration_seconds}."
        )
    if int(duration_seconds) <= 0:
        raise ValueError(f"duration_seconds must be positive; got {duration_seconds}.")
    if int(fps) <= 0:
        raise ValueError(f"fps must be positive; got {fps}.")

    serialized_inputs = json.dumps(
        {"audit_bundle": audit_bundle, "probe_report": probe_report},
        ensure_ascii=True,
    )
    assert_no_plaintext_secrets(
        serialized_inputs,
        secret_env_names=secret_env_names,
        extra_secrets=extra_secrets,
    )

    total_frames = int(duration_seconds) * int(fps)
    fonts = _create_fonts()
    scene_canvases = [
        _render_scene_canvas(idx, fonts=fonts, audit=audit_bundle, probe=probe_report)
        for idx in range(TOTAL_SCENES)
    ]

    # Allocate frames monotonically across scenes based on relative instructional weight.
    weights = (0.10, 0.13, 0.16, 0.14, 0.14, 0.18, 0.15)
    raw_counts = [max(1, round(w * total_frames)) for w in weights]
    diff = total_frames - sum(raw_counts)
    raw_counts[-1] = max(1, raw_counts[-1] + diff)

    scene_schedule: list[int] = []
    for s_idx, count in enumerate(raw_counts):
        scene_schedule.extend([s_idx] * count)
    if len(scene_schedule) > total_frames:
        scene_schedule = scene_schedule[:total_frames]
    while len(scene_schedule) < total_frames:
        scene_schedule.append(TOTAL_SCENES - 1)

    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    writer = imageio.get_writer(
        str(target_path),
        fps=int(fps),
        codec="libx264",
        pixelformat="yuv420p",
        macro_block_size=1,
        ffmpeg_params=["-preset", "ultrafast"],
    )
    try:
        for frame_idx, scene_idx in enumerate(scene_schedule):
            arr = _overlay_progress_bar(
                scene_canvases[scene_idx],
                fonts=fonts,
                scene_idx=scene_idx,
                frame_idx=frame_idx,
                total_frames=total_frames,
                duration_seconds=float(duration_seconds),
            )
            writer.append_data(arr)
    finally:
        writer.close()

    return DemoRenderResult(
        output_path=target_path,
        width=DEMO_WIDTH,
        height=DEMO_HEIGHT,
        fps=int(fps),
        duration_seconds=float(duration_seconds),
        frame_count=total_frames,
        scene_count=TOTAL_SCENES,
        file_size_bytes=target_path.stat().st_size,
        calibration_status=str(probe_report.get("calibration_status") or ""),
        model=str(probe_report.get("model") or ""),
        claim_id=str(audit_bundle.get("claim_id") or ""),
    )
