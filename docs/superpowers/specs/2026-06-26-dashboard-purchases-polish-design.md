# Dashboard & Purchases Polish — Design

**Date:** 2026-06-26
**Status:** Approved (brainstorming) — ready for plans
**Depends on:** MVP (Plans A–E) + Purchase tracker (Plans F–G), all merged to `main`

## 1. Purpose

A round of UX/feature improvements from real-world use of the running app:

- **General:** hover tooltips on every chart.
- **Purchases:** collapsible "Log a purchase" form; fix the effective-rate chart's "drop to zero"; align table headers with their values; add inline edit.
- **Dashboard:** surface battery charge/discharge and the inverter's conversion/idle draw; expand the history range beyond 24h.

## 2. Locked decisions

- **History range:** up to **30 days**, via a 24h / 7d / 30d toggle, backed by **server-side bucketing** (~400 points per response regardless of range).
- **Edit purchases:** **inline in the table row** (edit-in-place with Save/Cancel).
- **Energy detail:** **battery charge/discharge inside the Battery tile** + a **new Conversion/idle tile** for the residual.

## 3. Energy balance (the correct model)

The instantaneous power balance at the inverter bus, using the telemetry sign conventions
(`grid_power` + = import; `battery_power` + = charging):

```
pv_power + grid_power − battery_power − load_power = conversion/idle losses
```

So **`conversion_power = pv_power + grid_power − battery_power − load_power`** ≈ the
inverter's own conversion + standby draw. It can go slightly negative from measurement
noise; the tile clamps the displayed value at 0. This is **pure telemetry arithmetic for
display** — it is not an engine optimisation number and is not surfaced to the LLM
(not added to the explain layer's `allowed_numbers`).

---

## PLAN H — Backend

### H1. Expose battery power + conversion power

- `domain`/service: the values come straight from `telemetry` (`battery_power`) and the
  derived `conversion_power` (formula in §3), computed in `RecommendationService.build()`
  and carried on `DashboardData`.
- `api/schemas.py` — `DashboardView` gains `battery_power: float` and `conversion_power: float`.
- `api/app.py` — `_to_view` maps `data.telemetry.battery_power` and `data.conversion_power`
  (the service computes `conversion_power = pv + grid − battery_power − load`; `_to_view`
  rounds to whole watts).
- No engine/LLM coupling; `allowed_numbers` untouched.

### H2. History: 30-day range + server-side bucketing + battery power

- `api/schemas.py` — `HistoryPoint` gains `battery_power: float`.
- `storage/sqlite_store.py` — add `query_bucketed(start, end, bucket_seconds) -> list[Telemetry]`:
  - SQL aggregation, not Python-side, so 30 days never loads ~260k rows into memory.
  - Bucket key from the ISO `ts` text: `CAST(strftime('%s', replace(ts, 'T', ' ')) AS INTEGER) / :bucket`
    (the `T`→space swap keeps `strftime` robust across SQLite builds; the stored `+00:00`
    offset is handled by `strftime`, which returns UTC epoch).
  - `GROUP BY` the bucket key; `AVG()` each metric (`battery_soc`, `pv_power`, `grid_power`,
    `load_power`, `battery_power`); the bucket's `ts` = `MIN(ts)` of the bucket.
  - Return `Telemetry` rows (other fields zero-filled — only the charted metrics matter
    here), ordered by `ts`.
- `api/app.py` — `/api/history`:
  - Raise the cap: `hours: int = Query(default=24, ge=1, le=720)`.
  - Choose bucket width to target ≤ ~400 points: `bucket_seconds = max(10, ceil(hours * 3600 / 400))`.
  - Call `query_bucketed`; map to `HistoryPoint` including `battery_power`.
- Performance/refresh note (drives a frontend change in I): bucketed responses are light, so
  the frontend will fetch history on mount + on range-change + on a slower (60 s) timer,
  decoupled from the 10 s dashboard poll.

### H3. Edit a purchase: `PUT /api/purchases/{id}`

- `storage/purchase_store.py` — `PurchaseStore` Protocol + `SqlitePurchaseStore` gain
  `update(purchase_id: int, purchase: Purchase) -> Purchase | None` (SQL `UPDATE`; returns the
  updated row, or `None` when no row matched).
- `api/app.py` — `PUT /api/purchases/{purchase_id}` taking `PurchaseCreate` (same validation:
  positive rand/units, non-future date), returning `PurchaseView`; `404` when `update` returns
  `None`. CORS already allows the method set is GET/POST/DELETE — **add `PUT`**.

---

## PLAN I — Frontend

### I1. Chart hover tooltips (shared behaviour)

- Both `TrendChart.vue` (time series) and `PurchaseCharts.vue` (rate line + bars) get a
  pointer overlay: on `pointermove` over the SVG, map cursor x (via the element's bounding
  rect) to the nearest data index, then render a small absolutely-positioned tooltip inside
  the `figure` showing the value + label (TrendChart: metric value + timestamp; PurchaseCharts:
  effective rate + date for the line, rand/units + date for the bars). Hide on `pointerleave`.
- Keep it dependency-free and consistent with the existing hand-rolled SVG approach (no chart
  library). A highlight dot/line marks the snapped point.

### I2. Collapsible "Log a purchase"

- `Purchases.vue` wraps `PurchaseForm` in a collapsed-by-default disclosure: a
  "+ Log a purchase" button toggles it open. After a successful `created`, it can stay open
  or collapse — collapse (tidiest), with the table/charts refreshed.

### I3. Effective-rate "drop to zero" fix

- In `PurchaseCharts.vue` `rateGeom`, pad the y-domain by ~8% of its span (top and bottom)
  so the minimum value floats off the baseline instead of hugging it. The reference line and
  tooltips remain correct. (Root cause: the domain min mapped exactly to the chart's bottom
  edge, so the lowest/most-recent rate looked like zero.)

### I4. Purchases table alignment

- `PurchaseTable.vue` — right-align the numeric column **headers** (Paid, Units, Rate) to
  match their right-aligned cells; Date and Note stay left-aligned. Pure CSS.

### I5. Live tiles: battery flow + conversion/idle

- `LiveTiles.vue`:
  - **Battery tile** gains a sub-line derived from `dashboard.battery_power`:
    `> 0` → "charging N W", `< 0` → "discharging N W", `0` → "idle".
  - **New Conversion tile**: shows `max(0, dashboard.conversion_power)` W, labelled
    "Conversion / idle", with a one-line hint that it's inverter overhead + losses.
- `types.ts` `DashboardView` gains `battery_power: number` and `conversion_power: number`.

### I6. History range selector + battery-power trend

- `types.ts` `HistoryPoint` gains `battery_power: number`.
- `Dashboard.vue`:
  - A 24h / 7d / 30d toggle above the trend charts; selecting re-fetches `getHistory(hours)`
    (24 / 168 / 720).
  - Decouple history fetching from the 10 s dashboard poll: fetch on mount, on range change,
    and on a 60 s timer.
  - Add a 5th `TrendChart` for `battery_power` (charge/discharge), now that the field exists.
- `api/client.ts` — `getHistory` already takes `hours`; no signature change (callers pass the
  selected range).

### I7. Inline edit

- `api/types.ts` / `api/client.ts` — add `updatePurchase(id: number, body: PurchaseCreate): Promise<PurchaseView>`
  (`PUT /api/purchases/{id}`, same error handling as `createPurchase`).
- `PurchaseTable.vue` — each row gains an **Edit** button; clicking swaps its cells for
  inputs (date / rand / units / note) with **Save** / **Cancel**. Save validates (mirror the
  form: positive numbers, non-future date) and emits `update` with `{ id, body }`; the table
  shows inline errors and exits edit mode on success. Only one row editable at a time.
- `Purchases.vue` — handles `@update` → `updatePurchase` → `refresh()`.

---

## 4. Testing

**Backend**
- `conversion_power`: service computes `pv + grid − battery − load`; `DashboardView` carries
  it and `battery_power`; a known telemetry snapshot yields the expected residual (incl. a
  negative-noise case the tile would clamp).
- `query_bucketed`: rows spanning several buckets average correctly; bucket `ts` = bucket min;
  empty range → `[]`; a single bucket; verifies the `T`→space epoch bucketing.
- `/api/history`: `hours` accepts up to 720, rejects > 720; bucket width shrinks the point
  count for long ranges; `battery_power` present in points.
- `purchase_store.update`: updates an existing row (returns it), returns `None` for a missing
  id. `PUT /api/purchases/{id}`: happy path (200 + updated view), 404 for missing id, 422 for
  invalid body; CORS includes PUT.

**Frontend**
- Tooltip: `pointermove` over a chart shows the snapped value/label; `pointerleave` hides it.
- `PurchaseForm` collapse: hidden by default, button reveals it.
- Rate chart: the minimum value no longer maps to the baseline (y > bottom edge).
- `PurchaseTable`: numeric headers right-aligned; inline edit reveals inputs, Save emits
  `update` with the edited body, Cancel restores, validation blocks a bad edit.
- `LiveTiles`: battery sub-line reflects charging/discharging/idle by sign; Conversion tile
  clamps negatives to 0.
- `Dashboard`: range toggle calls `getHistory(24|168|720)`; battery-power chart renders.
- `client`: `updatePurchase` issues `PUT` with the body and surfaces errors via `ApiError`.

## 5. Decomposition

- **Plan H — backend:** H1 (battery/conversion fields), H2 (history bucketing + 30d +
  battery_power), H3 (PUT edit). Verifiable via API tests before any UI.
- **Plan I — frontend:** I1 tooltips, I2 collapsible form, I3 dropoff fix, I4 alignment,
  I5 tiles, I6 range selector + battery chart, I7 inline edit.

Same flow as F/G: worktree per plan, subagent-driven execution with two-stage review,
fast-forward merge to `main` per plan.

## 6. Non-goals (YAGNI)

- Data **retention/pruning** of telemetry (the DB grows unbounded; out of scope here — note
  it as a future task, especially before the long-term server deployment).
- Configurable bucket size / arbitrary custom date ranges (the 3 presets cover the need).
- Editing the **derived tariff** or fixed charge from the UI (still config + purchase-derived).
- Multi-row simultaneous editing.
- A full real-time animated energy-flow diagram (the tiles convey the same information).
