# Real Solar Forecast, Prepaid Projection & Clearer Recommendation — Design

**Date:** 2026-06-26
**Status:** Approved (brainstorming) — ready for plans
**Depends on:** MVP (A–E) + purchase tracker (F–G) + dashboard/purchases polish (H–I), all merged.

## 1. Purpose

Address comprehension/accuracy gaps found in real use:
- "Today's plan" grid-in/cost feel inaccurate — because the solar forecast is a static 20 kWh/day guess. Build our **own** location-based forecast.
- "Bill so far" is meaningless for prepaid — replace it with a **spend-vs-projection** view (energy only) plus a **per-purchase "what you got"** (days of cover).
- Battery tile should show a **%/hour** rate.
- The recommendation should be **actionable** and explain why daily cost is often flat across the slider.

## 2. Locked decisions

- Forecast source: **Forecast.Solar free API** (no key), our own provider — not Home Assistant.
- PV array: **split**, two planes of 2.5 kWp each (5 × 500 W), tilt **26°** (config default), Forecast.Solar azimuths **NE = −135**, **SW = +45** (API convention `0 = south`, `−90 = east`, `+90 = west`, `±180 = north`). Lat **−33.92**, lon **18.42**.
- Month projection: **energy only**, excludes the monthly fixed charge.
- Per-purchase display shows **units + ≈ days of cover**.
- Battery flow shown as **%/hour**.

---

## PLAN J — Backend

### J1. `ForecastSolarProvider` (our own forecast)

New `forecast/forecast_solar_provider.py` implementing the existing `ForecastProvider` protocol (`fetch() -> SolarForecast`).

- For each configured sub-array, call `GET https://api.forecast.solar/estimate/{lat}/{lon}/{tilt}/{azimuth}/{kwp}` (httpx, short timeout). Parse `result.watt_hours_day` → a `{date: kWh}` map; **sum across sub-arrays**. Map today's date → `expected_pv_kwh_today`, tomorrow → `expected_pv_kwh_tomorrow` (fall back to the nearest available day if a date is absent).
- **Caching:** hold the last `SolarForecast` + a monotonic timestamp. `fetch()` returns the cache unless older than `SA_FORECAST_TTL_S` (default `10800` = 3 h); only then attempt a refresh. This keeps us well under the ~12 req/hr free-tier limit even though `fetch()` is called on every dashboard poll, and avoids blocking most requests.
- **Fallback:** on any error (HTTP, timeout, parse, rate-limit 429) return the last good cache; if there's no cache yet, return the static config values (`forecast_today_kwh`/`forecast_tomorrow_kwh`). The app must never hard-depend on the network.
- Pure-ish: the provider does I/O (it's in `forecast/`, not `engine/` — the import-linter engine-purity contract is unaffected).

**Config** (`config.py`): `SA_FORECAST_SOURCE` (`static` | `forecast_solar`, default `static` so nothing changes until opted in), `SA_LAT` (−33.92), `SA_LON` (18.42), `SA_FORECAST_TTL_S` (10800), and the array list `SA_PV_ARRAYS` as a JSON string, default:
`[{"tilt":26,"azimuth":-135,"kwp":2.5},{"tilt":26,"azimuth":45,"kwp":2.5}]`.
Parse it into a typed `list[PvArray]` (a small frozen dataclass `PvArray(tilt, azimuth, kwp)`); on malformed JSON, log and fall back to the default arrays.

**Wiring** (`api/app.py` `create_production_app`): when `SA_FORECAST_SOURCE == "forecast_solar"`, construct `ForecastSolarProvider(lat, lon, arrays, ttl, static_today, static_tomorrow)`; else keep `StaticForecastProvider`. Everything downstream (`RecommendationService`) is unchanged — it just gets better numbers.

`docker-compose.yml`: pass the new `SA_*` envs through to the `api` service.

### J2. Prepaid month projection (energy only)

Surface a spend-vs-projection on the dashboard, computed in `RecommendationService.build()` (it already has the tariff/derived rate, telemetry MTD import, days-in-month, and — via the tariff provider's reader — purchase access; give the service a purchase reader to total the month's spend).

- `month_spend` = Σ `rand` of purchases whose `purchased_at` is in the current calendar month (of `telemetry.ts`).
- `month_projected_energy_cost` = `(mtd_grid_import_kwh / days_elapsed) * days_in_month * rate`, where `days_elapsed = telemetry.ts.day`, `rate` = derived marginal rate. **No fixed charge.** Guard `days_elapsed >= 1`.
- `month_balance` = `month_spend − month_projected_energy_cost` (positive = projected to spare; negative = top-up needed of `−balance`).
- Add to `DashboardData` + `DashboardView`: `month_spend: float`, `month_projected_cost: float`, `month_balance: float`. `_to_view` rounds to whole rand.
- Keep `recommendation.monthly_cost_so_far` in the engine for now (still used by the explain layer's facts) but the UI stops showing it (Plan K) in favour of the projection. (Do NOT add the projection to the LLM `allowed_numbers`; it's a display metric.)

The service needs the purchase reader. Inject a `PurchaseReader` (the existing Protocol with `list_since`) — sum `list_since(first_of_month)` filtered to the month. `create_production_app` passes the same `SqlitePurchaseStore`.

---

## PLAN K — Frontend

### K1. Battery %/hour
`LiveTiles.vue`: extend the battery sub-line to append a rate — `charging 420 W · ≈ +2.8%/h`, where `%/h = battery_power / (usable_kwh * 1000) * 100` (uses `dashboard.usable_kwh`, already present). Discharging shows `−x%/h`; idle shows just "idle". Round to 1 dp.

### K2. Prepaid projection panel (replaces "bill so far")
`types.ts` `DashboardView` += `month_spend`, `month_projected_cost`, `month_balance`. `RecommendationPanel.vue`: replace the `monthly_cost_so_far` line with the projection — **"This month: spent R X · projected R Y"** and a balance line: **"≈ R Z to top up"** (balance < 0) or **"≈ R Z to spare"** (balance ≥ 0), clearly tagged an estimate. (Confirm the panel reads these new dashboard fields, not the old recommendation field.)

### K3. Per-purchase "what you got" (days of cover)
`PurchaseTable.vue` (and the create flow): show each purchase's tangible yield — a **"≈ N days"** derived as `units_kwh / dailyConsumptionKwh` (rounded), alongside the existing units. The `Purchases` view already fetches the dashboard for the tariff badge; pass `daily_consumption_kwh` down as a prop to the table so it can compute days-of-cover. When daily consumption is unknown/0, omit the "≈ N days" gracefully.

### K4. Actionable recommendation + flat-cost explanation
`RecommendationPanel.vue`: reframe the existing fields as guidance —
- A headline action derived from `enable_overnight_grid_charge` + `grid_charge_kwh`: e.g. **"Enable overnight grid-charge to ~{reserve_target_soc}% (≈{grid_charge_kwh} kWh)"** when true, or **"No grid-charging needed — solar + battery cover your {reserve_target_soc}% reserve"** when false.
- When `grid_charge_kwh == 0`, add a one-line note that the daily cost won't move with the slider because no grid energy is being bought for backup — which is why the slider looks inert at high SOC.
- Keep reserve %, backup hours, expected daily import/cost, but label each in plain terms ("keep as backup", "runs essentials for", "grid energy you'll buy today", "today's grid cost").

This group is wording/markup over existing fields — no new backend data beyond J2.

---

## 3. Testing

**Backend**
- `ForecastSolarProvider`: parses a sample multi-array Forecast.Solar JSON and **sums** planes for today/tomorrow; caches (second `fetch()` within TTL does NOT re-call the HTTP client — inject a fake fetcher/clock); falls back to static on HTTP error / 429 / malformed JSON; cold-start error → static values. `SA_PV_ARRAYS` parsing (valid + malformed → default). `SA_FORECAST_SOURCE` selects the provider in the container wiring.
- Month projection: known telemetry (mtd import, ts.day) + seeded month purchases → expected `month_spend`, `month_projected_cost` (energy only, no fixed charge), `month_balance` sign (to-spare vs top-up); `days_elapsed` guard; purchases from a prior month excluded.
- `DashboardView` carries the three projection fields.

**Frontend**
- Battery %/h: charging/discharging sign + value from `battery_power`/`usable_kwh`; idle case.
- Projection panel: spent/projected/balance rendering; "to top up" vs "to spare" by sign; reads dashboard fields.
- Per-purchase days-of-cover: `units / daily` rounded; omitted when daily is 0.
- Recommendation: grid-charge action string when true; "no grid-charging needed" + flat-cost note when `grid_charge_kwh == 0`.

## 4. Decomposition
- **Plan J — backend:** J1 forecast provider (+ config + wiring + compose), J2 month projection.
- **Plan K — frontend:** K1 battery %/h, K2 projection panel, K3 per-purchase days, K4 recommendation wording.
Same flow: worktree per plan, subagent-driven with two-stage review, fast-forward merge per plan.

## 5. Non-goals (YAGNI)
- Modeling a realistic intra-day **load shape** (still a flat hourly average — a later accuracy lever once the forecast is real).
- Sub-hourly forecast / per-slot forecast allocation beyond the current daylight-overlap split.
- Solcast/Open-Meteo providers (Forecast.Solar suffices; the provider seam allows adding them later).
- Persisting forecast history or charting predicted-vs-actual PV.
- Telemetry retention/pruning (still tracked separately — see the standing TODO).
