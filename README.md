# AI Deal Filter for 3commas DCA Bots

A small proxy that sits between TradingView and 3commas. Every "start new deal"
alert is checked by Claude against live market data before it reaches your bot.

```
TradingView alert ──> your server (/signal) ──> Claude verdict ──> 3commas
                                          └──> blocked + logged if "skip"
```

## 1. Deploy the server

Any small VPS works (Hetzner/DigitalOcean ~$5/mo), or a free Railway/Render instance.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # from console.anthropic.com
export SHADOW_MODE=true                    # IMPORTANT: keep true at first
uvicorn main:app --host 0.0.0.0 --port 8000
```

Put it behind HTTPS (Caddy/nginx, or your platform does it for you).
TradingView requires webhook URLs on port 80/443.

## 2. Change ONE thing in TradingView

In each alert that starts a 3commas deal:

- **Webhook URL:** change `https://app.3commas.io/trade_signal/trading_view`
  to `https://YOUR-SERVER/signal`
- **Message:** leave your existing 3commas JSON exactly as it is.
  The server forwards the raw body untouched when approved.

That's it — no Pine Script changes required. (If your indicator builds the
alert with `alert()` in Pine, that also keeps working unchanged.)

## 3. Run in shadow mode first (strongly recommended)

With `SHADOW_MODE=true`, every deal still goes through, but the AI verdict is
recorded in `decisions.jsonl`. After 1–2 weeks:

```bash
# deals the AI would have blocked
grep '"approved_by_ai": false' decisions.jsonl
```

Check in 3commas how those specific deals actually performed. If the blocked
ones genuinely did worse, flip `SHADOW_MODE=false` and the filter goes live.
If not, tune `RISK_RULES` / `MIN_CONFIDENCE` and keep shadowing.

## 4. Tuning knobs (env vars)

| Variable         | Default            | Meaning                                          |
|------------------|--------------------|--------------------------------------------------|
| `SHADOW_MODE`    | `true`             | Log verdicts but never block                     |
| `MIN_CONFIDENCE` | `0.6`              | Min AI confidence for an "enter" to pass         |
| `ON_AI_ERROR`    | `forward`          | `forward` = fail-open, `block` = fail-closed     |
| `RISK_RULES`     | sensible defaults  | Plain-text rules injected into the AI prompt     |
| `ANTHROPIC_MODEL`| `claude-sonnet-4-6`| Use `claude-haiku-4-5-20251001` for cheaper calls|
| `FORWARD_URL`    | 3commas signal URL | Where approved payloads go                       |

## Notes & limitations

- Market context comes from Binance public endpoints (no key needed). If you
  trade on another exchange the prices may differ slightly, or swap in your
  exchange's public klines endpoint in `fetch_market_context`.
- Each check adds ~2–5 seconds of latency — fine for DCA bots, not for scalping.
- Cost: roughly a fraction of a cent per signal with Haiku, a few cents with Sonnet.
- The AI is one safety layer, not a guarantee. Keep your hard limits (max active
  deals, deal size, stop conditions) configured inside 3commas as usual.
- This is tooling, not financial advice — validate on your own data before
  trusting it with real capital.
