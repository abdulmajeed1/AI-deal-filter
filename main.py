"""
AI Deal Filter — sits between TradingView and 3commas.

Flow:
  TradingView alert  -->  POST /signal (this server)
                          1. Parse the 3commas payload (untouched)
                          2. Pull live market context from Binance public API
                          3. Ask Claude: safe to enter or not? (JSON verdict)
                          4. If approved (or SHADOW_MODE) -> forward payload to 3commas
                          5. Log everything to decisions.jsonl

Setup:
  pip install fastapi uvicorn httpx
  export ANTHROPIC_API_KEY=sk-ant-...
  uvicorn main:app --host 0.0.0.0 --port 8000

Then in TradingView, change your alert's Webhook URL from
  https://app.3commas.io/trade_signal/trading_view
to
  https://YOUR-SERVER/signal
Keep the alert message (the 3commas JSON) exactly as it is.
"""

import json
import os
import re
import time
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request

# ----------------------------- Configuration -------------------------------

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Where approved signals get forwarded (3commas TradingView signal endpoint)
FORWARD_URL = os.environ.get(
    "FORWARD_URL", "https://app.3commas.io/trade_signal/trading_view"
)

# SHADOW_MODE=true  -> ALWAYS forward to 3commas, but still ask the AI and log
#                      its verdict. Use this for 1-2 weeks first to verify the
#                      AI actually blocks bad deals before letting it block real ones.
SHADOW_MODE = os.environ.get("SHADOW_MODE", "true").lower() == "true"

# Minimum confidence (0-1) the AI must report for an "enter" verdict to pass.
MIN_CONFIDENCE = float(os.environ.get("MIN_CONFIDENCE", "0.6"))

# If the AI call fails (timeout, API error), what do we do?
# "forward" = fail-open (trade goes through), "block" = fail-closed.
ON_AI_ERROR = os.environ.get("ON_AI_ERROR", "forward")

# Your own risk rules, injected into the prompt. Edit freely.
RISK_RULES = os.environ.get(
    "RISK_RULES",
    "- Block if price dropped more than 8% in the last 24h (likely knife-catching for a DCA bot)\n"
    "- Block if the last 4 hourly candles are all strongly red (accelerating downtrend)\n"
    "- Block if 24h volume is unusually low versus the average (illiquid, manipulable)\n"
    "- Prefer entries after consolidation or a stabilizing wick, not mid-freefall",
)

LOG_FILE = os.environ.get("LOG_FILE", "decisions.jsonl")

app = FastAPI()

# ----------------------------- Market context ------------------------------


def pair_to_binance_symbol(payload: dict) -> str | None:
    """
    Try to derive a Binance symbol like 'BTCUSDT' from common 3commas /
    TradingView payload fields.
    Handles: pair='USDT_BTC', tv_instrument='BTCUSDT' / 'BTCUSDT.P', ticker etc.
    """
    pair = payload.get("pair")  # classic 3commas format: QUOTE_BASE
    if pair and "_" in pair:
        quote, base = pair.split("_", 1)
        return f"{base}{quote}".upper()

    for key in ("tv_instrument", "instrument", "ticker", "symbol"):
        val = payload.get(key)
        if val:
            return re.sub(r"[^A-Z0-9]", "", str(val).upper().split(".")[0])
    return None


async def fetch_market_context(symbol: str) -> dict | None:
    """Public Binance endpoints, no API key needed. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            t24 = await client.get(
                "https://data-api.binance.vision/api/v3/ticker/24hr",
                params={"symbol": symbol},
            )
            kl = await client.get(
                "https://data-api.binance.vision/api/v3/klines",
                params={"symbol": symbol, "interval": "1h", "limit": 24},
            )
            t24.raise_for_status()
            kl.raise_for_status()
            stats = t24.json()
            candles = [
                {
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                }
                for c in kl.json()
            ]
            return {
                "symbol": symbol,
                "last_price": float(stats["lastPrice"]),
                "change_24h_pct": float(stats["priceChangePercent"]),
                "high_24h": float(stats["highPrice"]),
                "low_24h": float(stats["lowPrice"]),
                "volume_24h_quote": float(stats["quoteVolume"]),
                "hourly_candles_last_24": candles,
            }
    except Exception:
        return None


# ------------------------------- AI verdict --------------------------------

VERDICT_SYSTEM_PROMPT = """You are a risk gatekeeper for an automated crypto DCA bot.
A TradingView indicator has just fired an entry signal. Your ONLY job is to decide
whether current market conditions make this a reasonable moment for a DCA bot to
open a new deal, based on the data and rules provided. You are a safety filter,
not a signal generator: when conditions look normal, approve; block only when a
risk rule is clearly violated or conditions are clearly hostile.

Respond with ONLY a JSON object, no markdown fences, no extra text:
{"verdict": "enter" or "skip", "confidence": <0.0-1.0>, "reason": "<one short sentence>"}"""


async def get_ai_verdict(payload: dict, market: dict | None) -> dict:
    user_content = (
        f"ENTRY SIGNAL (raw TradingView/3commas payload):\n{json.dumps(payload)}\n\n"
        f"LIVE MARKET DATA:\n{json.dumps(market) if market else 'UNAVAILABLE'}\n\n"
        f"RISK RULES TO ENFORCE:\n{RISK_RULES}\n\n"
        "Decide: enter or skip?"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 300,
                "system": VERDICT_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_content}],
            },
        )
        resp.raise_for_status()
        text = "".join(
            b.get("text", "") for b in resp.json()["content"] if b["type"] == "text"
        )
    clean = re.sub(r"```(json)?", "", text).strip()
    verdict = json.loads(clean)
    # sanity-check shape
    assert verdict.get("verdict") in ("enter", "skip")
    verdict["confidence"] = float(verdict.get("confidence", 0))
    return verdict


# ------------------------------- Forwarding --------------------------------


async def forward_to_3commas(raw_body: bytes, content_type: str) -> int:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            FORWARD_URL,
            content=raw_body,
            headers={"Content-Type": content_type or "application/json"},
        )
        return resp.status_code


def log_decision(record: dict) -> None:
    record["ts"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


# --------------------------------- Routes ----------------------------------


@app.post("/signal")
async def handle_signal(request: Request):
    started = time.time()
    raw_body = await request.body()
    content_type = request.headers.get("content-type", "application/json")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        payload = {"_raw": raw_body.decode(errors="replace")}

    symbol = pair_to_binance_symbol(payload)
    market = await fetch_market_context(symbol) if symbol else None

    ai_error = None
    try:
        verdict = await get_ai_verdict(payload, market)
    except Exception as e:
        ai_error = str(e)
        verdict = {
            "verdict": "enter" if ON_AI_ERROR == "forward" else "skip",
            "confidence": 0.0,
            "reason": f"AI unavailable, fail-{'open' if ON_AI_ERROR == 'forward' else 'closed'}",
        }

    approved = verdict["verdict"] == "enter" and (
        ai_error or verdict["confidence"] >= MIN_CONFIDENCE
    )
    will_forward = approved or SHADOW_MODE

    forward_status = None
    if will_forward:
        try:
            forward_status = await forward_to_3commas(raw_body, content_type)
        except Exception as e:
            forward_status = f"forward_error: {e}"

    log_decision(
        {
            "symbol": symbol,
            "payload": payload,
            "market_data_available": market is not None,
            "verdict": verdict,
            "ai_error": ai_error,
            "approved_by_ai": approved,
            "shadow_mode": SHADOW_MODE,
            "forwarded": will_forward,
            "forward_status": forward_status,
            "latency_s": round(time.time() - started, 2),
        }
    )

    return {
        "ai_verdict": verdict,
        "forwarded_to_3commas": will_forward,
        "shadow_mode": SHADOW_MODE,
    }


@app.get("/health")
async def health():
    return {"ok": True, "shadow_mode": SHADOW_MODE, "model": ANTHROPIC_MODEL}
