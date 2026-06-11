"""
Backtest: would the AI filter's risk rules have blocked your past deals?

For each historical deal entry, this script downloads the hourly Binance candles
for the period BEFORE the entry, applies the same risk rules the live filter
uses, and reports the verdict. Then it compares outcomes:
deals that would have been ALLOWED vs deals that would have been BLOCKED.

How to run (Railway):  open your service -> Console tab -> type:
    python backtest.py
"""

import time
from datetime import datetime, timezone

import httpx

# ----------------------- Your deal history (bot 16840306) -----------------------
# entry times are treated as UTC (3commas exports use UTC).
# profit_usd for the 2 still-open deals = unrealized P/L at export time.

DEALS = [
    {"symbol": "VIRTUALUSDT", "entry": "2026-05-07 14:32:52", "status": "completed", "profit_usd": 0.66,   "duration_h": 9.2,  "so_used": 1},
    {"symbol": "TAOUSDT",     "entry": "2026-05-11 03:34:36", "status": "completed", "profit_usd": 0.26,   "duration_h": 1.9,  "so_used": 0},
    {"symbol": "DASHUSDT",    "entry": "2026-05-12 01:33:12", "status": "completed", "profit_usd": 0.67,   "duration_h": 18.1, "so_used": 1},
    {"symbol": "DASHUSDT",    "entry": "2026-05-13 12:38:15", "status": "completed", "profit_usd": 1.28,   "duration_h": 25.1, "so_used": 2},
    {"symbol": "TAOUSDT",     "entry": "2026-05-13 13:46:24", "status": "completed", "profit_usd": 0.67,   "duration_h": 23.6, "so_used": 1},
    {"symbol": "DASHUSDT",    "entry": "2026-05-21 10:39:37", "status": "completed", "profit_usd": 0.26,   "duration_h": 6.4,  "so_used": 0},
    {"symbol": "DASHUSDT",    "entry": "2026-05-22 09:33:48", "status": "completed", "profit_usd": 3.55,   "duration_h": 15.8, "so_used": 4},
    {"symbol": "VIRTUALUSDT", "entry": "2026-05-26 12:05:53", "status": "completed", "profit_usd": 0.68,   "duration_h": 2.1,  "so_used": 1},
    {"symbol": "TAOUSDT",     "entry": "2026-05-26 13:22:28", "status": "completed", "profit_usd": 0.27,   "duration_h": 1.0,  "so_used": 0},
    {"symbol": "VIRTUALUSDT", "entry": "2026-05-27 02:17:43", "status": "completed", "profit_usd": 0.68,   "duration_h": 3.2,  "so_used": 1},
    {"symbol": "TAOUSDT",     "entry": "2026-05-27 18:13:20", "status": "STUCK",     "profit_usd": -84.12, "duration_h": None, "so_used": 8},
    {"symbol": "DASHUSDT",    "entry": "2026-05-28 04:03:35", "status": "completed", "profit_usd": 1.30,   "duration_h": 12.6, "so_used": 2},
    {"symbol": "XLMUSDT",     "entry": "2026-05-28 18:50:25", "status": "completed", "profit_usd": 0.70,   "duration_h": 0.4,  "so_used": 1},
    {"symbol": "XLMUSDT",     "entry": "2026-05-28 20:10:04", "status": "completed", "profit_usd": 0.27,   "duration_h": 0.2,  "so_used": 0},
    {"symbol": "XLMUSDT",     "entry": "2026-05-28 22:44:10", "status": "completed", "profit_usd": 0.28,   "duration_h": 0.2,  "so_used": 0},
    {"symbol": "XLMUSDT",     "entry": "2026-05-29 00:45:49", "status": "completed", "profit_usd": 0.68,   "duration_h": 2.7,  "so_used": 1},
    {"symbol": "XLMUSDT",     "entry": "2026-05-29 06:11:00", "status": "completed", "profit_usd": 0.69,   "duration_h": 1.1,  "so_used": 1},
    {"symbol": "XLMUSDT",     "entry": "2026-05-29 09:10:06", "status": "completed", "profit_usd": 3.65,   "duration_h": 6.1,  "so_used": 4},
    {"symbol": "XLMUSDT",     "entry": "2026-05-29 16:17:28", "status": "completed", "profit_usd": 0.71,   "duration_h": 1.8,  "so_used": 1},
    {"symbol": "XLMUSDT",     "entry": "2026-05-29 20:15:16", "status": "completed", "profit_usd": 0.69,   "duration_h": 0.4,  "so_used": 1},
    {"symbol": "ALGOUSDT",    "entry": "2026-05-30 01:49:03", "status": "completed", "profit_usd": 0.28,   "duration_h": 0.2,  "so_used": 0},
    {"symbol": "ALGOUSDT",    "entry": "2026-05-30 02:43:02", "status": "completed", "profit_usd": 1.32,   "duration_h": 1.3,  "so_used": 2},
    {"symbol": "ALGOUSDT",    "entry": "2026-05-30 04:31:27", "status": "completed", "profit_usd": 2.28,   "duration_h": 9.7,  "so_used": 3},
    {"symbol": "ALGOUSDT",    "entry": "2026-05-30 18:01:17", "status": "completed", "profit_usd": 2.29,   "duration_h": 12.3, "so_used": 3},
    {"symbol": "ADAUSDT",     "entry": "2026-06-02 12:17:44", "status": "STUCK",     "profit_usd": -76.03, "duration_h": None, "so_used": 8},
]

# ----------------------- Risk rules (mirror of the live filter) -----------------------

DUMP_THRESHOLD_PCT = -8.0      # block if 24h price change worse than this
RED_STREAK_CANDLES = 4         # block if this many consecutive red hourly candles...
RED_STREAK_MIN_DROP_PCT = 2.5  # ...with at least this combined drop
LOW_VOLUME_RATIO = 0.5         # block if last-24h volume < 50% of prior-7-day average


def fetch_candles_before(symbol: str, entry_dt: datetime, hours: int = 192) -> list:
    """Hourly klines ENDING at the entry moment (8 days back). Returns oldest-first."""
    end_ms = int(entry_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    r = httpx.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": symbol, "interval": "1h", "endTime": end_ms, "limit": hours},
        timeout=20,
    )
    r.raise_for_status()
    return [
        {"open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
         "close": float(c[4]), "quote_vol": float(c[7])}
        for c in r.json()
    ]


def apply_rules(candles: list) -> tuple[str, str]:
    """Returns (verdict, reason). Needs >= 48 candles; uses last 24 as 'the day before entry'."""
    if len(candles) < 48:
        return "enter", "insufficient history to judge - allowed by default"

    last24 = candles[-24:]
    baseline = candles[:-24]

    # Rule 1: 24h dump
    change_24h = (last24[-1]["close"] - last24[0]["open"]) / last24[0]["open"] * 100
    if change_24h <= DUMP_THRESHOLD_PCT:
        return "skip", f"24h dump: {change_24h:.1f}% (threshold {DUMP_THRESHOLD_PCT}%)"

    # Rule 2: accelerating red streak
    streak = last24[-RED_STREAK_CANDLES:]
    all_red = all(c["close"] < c["open"] for c in streak)
    streak_drop = (streak[-1]["close"] - streak[0]["open"]) / streak[0]["open"] * 100
    if all_red and streak_drop <= -RED_STREAK_MIN_DROP_PCT:
        return "skip", f"last {RED_STREAK_CANDLES}h all red, {streak_drop:.1f}% combined"

    # Rule 3: abnormally low volume
    vol_24h = sum(c["quote_vol"] for c in last24)
    baseline_avg_24h = sum(c["quote_vol"] for c in baseline) / len(baseline) * 24
    if baseline_avg_24h > 0 and vol_24h < LOW_VOLUME_RATIO * baseline_avg_24h:
        ratio = vol_24h / baseline_avg_24h * 100
        return "skip", f"volume only {ratio:.0f}% of 7-day average"

    return "enter", f"normal conditions (24h: {change_24h:+.1f}%)"


def main():
    allowed, blocked, errors = [], [], []

    print(f"{'PAIR':<13}{'ENTRY (UTC)':<21}{'VERDICT':<9}{'OUTCOME':<12}{'P/L':>9}   REASON")
    print("-" * 100)

    for d in DEALS:
        entry_dt = datetime.strptime(d["entry"], "%Y-%m-%d %H:%M:%S")
        try:
            candles = fetch_candles_before(d["symbol"], entry_dt)
            verdict, reason = apply_rules(candles)
        except Exception as e:
            verdict, reason = "error", str(e)[:60]
            errors.append(d)

        outcome = "STUCK OPEN" if d["status"] == "STUCK" else f"closed {d['duration_h']}h"
        print(f"{d['symbol']:<13}{d['entry']:<21}{verdict.upper():<9}{outcome:<12}"
              f"{d['profit_usd']:>8.2f}$   {reason}")

        if verdict == "skip":
            blocked.append(d)
        elif verdict == "enter":
            allowed.append(d)
        time.sleep(0.3)  # be polite to Binance API

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    for name, group in (("ALLOWED by filter", allowed), ("BLOCKED by filter", blocked)):
        if not group:
            print(f"\n{name}: none")
            continue
        total = sum(d["profit_usd"] for d in group)
        stuck = [d for d in group if d["status"] == "STUCK"]
        wins = [d for d in group if d["status"] == "completed"]
        avg_so = sum(d["so_used"] for d in group) / len(group)
        print(f"\n{name}: {len(group)} deals")
        print(f"  total P/L: {total:+.2f}$   (completed: {len(wins)}, stuck open: {len(stuck)})")
        print(f"  avg safety orders used: {avg_so:.1f}")
        if stuck:
            for d in stuck:
                print(f"  >> stuck deal in this group: {d['symbol']} {d['entry']} ({d['profit_usd']:.2f}$)")

    if errors:
        print(f"\nNote: {len(errors)} deals could not be checked (data errors above).")

    print("\nInterpretation guide:")
    print("- The filter earns its place if the BLOCKED group contains the stuck/worst deals")
    print("  while the ALLOWED group keeps most of the profitable ones.")
    print("- If the BLOCKED group is mostly normal winners, the rules are too strict: relax them.")
    print("- If the stuck deals were ALLOWED, the rules are too loose or wrong: tighten/change them.")
    print("- Reminder: the live filter uses Claude's judgment with these rules as guidance,")
    print("  so live verdicts may be slightly more lenient/contextual than this strict replay.")


if __name__ == "__main__":
    main()
