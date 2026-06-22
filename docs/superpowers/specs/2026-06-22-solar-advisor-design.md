# Solar Advisor — Design Spec

**Date:** 2026-06-22
**Status:** Draft for review
**Author:** Riaan Schoeman

A self-hosted, advisory-only companion app for a local SolarAssistant instance. It
ingests live inverter telemetry and the current work-mode schedule, runs a
**deterministic** optimisation engine, and uses an LLM **only** to explain the engine's
output in plain English. It never writes to the inverter.

This is a clean-room personal/portfolio project: original code only, no SolarAssistant
proprietary code, no employer IP.

---

## 1. Goals & non-goals

**Goals (MVP):**
1. Connect read-only to the local SolarAssistant MQTT broker; ingest live telemetry and
   the current 6-slot work-mode / TOU schedule.
2. A clean dashboard that is genuinely easier to read than the stock UI.
3. An "Explain & Suggest" panel: for the current schedule, explain in plain English what
   each slot does, what it likely costs, and what to change and why.
4. A single **cost ↔ resilience** slider that re-runs the engine and changes the
   recommendation + explanation.

**Non-goals (MVP):**
- No writes to the inverter, ever (advisory-only; see §7).
- No multi-inverter / three-phase support (the target system is single-inverter,
  single-phase — see §2). The data model leaves room but we do not build for it.
- No REST/WebSocket ingest (MQTT covers everything we need; see §3).
- No historical database / long-term analytics beyond what the engine needs. In-memory
  rolling state for MVP.

---

## 2. Target system (discovered empirically, 2026-06-22)

Confirmed from a live `mosquitto_sub -v -t '#'` dump of the user's broker.

- **Inverter:** Deye/SunSynk/Sol-Ark, serial `2206074003`, **single inverter, single
  phase** (one `grid_voltage` ≈ 226 V, one AC output). MQTT root namespace
  `solar_assistant/`.
- **Battery:** ~51.2 V nominal LFP (absorption 53.0 V, float 52.5 V). No usable-capacity
  entity is published → capacity must be estimated (§5.2). BMS battery temperature read
  0.0 in the sample (may be absent/unreliable — treat as optional).
- **Settings of interest:** `max_charge_current=150 A`, `max_grid_charge_current=71 A`,
  `max_discharge_current=150 A`, `output_shutdown_capacity=20 %` (hard floor),
  `stop_battery_discharge_capacity=25 %`, `work_mode=Zero export to CT`,
  `energy_pattern=Battery first`, `use_timer=true`, `grid_charge=Enabled`.
- **The TOU schedule is fully exposed** as a 6-slot table (see §4.2). No per-slot power
  field exists in MQTT — confirming the firmware quirk: charge-rate is governed by
  `max_charge_current` / `max_grid_charge_current`, not a per-slot "Power" value. We do
  not model per-slot power.
- **Essential vs non-essential load split exists** (`load_power_essential`,
  `load_power_non-essential`) — the essential bus is the measurable backup-critical load.

### Parameter classification (post-discovery)

| Bucket | Parameters |
|---|---|
| **READ** (from MQTT) | Inverter identity/phase; SOC, battery V/I/power; PV power (+2 strings); grid import/export power + energy counters; load power (total/essential/non-essential); max charge/discharge/grid-charge currents; SOC floor (`output_shutdown_capacity`, `stop_battery_discharge_capacity`); full 6-slot schedule; work mode; energy pattern |
| **ESTIMATE** (from telemetry history, show confidence, user-correctable) | Usable battery kWh (from `battery_energy_in/out` counters over a cycle); PV array kWp (from peak clear-sky generation); typical daily consumption kWh (from `load_energy`); panel orientation (rough, optional, low confidence) |
| **ASK-ME** (cannot come from inverter) | Flat tariff: energy rate (R/kWh) + monthly fixed charge (R); backup priorities/windows beyond "hold reserve for essential bus"; objective slider default (BALANCED) |

---

## 3. Transport & data contract

| Concern | Transport | Notes |
|---|---|---|
| Live telemetry | **MQTT subscribe** (retained + streaming) | Primary, push-based, complete |
| Current settings & 6-slot schedule | **MQTT** (retained) | Same broker, no separate fetch |
| Writes | **NONE** | Hard-blocked in code (§7) |

**Ingest filter:** subscribe to `solar_assistant/#` only. The broker also carries
unrelated Frigate/camera binary topics; everything outside `solar_assistant/` is ignored.

**Topic → field mapping (telemetry):**

| Field | Topic | Unit |
|---|---|---|
| `battery_soc` | `solar_assistant/total/battery_state_of_charge/state` | % |
| `battery_power` | `solar_assistant/total/battery_power/state` | W (signed) |
| `battery_voltage` | `solar_assistant/inverter_1/battery_voltage/state` | V |
| `battery_current` | `solar_assistant/inverter_1/battery_current/state` | A |
| `pv_power` | `solar_assistant/inverter_1/pv_power/state` | W |
| `grid_power` | `solar_assistant/inverter_1/grid_power/state` | W (signed; + = import) |
| `load_power` | `solar_assistant/inverter_1/load_power/state` | W |
| `load_power_essential` | `solar_assistant/inverter_1/load_power_essential/state` | W |
| `grid_energy_in` (cumulative) | `solar_assistant/total/grid_energy_in/state` | kWh |
| `grid_energy_out` (cumulative) | `solar_assistant/total/grid_energy_out/state` | kWh |
| `pv_energy` / `load_energy` / `battery_energy_in` / `battery_energy_out` | `solar_assistant/total/{...}/state` | kWh |

Month-to-date grid import is **accumulated by us** from `grid_energy_in` deltas
(remembering the value at month rollover), since the inverter counter is lifetime-cumulative.

**Topic → field mapping (schedule, 6 slots, `i = 1..6`):**

| Field | Topic | Type |
|---|---|---|
| Slot start time | `solar_assistant/inverter_1/time_point_{i}/state` | `HH:MM` |
| Target SOC | `solar_assistant/inverter_1/capacity_point_{i}/state` | % |
| Grid-charge allowed | `solar_assistant/inverter_1/grid_charge_point_{i}/state` | bool |
| Gen-charge allowed | `solar_assistant/inverter_1/gen_charge_point_{i}/state` | bool |

A slot runs from its start time to the next slot's start (slot 6 wraps to slot 1).

---

## 4. Domain model

### 4.1 Telemetry snapshot (normalized)
Immutable struct produced by ingest: all of §3's telemetry fields + a timestamp + a
derived `month_to_date_grid_import_kwh`. The engine and dashboard consume this; neither
parses MQTT.

### 4.2 Schedule model
`Schedule = list[Slot]`, `Slot = {start: time, end: time, target_soc: int,
grid_charge: bool, gen_charge: bool}`. Built from the 6-slot topics. Pure data.

### 4.3 Config model
`BatteryLimits` (currents, voltages, SOC floor — read), `BatteryCapacity` (estimated kWh
+ confidence), `Tariff` (§6), `Objective` (slider scalar 0..1, default 0.5),
`BackupPolicy` (reserve floor, optional guaranteed windows).

---

## 5. Deterministic engine (`backend/engine/`)

**The engine is pure: no I/O, no network, no LLM, no clock reads passed implicitly.**
All inputs are explicit arguments; all outputs are plain data. This is what makes it
unit-testable and provably correct, and it is the project's centrepiece.

### 5.1 Modules
- `tariff.py` — `TariffModel` protocol; `FlatRateTariff` implementation (§6).
- `battery.py` — limits, usable-capacity estimate, SOC-floor logic, charge/discharge power
  from current × voltage.
- `schedule.py` — evaluate the *current* schedule: per-slot classification (what is this
  slot doing — solar-charging, grid-charging, holding, discharging), estimated cost/value
  per slot.
- `optimize.py` — given (tariff, battery limits, solar forecast, load profile, objective
  scalar), produce a **recommended** schedule + per-slot rationale + scores.

### 5.2 Battery capacity estimation
No capacity entity is published. Estimate usable kWh by integrating `battery_energy_out`
between a high-SOC and low-SOC point of an observed discharge (or `battery_energy_in` over
a charge), normalised by the SOC delta. Report value **with a confidence figure**; allow
user override. Until an estimate exists, the engine uses the user-provided/override value
or flags "insufficient data".

### 5.3 Objective: the cost ↔ resilience scalar
A single scalar `objective ∈ [0,1]` (0 = pure cost, 1 = pure resilience), default 0.5.
- **Toward cost:** minimise grid import; cycle the battery on solar; lower overnight
  reserve toward the SOC floor; disable grid-charge in slots where solar can refill.
- **Toward resilience:** hold a higher backup floor (grid-topped when solar falls short),
  accept the cost.
Same engine, one parameter, monotonic behaviour (verified by test: sweeping the scalar
moves reserve/expected-cost monotonically).

### 5.4 Key economic fact encoded
With a **flat** tariff and no cheap window, **self-consumption maximisation =
bill minimisation**. Grid-charging the battery is pure cost (paying the flat rate to store
energy solar would supply free) and earns its keep **only** as resilience insurance. The
engine makes this trade-off explicit; the slider is the single real decision variable.

---

## 6. Tariff model (corrected 2026-06-22)

The user's supply is **Eskom Direct prepaid, Homepower-class, flat-rate** — **not**
inclining-block (the IBT structure was removed under Eskom's Retail Tariff Plan):

- **Single flat energy rate** (~R3.56/kWh), independent of month-to-date consumption.
- **Monthly fixed charge** (~R535–700, varies by days in month), recovered first from
  prepaid purchases. This is a **sunk monthly cost**: it affects the *total bill* and the
  "early-month units feel expensive" explanation, but **not** any marginal scheduling
  decision. The optimiser uses the flat marginal rate only; bill projection adds the fixed
  charge.

**Implementation:** `TariffModel` protocol with `marginal_rate(month_to_date_kwh) -> R`
and `monthly_cost(import_kwh, days_in_month) -> R`. `FlatRateTariff` returns a constant
marginal rate and `fixed_charge + import_kwh * rate` for monthly cost. The protocol is
retained (not collapsed to a constant) because (a) rates change annually each April and
(b) the tariff structure already changed once under us — an inclining-block adapter could
return without touching the engine. Rates/charges live in config; the user supplies real
numbers.

---

## 7. Safety — advisory-only, enforced

- The MQTT client has **no publish path**. Every writable command topic is known from the
  dump (`solar_assistant/+/+/set`, `solar_assistant/set/#`); the client is constructed
  with publishing disabled and a blocklist, and a **unit test asserts it cannot publish**
  to any `/set` topic. Advisory-only is a tested invariant, not a promise.
- The UI shows a persistent disclaimer: recommendations are for the user to apply manually.

---

## 8. LLM explanation layer (`backend/explain/`) — the enforced boundary

The LLM is the **explanation/interface layer only**. It does not decide the schedule or
compute any number it presents.

- `context.py` builds an `ExplanationContext` DTO containing **only already-computed
  values** from the engine + telemetry snapshot (numbers, slot verdicts, costs in Rand,
  the recommended changes). The LLM never gets a solver handle, raw counters to do math
  on, or network access.
- `prompt.py` — templated prompts that ask Claude to render the provided facts as prose.
- `guard.py` — **numeric-provenance check**: every numeric token in the LLM's output is
  validated against the whitelist of values in the DTO (with tolerance for rounding/units).
  A number that did not come from the engine causes the response to be rejected/flagged.
  "The LLM never presents a number it didn't get from the engine" becomes a **testable
  runtime invariant**.

**Boundary enforcement (not just convention):** `engine/` imports nothing from `explain/`,
no network lib, and no LLM SDK. This is checked in CI by an `import-linter` contract; a PR
that makes the engine import the Anthropic SDK fails the build.

**Model:** Claude **Haiku 4.5** (cost-appropriate, fast, structured output). API key is
server-side only, rate-limited, with an env kill-switch. The key never reaches the browser.

---

## 9. Solar forecast

The engine takes a `SolarForecast` interface. Default adapter **reuses the user's existing
Home Assistant Forecast.Solar feed** (`sensor.energy_production_today/tomorrow`,
`power_production_now`) to avoid a second external dependency. An alternate adapter
(direct Forecast.Solar / Open-Meteo, lat -33.92 / lon 18.42, Cape Town) can be added
behind the same interface. Forecast source is config.

---

## 10. Repo structure

```
solar-advisor/
├─ backend/
│  ├─ ingest/      # MQTT client → normalized Telemetry + Config/Schedule snapshots. READ-ONLY.
│  ├─ engine/      # DETERMINISTIC. Pure functions. No I/O, no network, no LLM.
│  │  ├─ tariff.py
│  │  ├─ battery.py
│  │  ├─ schedule.py
│  │  └─ optimize.py
│  ├─ explain/     # LLM layer. Consumes engine output only.
│  │  ├─ context.py
│  │  ├─ prompt.py
│  │  └─ guard.py
│  ├─ api/         # FastAPI; key/rate-limit/kill-switch server-side only
│  └─ tests/       # heavy coverage on engine/ specifically
├─ frontend/       # Vue 3 + Vite + TS-strict
├─ docker-compose.yml
└─ README.md       # portfolio-grade from commit 1
```

---

## 11. Stack & conventions

- **Backend:** Python + FastAPI; MQTT (paho/asyncio-mqtt); Anthropic SDK server-side only.
- **Frontend:** Vue 3 + Vite + TypeScript (strict).
- **Local-first:** Docker Compose, runs in a container on Proxmox.
- **Conventions-first:** ruff + mypy(strict) for Python; ESLint + Prettier + TS-strict for
  Vue; `import-linter` boundary contract — all set up **before** feature code.
- **Audit-before-fix; small reviewable commits; real tests on the engine specifically.**

---

## 12. Staged build plan & definition of done

| Stage | Deliverable | Definition of done |
|---|---|---|
| **0. Conventions** | ruff + mypy(strict), ESLint + Prettier + TS-strict, import-linter contract, CI, Docker Compose skeleton, README skeleton | `make lint test` green on empty scaffold; boundary contract enforced in CI |
| **1. Ingest** | MQTT client → normalized Telemetry/Schedule/Config from the real topics; month-to-date grid-import accumulator | Live values match SA UI; reconnects cleanly; **publish-blocked test passes** |
| **2. Engine core** | `FlatRateTariff`, battery model, schedule evaluator | Unit-tested against hand-computed fixtures incl. month-boundary + SOC-floor edges |
| **3. Optimizer + slider** | objective scalar → recommended schedule + per-slot rationale + scores | Slider sweep produces monotonic, sane outputs; fully tested |
| **4. Explain layer** | ExplanationContext DTO, Claude integration, provenance guard | Guard rejects injected fake numbers in tests; explanations reference only engine values |
| **5. Dashboard** | Vue dashboard + Explain & Suggest panel + slider + advisory disclaimer | Reads cleaner than stock UI; slider re-runs engine live; disclaimer visible |

---

## 13. Open config values still needed from the user

1. **Flat tariff numbers:** energy rate (R/kWh) + monthly fixed charge (R). Can be
   reverse-engineered from a recent prepaid slip (e.g. "R1000 → 137.8 units").
2. **Backup priorities:** is "hold reserve for the essential bus" sufficient, or are there
   specific circuits / guaranteed time-windows? (Cape Town load-shedding context.)
3. **Slider default:** BALANCED (0.5) unless specified.

These are config, not architecture — they do not block stages 0–2.
