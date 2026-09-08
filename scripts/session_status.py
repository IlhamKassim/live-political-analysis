#!/usr/bin/env python3
"""Session and context monitoring script for Antigravity CLI sessions."""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

MODEL_CONTEXT_WINDOWS = {
    "gemini": 1_048_576,  # 1M tokens
    "claude": 200_000,    # 200k tokens
    "gpt": 128_000,       # 128k tokens
}
DEFAULT_CONTEXT_WINDOW = 1_000_000
SYSTEM_OVERHEAD_TOKENS = 15_000


def get_active_model() -> str:
    settings_path = os.path.expanduser("~/.gemini/antigravity-cli/settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path) as f:
                data = json.load(f)
                model_val = data.get("model")
                if isinstance(model_val, str):
                    return model_val
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("Failed reading settings: %s", e)
    return "Gemini 3.8 Flash"


def get_context_window(model_name: str) -> int:
    name_lower = model_name.lower()
    for key, limit in MODEL_CONTEXT_WINDOWS.items():
        if key in name_lower:
            return limit
    return DEFAULT_CONTEXT_WINDOW


def get_active_transcript() -> str | None:
    brain_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain")
    pattern = os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript_full.jsonl")
    transcripts = glob.glob(pattern)
    if not transcripts:
        return None
    transcripts.sort(key=os.path.getmtime, reverse=True)
    return transcripts[0]


def calculate_transcript_tokens(transcript_path: str) -> int:
    total_chars = 0
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                try:
                    item = json.loads(line)
                    content = item.get("content", "")
                    if content:
                        total_chars += len(content)
                    thinking = item.get("thinking", "")
                    if thinking:
                        total_chars += len(thinking)
                    tool_calls = item.get("tool_calls", [])
                    if tool_calls:
                        total_chars += len(json.dumps(tool_calls))
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.debug("Error reading transcript: %s", e)
        return SYSTEM_OVERHEAD_TOKENS
    # Roughly ~4 characters per token
    return (total_chars // 4) + SYSTEM_OVERHEAD_TOKENS


def get_cli_quota() -> dict[str, str]:
    quota_info: dict[str, str] = {}
    agy_bin = shutil.which("agy")
    if not agy_bin:
        return quota_info
    try:
        res = subprocess.run(
            [agy_bin, "--print", "/usage"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if res.returncode == 0:
            for line in res.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split("\t") if p.strip()]
                if len(parts) >= 3:
                    label = f"{parts[0]} ({parts[1]})"
                    quota_info[label] = parts[2]
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug("Error querying agy quota: %s", e)
    return quota_info


def make_bar(percentage: float, length: int = 30) -> str:
    filled = round(length * (percentage / 100.0))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


def main() -> None:
    model = get_active_model()
    window = get_context_window(model)
    transcript = get_active_transcript()
    tokens = calculate_transcript_tokens(transcript) if transcript else SYSTEM_OVERHEAD_TOKENS
    pct_used = min(100.0, (tokens / window) * 100.0)

    print("=== Antigravity Session Status ===")
    print(f"Active Model: {model} (Context Window: {window:,} tokens)")
    print(f"Context Tokens: ~{tokens:,} / {window:,} ({pct_used:.1f}% used)")
    print(f"Context Bar:    [{make_bar(pct_used)}] {pct_used:.1f}%")

    quota = get_cli_quota()
    if quota:
        print("\n=== Model Quotas Remaining ===")
        for k, v in quota.items():
            print(f"- {k}: {v}")

    # Compact single-line footer for agent messages
    print("\n=== Agent Footer Bar ===")
    gemini_5h = quota.get("Gemini Models (Five Hour Limit Remaining)", "N/A")
    gemini_wk = quota.get("Gemini Models (Weekly Limit Remaining)", "N/A")
    short_model = model.split("(")[0].strip()
    footer = f"[Context: {pct_used:.1f}% (~{tokens // 1000}k / {window // 1000}k tokens) | {short_model}]"
    if gemini_5h != "N/A":
        footer += f" [Quota Remaining: 5h: {gemini_5h} | Weekly: {gemini_wk}]"
    print(footer)


if __name__ == "__main__":
    main()
