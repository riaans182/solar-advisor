# Purchase Tracker & Data-Derived Tariff — Design

**Date:** 2026-06-25
**Status:** Approved (brainstorming) — ready for plan
**Depends on:** MVP (Plans A–E, merged to `main`)

## 1. Purpose

Today the tariff is a static config guess (`SA_TARIFF_RATE`, default R3.56/kWh). The
engine's every decision turns on that single number, and we have no way to know if it
is still accurate after an Eskom increase.

This feature adds a place to **log each prepaid electricity purchase** (date, rand
spent, units received), persists them, **graphs spend/units/effective-price over
time**, and makes the engine's marginal tariff **derived from real purchases** instead
of a static guess — so the rate tracks reality and price increases are visible
historically rather than discovered by surprise.

## 2. The read-only boundary (explicit)

The MVP's load-bearing invariant is **read-only against the inverter**: no MQTT publish
path, `assert_read_only` rejects `/set` topics, CORS is GET-only, the advisory
disclaimer is always visible.

This feature introduces the app's **first write endpoints** (`POST`/`DELETE`). They
write **only to the advisor's own SQLite database** (the purchase log) — never to the
inverter, never over MQTT. The inverter remains strictly subscribe-only and the
advisory disclaimer is unchanged. CORS gains `POST`/`DELETE`, **scoped to
`/api/purchases` only**; `/api/dashboard`, `/api/explain`, `/api/history` stay GET-only.
This distinction must be stated in code comments where the write path is introduced so a
future reader doesn't mistake it for a relaxation of the inverter invariant.

## 3. Data model

A purchase is a user-entered record:

```
Purchase {
    id: int            # autoincrement primary key
    purchased_at: date # ISO date (no time component needed)
    rand: float        # > 0, total rand paid
    units_kwh: float   # > 0, units credited to the meter
    note: str | None   # optional free text, e.g. "City of CT prepaid"
}
```

The **effective rate** (`rand / units_kwh`) is **derived on read, never stored** — it is
a pure function of the two recorded numbers, so storing it would risk drift.

Stored in a new SQLite table `purchases` in the **same database file** as telemetry
(`config.db_path`), so there is one volume to back up and one connection story. The
telemetry store is unaffected.

## 4. Tariff derivation (the chosen method)

A new pure function/module derives the engine's marginal rate from the purchase list:

- **Marginal R/kWh = the minimum `rand / units_kwh` across purchases within a trailing
  window** (default **90 days**, `SA_TARIFF_WINDOW_DAYS`).
- **Rationale:** on prepaid, the monthly fixed charge is recovered from the *first*
  purchase of each month, so that purchase's `rand/units` is inflated (you paid for units
  you didn't receive). Later same-month purchases converge on the true flat energy rate.
  The **minimum** effective rate in the window is therefore the least
  fixed-charge-contaminated estimate of the marginal cost — which is exactly the number
  the engine's self-consumption-vs-grid-charge decisions depend on. When a price increase
  lands (e.g. the April Eskom hike), the trailing window drops the old cheap buys and the
  minimum steps up to the new rate.
- **Fallback:** when there are **no purchases in the window**, fall back to
  `config.tariff_rate`. (So a fresh install behaves exactly as it does today until the
  first purchase is logged.)
- **Provenance:** the derivation returns both the rate **and** the purchase it came from
  (date), so the UI can show "R3.51/kWh — from your purchase on 12 Apr" vs. "R3.56/kWh —
  config default (no purchases logged yet)".

**Monthly fixed charge stays config-driven** (`SA_TARIFF_FIXED_CHARGE`). The chosen
method derives the *marginal* rate only; the fixed charge feeds the bill projection
(`monthly_cost`), not the engine's slot decisions. This is a deliberate, documented
limitation — a future upgrade could derive the fixed charge via a regression "fit" over
purchases, but YAGNI for now.

## 5. Backend components

| Unit | Responsibility |
|------|----------------|
| `storage/purchase_store.py` — `SqlitePurchaseStore` | CRUD over the `purchases` table: `add(purchase) -> Purchase` (returns row with id), `list_all() -> list[Purchase]` (newest first), `list_since(cutoff_date) -> list[Purchase]`, `delete(id) -> bool`. Mirrors `SqliteTelemetryStore`'s `check_same_thread=False` single-writer-multi-reader story. |
| `storage/purchase_store.py` — `PurchaseStore` Protocol | `@runtime_checkable` Protocol mirroring `storage/store.py`, so the API depends on the interface. |
| `domain/purchase.py` — `Purchase` | Frozen dataclass (the model in §3). |
| `tariff/derivation.py` — `derive_marginal_rate(purchases, *, window_days, today, fallback_rate) -> DerivedRate` | Pure function implementing §4. `DerivedRate { rate: float, source: "purchase" | "config", source_date: date | None }`. No I/O — testable in isolation, and (like `engine/`) free of storage imports. |
| `services/recommendation.py` (modify) | `RecommendationService` gains a tariff-provider dependency; `build()` calls the derivation (using the purchase store + `cfg.tariff_rate` fallback) and constructs `FlatRateTariff(energy_rate=derived.rate, monthly_fixed_charge=cfg.tariff_fixed_charge)`. `DashboardData` gains `tariff_source` + `tariff_source_date` so the dashboard can show provenance. |
| `api/app.py` (modify) | New endpoints (below); CORS allow `POST`/`DELETE`; wire `SqlitePurchaseStore` into `create_production_app()` and `app.state`. |
| `api/schemas.py` (modify) | `PurchaseCreate` (request: purchased_at, rand, units_kwh, note?), `PurchaseView` (response: + id + effective_rate), `PurchaseListView`. `DashboardView` gains `tariff_source`, `tariff_source_date`. |

### Endpoints

- `POST /api/purchases` — body `PurchaseCreate`; validates `rand > 0`, `units_kwh > 0`,
  `purchased_at` parseable and not in the future; returns `201` + `PurchaseView`.
- `GET /api/purchases` — returns `PurchaseListView` (newest first, each with derived
  `effective_rate`).
- `DELETE /api/purchases/{id}` — removes a mistaken entry; `204` on success, `404` if no
  such id.

The derived tariff surfaces on the existing `GET /api/dashboard` (rate + source +
source_date) — no separate tariff endpoint (YAGNI).

## 6. Frontend components

A new **Purchases** section/view (reachable from the dashboard), plus a small provenance
badge on the dashboard's existing tariff figure.

| Unit | Responsibility |
|------|----------------|
| `api/types.ts` + `api/client.ts` (modify) | Types for `PurchaseCreate`/`PurchaseView`/`PurchaseListView`; client gains `getPurchases()`, `createPurchase(body)`, `deletePurchase(id)` (the first non-GET calls — keep `ApiError` handling consistent). |
| `components/PurchaseForm.vue` | Capture form: date / rand / units, with a **live "= R X.XX/kWh" preview** as the user types; client-side validation mirrors the server (positive numbers, non-future date); on submit calls `createPurchase`, emits success to refresh the list. |
| `components/PurchaseTable.vue` | Lists purchases newest-first (date, rand, units, effective rate), each row deletable (with confirm). |
| `components/PurchaseCharts.vue` | Hand-rolled SVG charts (same approach as `TrendChart`): (a) **effective R/kWh over time** — the price-increase story, with the current derived marginal rate drawn as a reference line; (b) **rand spent per purchase / per month**; (c) **units received per purchase**. |
| `components/TariffBadge.vue` (or inline in dashboard) | Shows the derived rate's provenance ("from purchases" + date, or "config default"). |
| `views/Purchases.vue` | Composes form + table + charts; refetches the list after create/delete. |

The capture form is the app's first user input that mutates state — keep it simple and
forgiving (clear validation messages, no destructive surprises).

## 7. Testing

- **`derive_marginal_rate` (unit, the heart of the feature):** minimum-over-window;
  the fixed-charge-contamination case (a high first-of-month buy is correctly ignored in
  favour of a cheaper later buy); empty window → config fallback; the **April step-up**
  (old cheap purchases age out of the window → derived rate rises); window boundary
  (a purchase exactly at the cutoff); provenance fields populated correctly.
- **`SqlitePurchaseStore` (round-trip):** add→list (newest-first ordering), `list_since`
  cutoff, delete (existing + missing id), effective-rate derivation on read.
- **Endpoints:** `POST` happy path + validation rejections (non-positive rand/units,
  future date, malformed date); `GET` ordering + effective_rate; `DELETE` 204/404;
  CORS still GET-only for the other endpoints.
- **`RecommendationService` (integration):** with purchases logged, `FlatRateTariff` uses
  the derived rate and `DashboardData` reports `tariff_source="purchase"`; with none, it
  falls back to config with `tariff_source="config"`.
- **Frontend:** `PurchaseForm` validation + live effective-rate preview; `PurchaseTable`
  renders/derives rate + delete confirm; chart components render given sample data;
  client create/delete error handling.

## 8. Decomposition into plans

Two sequential plans, each shipping working, tested software:

- **Plan F — Backend:** `domain/purchase.py`, `storage/purchase_store.py`,
  `tariff/derivation.py`, schema additions, the three endpoints, CORS change,
  `RecommendationService` wiring, dashboard provenance fields. Engine now consumes the
  derived tariff; everything verifiable via API tests before any UI exists.
- **Plan G — Frontend:** client methods, `PurchaseForm`, `PurchaseTable`,
  `PurchaseCharts`, `Purchases` view, dashboard tariff badge.

Same flow as Plans A–E: own git worktree per plan, subagent-driven execution with
two-stage review, fast-forward merge to `main` per plan.

## 9. Non-goals (YAGNI)

- Deriving the monthly fixed charge from data (config-driven for now — §4).
- Editing a purchase in place (delete + re-add covers the rare correction).
- Multi-meter / multi-account support (single household).
- Auth on the write endpoints (self-hosted, single-user, LAN-only — consistent with the
  rest of the app).
- Importing purchase history from a file (manual entry is enough to start tracking).
