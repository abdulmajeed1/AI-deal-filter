"""
Backtest v2 — TAO bot (59 deals, Dec 2025 - Jun 2026), comparing TWO rulesets:

  RULESET A (original defaults): block on -8% 24h dump, 4 red candles, low volume
  RULESET B (momentum rule):     block long entries when 24h change < -2%

Run in Railway console:  python backtest2.py
"""

import time
from datetime import datetime, timezone

import httpx

SYMBOL = "TAOUSDT"

DEALS = [
    {"entry": "2025-12-15 11:42:58", "status": "completed", "profit_usd": 13.85, "duration_h": 450.0, "so_used": 8},
    {"entry": "2026-01-07 09:34:04", "status": "completed", "profit_usd": 0.49, "duration_h": 23.2, "so_used": 2},
    {"entry": "2026-01-12 08:31:38", "status": "completed", "profit_usd": 0.34, "duration_h": 7.3, "so_used": 1},
    {"entry": "2026-01-12 23:10:25", "status": "completed", "profit_usd": 0.05, "duration_h": 3.0, "so_used": 0},
    {"entry": "2026-01-16 15:29:10", "status": "completed", "profit_usd": 0.32, "duration_h": 10.9, "so_used": 0},
    {"entry": "2026-01-18 23:28:33", "status": "completed", "profit_usd": 4.17, "duration_h": 1.0, "so_used": 7},
    {"entry": "2026-01-25 14:23:20", "status": "completed", "profit_usd": 1.92, "duration_h": 18.7, "so_used": 3},
    {"entry": "2026-01-29 14:58:32", "status": "completed", "profit_usd": 0.42, "duration_h": 2.7, "so_used": 2},
    {"entry": "2026-01-29 19:23:39", "status": "completed", "profit_usd": 0.25, "duration_h": 6.3, "so_used": 0},
    {"entry": "2026-01-30 10:09:17", "status": "completed", "profit_usd": 0.17, "duration_h": 2.3, "so_used": 0},
    {"entry": "2026-01-31 08:37:09", "status": "completed", "profit_usd": 4.4, "duration_h": 10.8, "so_used": 7},
    {"entry": "2026-01-31 20:32:56", "status": "completed", "profit_usd": 0.75, "duration_h": 4.7, "so_used": 0},
    {"entry": "2026-02-01 14:39:46", "status": "completed", "profit_usd": 0.09, "duration_h": 0.4, "so_used": 0},
    {"entry": "2026-02-02 03:21:24", "status": "completed", "profit_usd": 0.67, "duration_h": 0.8, "so_used": 1},
    {"entry": "2026-02-03 17:08:08", "status": "completed", "profit_usd": 3.75, "duration_h": 3.0, "so_used": 3},
    {"entry": "2026-02-03 23:04:17", "status": "completed", "profit_usd": 0.15, "duration_h": 3.4, "so_used": 0},
    {"entry": "2026-02-04 18:09:09", "status": "completed", "profit_usd": 0.16, "duration_h": 1.2, "so_used": 0},
    {"entry": "2026-02-05 05:22:32", "status": "completed", "profit_usd": 7.71, "duration_h": 25.4, "so_used": 8},
    {"entry": "2026-02-08 23:36:29", "status": "completed", "profit_usd": 0.16, "duration_h": 6.4, "so_used": 0},
    {"entry": "2026-02-10 06:46:24", "status": "completed", "profit_usd": 2.56, "duration_h": 46.5, "so_used": 5},
    {"entry": "2026-02-14 10:04:16", "status": "completed", "profit_usd": 0.08, "duration_h": 0.3, "so_used": 0},
    {"entry": "2026-02-14 10:27:22", "status": "completed", "profit_usd": 27.93, "duration_h": 42.5, "so_used": 5},
    {"entry": "2026-02-16 07:12:47", "status": "completed", "profit_usd": 3.22, "duration_h": 3.5, "so_used": 4},
    {"entry": "2026-02-17 17:12:35", "status": "completed", "profit_usd": 0.1, "duration_h": 2.1, "so_used": 0},
    {"entry": "2026-02-18 00:46:11", "status": "completed", "profit_usd": 0.3, "duration_h": 9.0, "so_used": 0},
    {"entry": "2026-02-18 18:20:35", "status": "completed", "profit_usd": 0.22, "duration_h": 9.4, "so_used": 1},
    {"entry": "2026-02-22 20:33:44", "status": "completed", "profit_usd": 1.98, "duration_h": 16.0, "so_used": 3},
    {"entry": "2026-02-24 03:29:09", "status": "completed", "profit_usd": 2.04, "duration_h": 13.1, "so_used": 2},
    {"entry": "2026-02-26 16:34:25", "status": "completed", "profit_usd": 0.91, "duration_h": 8.1, "so_used": 1},
    {"entry": "2026-02-28 06:18:40", "status": "completed", "profit_usd": 2.24, "duration_h": 7.8, "so_used": 3},
    {"entry": "2026-03-02 07:18:25", "status": "completed", "profit_usd": 0.22, "duration_h": 6.6, "so_used": 0},
    {"entry": "2026-03-04 03:36:40", "status": "completed", "profit_usd": 1.55, "duration_h": 5.5, "so_used": 0},
    {"entry": "2026-03-06 12:03:48", "status": "completed", "profit_usd": 3.21, "duration_h": 26.1, "so_used": 3},
    {"entry": "2026-03-13 19:40:29", "status": "completed", "profit_usd": 0.23, "duration_h": 1.8, "so_used": 0},
    {"entry": "2026-03-16 02:38:44", "status": "completed", "profit_usd": 0.18, "duration_h": 1.9, "so_used": 0},
    {"entry": "2026-03-17 05:33:26", "status": "completed", "profit_usd": 0.67, "duration_h": 1.9, "so_used": 1},
    {"entry": "2026-03-17 12:45:37", "status": "completed", "profit_usd": 1.21, "duration_h": 5.8, "so_used": 1},
    {"entry": "2026-03-18 12:30:42", "status": "completed", "profit_usd": 0.94, "duration_h": 5.8, "so_used": 3},
    {"entry": "2026-03-19 03:02:44", "status": "completed", "profit_usd": 8.83, "duration_h": 18.6, "so_used": 4},
    {"entry": "2026-03-20 07:01:14", "status": "completed", "profit_usd": 0.55, "duration_h": 1.3, "so_used": 0},
    {"entry": "2026-03-21 23:52:19", "status": "completed", "profit_usd": 2.46, "duration_h": 1.7, "so_used": 2},
    {"entry": "2026-03-22 10:51:23", "status": "completed", "profit_usd": 0.29, "duration_h": 2.8, "so_used": 0},
    {"entry": "2026-03-22 18:25:36", "status": "completed", "profit_usd": 2.48, "duration_h": 10.3, "so_used": 2},
    {"entry": "2026-03-25 02:50:37", "status": "completed", "profit_usd": 0.14, "duration_h": 2.5, "so_used": 0},
    {"entry": "2026-03-25 11:44:48", "status": "completed", "profit_usd": 2.12, "duration_h": 1.7, "so_used": 2},
    {"entry": "2026-03-25 18:46:52", "status": "completed", "profit_usd": 0.15, "duration_h": 0.6, "so_used": 0},
    {"entry": "2026-03-27 05:02:09", "status": "completed", "profit_usd": 4.68, "duration_h": 10.9, "so_used": 4},
    {"entry": "2026-03-27 20:32:31", "status": "completed", "profit_usd": 1.81, "duration_h": 12.4, "so_used": 2},
    {"entry": "2026-03-28 21:57:55", "status": "completed", "profit_usd": 0.21, "duration_h": 8.6, "so_used": 0},
    {"entry": "2026-03-29 22:45:42", "status": "completed", "profit_usd": 1.02, "duration_h": 1.9, "so_used": 0},
    {"entry": "2026-03-30 17:22:04", "status": "completed", "profit_usd": 0.17, "duration_h": 5.1, "so_used": 0},
    {"entry": "2026-03-31 06:20:10", "status": "completed", "profit_usd": 1.45, "duration_h": 25.7, "so_used": 1},
    {"entry": "2026-04-09 23:46:48", "status": "completed", "profit_usd": 31.09, "duration_h": 549.4, "so_used": 8},
    {"entry": "2026-05-03 10:15:35", "status": "completed", "profit_usd": 0.76, "duration_h": 11.4, "so_used": 0},
    {"entry": "2026-05-11 03:34:39", "status": "completed", "profit_usd": 0.42, "duration_h": 3.4, "so_used": 0},
    {"entry": "2026-05-15 15:44:41", "status": "completed", "profit_usd": 5.32, "duration_h": 120.6, "so_used": 6},
    {"entry": "2026-05-22 18:45:44", "status": "completed", "profit_usd": 9.16, "duration_h": 22.3, "so_used": 5},
    {"entry": "2026-05-27 02:25:03", "status": "completed", "profit_usd": 0.42, "duration_h": 10.7, "so_used": 1},
    {"entry": "2026-06-02 09:09:44", "status": "STUCK", "profit_usd": -63.24, "duration_h": 0.0, "so_used": 8},
]

# --------------------------- data fetch ---------------------------

def fetch_candles_before(entry_dt: datetime, hours: int = 192) -> list:
    end_ms = int(entry_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    r = httpx.get(
        "https://data-api.binance.vision/api/v3/klines",
        params={"symbol": SYMBOL, "interval": "1h", "endTime": end_ms, "limit": hours},
        timeout=20,
    )
    r.raise_for_status()
    return [
        {"open": float(c[1]), "close": float(c[4]), "quote_vol": float(c[7])}
        for c in r.json()
    ]

# --------------------------- rulesets ---------------------------

def ruleset_a(candles):
    """Original defaults: -8% dump, 4-red-candle streak, low volume."""
    last24, baseline = candles[-24:], candles[:-24]
    change = (last24[-1]["close"] - last24[0]["open"]) / last24[0]["open"] * 100
    if change <= -8.0:
        return "skip", f"24h dump {change:.1f}%"
    streak = last24[-4:]
    drop = (streak[-1]["close"] - streak[0]["open"]) / streak[0]["open"] * 100
    if all(c["close"] < c["open"] for c in streak) and drop <= -2.5:
        return "skip", f"4h red streak {drop:.1f}%"
    vol = sum(c["quote_vol"] for c in last24)
    base_avg = sum(c["quote_vol"] for c in baseline) / len(baseline) * 24
    if base_avg > 0 and vol < 0.5 * base_avg:
        return "skip", f"volume {vol/base_avg*100:.0f}% of avg"
    return "enter", f"24h {change:+.1f}%"


def ruleset_b(candles):
    """Momentum rule: block long entry when 24h change below -2%."""
    last24 = candles[-24:]
    change = (last24[-1]["close"] - last24[0]["open"]) / last24[0]["open"] * 100
    if change <= -2.0:
        return "skip", f"negative 24h momentum {change:.1f}%"
    return "enter", f"24h {change:+.1f}%"

# --------------------------- run ---------------------------

def summarize(name, deals):
    groups = {"enter": [], "skip": []}
    for d in deals:
        groups[d[name]].append(d)
    out = []
    for verdict, label in (("enter", "ALLOWED"), ("skip", "BLOCKED")):
        g = groups[verdict]
        if not g:
            out.append(f"  {label}: none")
            continue
        total = sum(d["profit_usd"] for d in g)
        stuck = sum(1 for d in g if d["status"] == "STUCK")
        deep = sum(1 for d in g if d["so_used"] >= 5)
        avg_dur = sum(d["duration_h"] for d in g if d["status"] == "completed")
        ncomp = sum(1 for d in g if d["status"] == "completed")
        avg_dur = avg_dur / ncomp if ncomp else 0
        out.append(
            f"  {label}: {len(g)} deals | total P/L {total:+8.2f}$ | "
            f"stuck: {stuck} | deep-SO (>=5): {deep} | avg close time {avg_dur:.1f}h"
        )
    return "\n".join(out)


def main():
    print(f"{'ENTRY (UTC)':<21}{'OUTCOME':<14}{'P/L':>9}  {'SO':>3}  {'A-default':<26}{'B-momentum':<26}")
    print("-" * 105)
    for d in DEALS:
        entry_dt = datetime.strptime(d["entry"], "%Y-%m-%d %H:%M:%S")
        try:
            candles = fetch_candles_before(entry_dt)
            va, ra = ruleset_a(candles)
            vb, rb = ruleset_b(candles)
        except Exception as e:
            va = vb = "error"
            ra = rb = str(e)[:24]
        d["a"], d["b"] = va, vb
        outcome = "STUCK OPEN" if d["status"] == "STUCK" else f"closed {d['duration_h']}h"
        flag = " <<<" if d["status"] == "STUCK" or d["so_used"] >= 5 else ""
        print(f"{d['entry']:<21}{outcome:<14}{d['profit_usd']:>8.2f}$  {d['so_used']:>3}  "
              f"{va.upper()+': '+ra:<26}{vb.upper()+': '+rb:<26}{flag}")
        time.sleep(0.25)

    ok = [d for d in DEALS if d["a"] != "error"]
    print("\n" + "=" * 105)
    print(f"RULESET A — original defaults   ({len(ok)} deals checked)")
    print(summarize("a", ok))
    print()
    print(f"RULESET B — momentum < -2% blocks")
    print(summarize("b", ok))
    print()
    print("'<<<' marks the painful deals (stuck, or 5+ safety orders used).")
    print("The better ruleset is the one whose BLOCKED row collects the stuck/deep-SO deals")
    print("while keeping the ALLOWED row's total P/L close to the bot's full profit.")


if __name__ == "__main__":
    main()
