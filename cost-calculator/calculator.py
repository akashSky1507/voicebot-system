#!/usr/bin/env python3
"""
Voicebot cost calculator (CLI version of cost-calculator/index.html)

Computes monthly cost for the STT -> LLM -> TTS pipeline, per provider and
per full-stack preset, from the traffic assumptions and pricing table in
config.yaml.

Usage:
    pip install -r requirements.txt
    python calculator.py                # uses config.yaml in this folder
    python calculator.py --currency inr
    python calculator.py --config my_config.yaml
    python calculator.py --calls 100000 --minutes 4   # override a few inputs ad hoc
"""

import argparse
import sys
from pathlib import Path

import yaml


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fmt_money(usd: float, currency: str, fx: float) -> str:
    if currency == "usd":
        return f"${usd:,.2f}"
    return f"₹{usd * fx:,.0f}"


def fmt_rate(usd: float, currency: str, fx: float, decimals: int = 4) -> str:
    if currency == "usd":
        return f"${usd:.{decimals}f}"
    return f"₹{usd * fx:.{decimals}f}"


def compute_stage_costs(cfg: dict):
    """Mirrors the compute() function in cost-calculator/index.html."""
    i = cfg["inputs"]
    monthly_minutes = i["monthly_calls"] * i["avg_call_minutes"]
    monthly_turns = i["monthly_calls"] * i["avg_turns_per_call"]
    monthly_tok_in = monthly_turns * i["avg_input_tokens_per_turn"]
    monthly_tok_out = monthly_turns * i["avg_output_tokens_per_turn"]
    monthly_chars = i["monthly_calls"] * i["avg_tts_chars_per_call"]

    stt_costs = []
    for p in cfg["pricing"]["stt"]:
        cost = monthly_minutes * p["per_min"]
        stt_costs.append({**p, "cost": cost, "monthly_minutes": monthly_minutes})

    llm_costs = []
    for p in cfg["pricing"]["llm"]:
        cost = (monthly_tok_in / 1e6) * p["in_per_1m"] + (monthly_tok_out / 1e6) * p["out_per_1m"]
        llm_costs.append({**p, "cost": cost, "monthly_tok_in": monthly_tok_in, "monthly_tok_out": monthly_tok_out})

    tts_costs = []
    for p in cfg["pricing"]["tts"]:
        cost = (monthly_chars / 1e6) * p["per_1m"]
        tts_costs.append({**p, "cost": cost, "monthly_chars": monthly_chars})

    return {
        "monthly_minutes": monthly_minutes,
        "monthly_turns": monthly_turns,
        "monthly_tok_in": monthly_tok_in,
        "monthly_tok_out": monthly_tok_out,
        "monthly_chars": monthly_chars,
        "stt": stt_costs,
        "llm": llm_costs,
        "tts": tts_costs,
    }


def print_stage_table(title: str, rows: list, currency: str, fx: float, rate_label: str, rate_key):
    print(f"\n{title}")
    print("-" * len(title))
    live_rows = [r for r in rows if not r.get("batch_only")]
    min_cost = min(r["cost"] for r in live_rows) if live_rows else None
    rows_sorted = sorted(rows, key=lambda r: r["cost"])

    name_w = max(len(r["name"]) for r in rows_sorted) + 2
    header = f'{"Provider":<{name_w}}{rate_label:<16}{"Monthly cost":<16}Notes'
    print(header)
    for r in rows_sorted:
        badge = ""
        if r.get("batch_only"):
            badge = "[NOT LIVE-CALL SAFE] "
        elif r["cost"] == min_cost:
            badge = "[CHEAPEST] "
        rate_str = rate_key(r)
        print(f'{r["name"]:<{name_w}}{rate_str:<16}{fmt_money(r["cost"], currency, fx):<16}{badge}{r.get("note", "")}')


def print_presets(cfg: dict, data: dict, currency: str, fx: float):
    def find(rows, name):
        matches = [r for r in rows if r["name"] == name]
        if not matches:
            raise SystemExit(f"Preset references unknown provider name: {name!r}")
        return matches[0]

    print("\nFull-stack presets (monthly total)")
    print("-----------------------------------")
    totals = []
    for p in cfg["presets"]:
        stt = find(data["stt"], p["stt"])
        llm = find(data["llm"], p["llm"])
        tts = find(data["tts"], p["tts"])
        total = stt["cost"] + llm["cost"] + tts["cost"]
        totals.append((p["title"], total))
        print(f'\n{p["title"]} — {p["desc"]}')
        print(f'  STT ({stt["name"]}):  {fmt_money(stt["cost"], currency, fx)}')
        print(f'  LLM ({llm["name"]}):  {fmt_money(llm["cost"], currency, fx)}')
        print(f'  TTS ({tts["name"]}):  {fmt_money(tts["cost"], currency, fx)}')
        print(f'  TOTAL: {fmt_money(total, currency, fx)}/month')

    max_total = max(t for _, t in totals) if totals else 0
    print("\nSide-by-side (bar = share of most expensive preset)")
    for title, total in totals:
        bar_len = int((total / max_total) * 40) if max_total else 0
        print(f'  {title:<28}{"#" * bar_len:<42}{fmt_money(total, currency, fx)}')


def apply_overrides(cfg: dict, args: argparse.Namespace):
    i = cfg["inputs"]
    if args.calls is not None:
        i["monthly_calls"] = args.calls
    if args.minutes is not None:
        i["avg_call_minutes"] = args.minutes
    if args.turns is not None:
        i["avg_turns_per_call"] = args.turns


def main():
    parser = argparse.ArgumentParser(description="Voicebot STT/LLM/TTS monthly cost calculator")
    parser.add_argument("--config", default=str(Path(__file__).parent / "config.yaml"),
                         help="Path to config.yaml (default: config.yaml next to this script)")
    parser.add_argument("--currency", choices=["usd", "inr"], default="usd",
                         help="Display currency (default: usd)")
    parser.add_argument("--calls", type=int, default=None, help="Override monthly_calls")
    parser.add_argument("--minutes", type=float, default=None, help="Override avg_call_minutes")
    parser.add_argument("--turns", type=int, default=None, help="Override avg_turns_per_call")
    args = parser.parse_args()

    if not Path(args.config).exists():
        print(f"Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config(args.config)
    apply_overrides(cfg, args)
    fx = cfg["inputs"]["fx_usd_to_inr"]
    data = compute_stage_costs(cfg)

    print("=" * 60)
    print("VOICEBOT MONTHLY COST ESTIMATE")
    print("=" * 60)
    i = cfg["inputs"]
    print(f'Calls/month:        {i["monthly_calls"]:,}')
    print(f'Avg call length:    {i["avg_call_minutes"]} min')
    print(f'Turns/call:         {i["avg_turns_per_call"]}')
    print(f'Total call minutes: {data["monthly_minutes"]:,.0f}')
    print(f'Total LLM tokens:   {data["monthly_tok_in"]/1e6:.2f}M in / {data["monthly_tok_out"]/1e6:.2f}M out')
    print(f'Total TTS chars:    {data["monthly_chars"]/1e6:.2f}M')

    print_stage_table("STT / ASR — cost per provider", data["stt"], args.currency, fx,
                       "$/min", lambda r: fmt_rate(r["per_min"], args.currency, fx, 4))
    print_stage_table("LLM — cost per provider", data["llm"], args.currency, fx,
                       "$/1M in-out", lambda r: f'{fmt_rate(r["in_per_1m"], args.currency, fx, 3)}/{fmt_rate(r["out_per_1m"], args.currency, fx, 3)}')
    print_stage_table("TTS — cost per provider", data["tts"], args.currency, fx,
                       "$/1M chars", lambda r: fmt_rate(r["per_1m"], args.currency, fx, 2))

    print_presets(cfg, data, args.currency, fx)

    print("\nNote: pricing seeded from vendor pages, mid-July 2026 — re-check before budgeting a contract.")


if __name__ == "__main__":
    main()
