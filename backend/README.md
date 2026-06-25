# Solar Advisor

A clean, self-hosted advisory dashboard for a home solar + battery system running
[SolarAssistant](https://solar-assistant.io). It reads inverter telemetry and the
work-mode schedule over local MQTT, runs a **deterministic** optimisation engine to
plan the day, and uses an LLM **only** to explain the engine's output in plain
language. It never writes to the inverter.

> ⚠️ **Advisory only — strictly read-only.** Solar Advisor never publishes to MQTT
> and never changes an inverter setting. Every recommendation is shown for you to apply
> manually, and an advisory disclaimer is visible on the dashboard at all times.

## The thesis: a hard boundary between the engine and the explanation

The point of this project is the line drawn down the middle of it:

```
              ┌──────────────────────────────────────────────────────┐
  MQTT  ──▶   │  Collector → SQLite        Deterministic engine        │
 (read-only)  │  (telemetry history)    (schedule, costs, reserve SOC, │
              │                          backup hours, recommendation) │
              └───────────────────────┬──────────────────────────────┘
                                      │  every number the user sees
                                      ▼  is computed here, verifiably
              ┌──────────────────────────────────────────────────────┐
   FastAPI    │  /api/dashboard  /api/history  /api/health            │
              │  /api/explain  ── LLM narrates the engine's output,    │
              │                   guarded so it can ONLY restate       │
              │                   numbers the engine produced          │
              └───────────────────────┬──────────────────────────────┘
                                      ▼
   Vue 3 SPA  │  live tiles · 6-slot schedule with per-slot cost &      │
  (nginx)     │  behaviour · cost↔resilience slider (re-runs engine) ·  │
              │  recommendation · Explain panel · 24h trend charts      │
```

- **The deterministic engine owns the decisions and the numbers.** Battery schedule,
  per-slot grid-import cost, reserve SOC, expected daily bill, backup runtime — all of
  it comes from explicit, testable Python. No model is in the loop for any figure you
  act on.
- **The LLM only narrates.** `/api/explain` asks Claude to describe the plan in plain
  language. A **provenance guard** checks the generated text against the engine's
  facts: if the explanation cites a number the engine didn't produce, it is
  **withheld** rather than shown — and the dashboard surfaces that withholding as a
  visible feature, not an error. This keeps a hallucinated figure from ever masquerading
  as advice.
- **The cost↔resilience slider re-runs the engine.** Moving it from "cheapest bill" to
  "most backup" re-evaluates the schedule deterministically and refreshes every number —
  the LLM is never asked to optimise anything.

## Dashboard

A modern Vue 3 dashboard designed to be easier to read at a glance than the stock UI:

- **Live tiles** — battery SOC, solar, grid (importing/exporting), and load.
- **Today's plan** — the 6-slot schedule with each slot's behaviour (solar-charging /
  grid-charging / discharging / holding), target & projected SOC, grid import, and cost.
  Grid-charging slots are flagged as a cost.
- **Recommendation** — reserve target SOC, backup runtime, expected daily cost, and the
  month-to-date bill, framed as a cost↔resilience trade-off.
- **Cost↔resilience slider** — re-runs the engine (debounced) on change.
- **Explain & Suggest** — a plain-language read of the plan from `/api/explain`, with the
  provenance-withheld warning surfaced.
- **24-hour trend charts** — hand-rolled SVG line charts for SOC, solar, grid, and load.
- **Purchase tracker:** log prepaid electricity purchases (date, rand, units); the app graphs the effective R/kWh over time and derives the engine's marginal tariff from your real purchases (lowest effective rate over a trailing window), falling back to the configured rate when no history exists. Writes go only to the app's own database — never to the inverter.

## Architecture

| Layer        | Stack                                              |
| ------------ | -------------------------------------------------- |
| Collector    | Python, async MQTT (read-only) → SQLite            |
| Engine       | Pure Python, deterministic, fully unit-tested      |
| API          | FastAPI (`/api/dashboard`, `/api/history`, `/api/explain`, `/api/health`) |
| Explanation  | Claude via the Anthropic SDK, behind a provenance guard + kill-switch |
| Frontend     | Vue 3 + TypeScript (strict), Vite, Vitest; SVG charts, no chart lib |
| Delivery     | Docker Compose: collector + API + nginx-served SPA |

The frontend is served as static files by nginx, which proxies `/api/*` to the API
container — so the SPA calls a same-origin API in production.

## Running it

From the `backend/` directory (where `docker-compose.yml` lives), create a `.env`
with at least the two required variables, then bring the stack up:

```bash
cat > .env <<'EOF'
SA_MQTT_HOST=your-solarassistant-host
ANTHROPIC_API_KEY=sk-ant-...
EOF
docker compose up --build
```

Then open:

- Dashboard (SPA via nginx): <http://localhost:8080>
- API directly: <http://localhost:8000>

Compose starts three services: `collector` (MQTT → SQLite), `api` (FastAPI), and `web`
(nginx serving the built SPA, proxying `/api/` to `api:8000`).

### Environment variables

Required:

| Variable            | Purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `SA_MQTT_HOST`      | SolarAssistant MQTT broker host (read-only).         |
| `ANTHROPIC_API_KEY` | Claude API key for the Explain panel.                |

Common optional (defaults shown):

| Variable                  | Default            | Purpose                                  |
| ------------------------- | ------------------ | ---------------------------------------- |
| `SA_MQTT_PORT`            | `1883`             | MQTT port.                               |
| `SA_MQTT_USER` / `SA_MQTT_PASS` | _(empty)_    | MQTT credentials, if your broker needs them. |
| `SA_DB_PATH`              | `solar_advisor.db` | SQLite telemetry path (a Docker volume in compose). |
| `SA_TARIFF_RATE`          | `3.56`             | Energy rate (currency/kWh) for cost maths. |
| `SA_TARIFF_FIXED_CHARGE`  | `600`              | Fixed monthly charge.                    |
| `SA_BATTERY_NOMINAL_KWH`  | `15`               | Battery usable capacity estimate.        |
| `SA_BATTERY_SOC_FLOOR_PCT`| `20`               | Reserve floor the engine won't plan below. |
| `SA_ESSENTIAL_POWER_W`    | `1136`             | Essential load used for backup-runtime maths. |
| `SA_OBJECTIVE_DEFAULT`    | `0.5`              | Starting cost↔resilience objective (0..1). |
| `SA_EXPLAIN_ENABLED`      | `true`             | Kill-switch for the LLM Explain panel.   |
| `SA_EXPLAIN_MODEL`        | `claude-haiku-4-5` | Model used for explanations.             |
| `SA_EXPLAIN_MIN_INTERVAL_S` | `10`             | Rate-limit between explanation calls.    |
| `SA_EXPLAIN_MAX_TOKENS`   | `2048`             | Max tokens per explanation.              |

With `SA_EXPLAIN_ENABLED=false` the dashboard runs fully without any LLM — the
deterministic engine and every number it produces are unaffected.

## Development

```bash
cd backend  && make check    # ruff, mypy strict, import-linter, pytest
cd frontend && npm run check  # eslint, vue-tsc, vitest, vite build
```

Clean-room personal project. See `docs/superpowers/specs/` for the design and
`docs/superpowers/plans/` for the build plans (A–E).
