# Recommended Inverter Settings & Solar Forecast Display — Design

**Date:** 2026-06-26
**Status:** Approved (brainstorming) — ready for plan
**Depends on:** everything merged through Plan N.

## 1. Purpose

Two display-only improvements (all data already in the `/api/dashboard` payload):
1. **The recommendation must speak in the inverter's own settings.** The current "Recommended schedule" shows engine projections (behaviour/end-SOC/cost), not what to *set*. Replace it with a **settings sheet** whose columns mirror the inverter's TOU screen — **Time | State of charge | Charge** — so the user can transcribe it directly. Only SOC and grid-charge are advised; Power and Sell are untouched (the inverter is zero-export).
2. **Surface the solar forecast** we built (`expected_pv_kwh_today`/`expected_pv_kwh_tomorrow`) — currently in the payload but shown nowhere.

No backend changes: `DashboardView` already carries `slots`, `recommended_slots` (each `SlotView` with `target_soc:int`, `grid_charge:bool`, `start`, `end`), and `expected_pv_kwh_today`/`expected_pv_kwh_tomorrow`.

## 2. Confirmed facts (from the user's inverter config)
- Per-slot "Charge" = **grid charge** (Work mode → Grid charge: Enabled). Our `grid_charge` flag maps to it.
- **Zero export to CT** → no selling; the per-slot "Sell" is irrelevant — footnote says it stays off.
- Battery 300 Ah ≈ 15.4 kWh; Deye/SunSynk — consistent with the app's assumptions.

---

## PLAN O — Frontend

### O1. `ScheduleSettings.vue` — the "what to set" sheet

New presentational component. Props: `current: SlotView[]`, `recommended: SlotView[]`. Renders a table mirroring the inverter's TOU config:

| Time | State of charge | Charge |
|------|-----------------|--------|
| 00:00–05:00 | **60% (was 65%)** | **Off (was On)** |
| 08:00–16:30 | 100% | Off |
| … | | |

- One row per slot (all slots, so it's a complete sheet to transcribe).
- **State of charge** = `recommended.target_soc`%; if it differs from `current.target_soc`, show `60% (was 65%)` and highlight the cell.
- **Charge** = `recommended.grid_charge ? 'On' : 'Off'`; if it differs from current, show `Off (was On)` and highlight.
- Header label "Charge" with a small "(grid)" qualifier so it's unambiguous.
- Footnote: *"Only State of charge and Charge change. Leave Power as-is; Sell stays off (zero-export)."*

### O2. `ScheduleCompare.vue` — use the settings sheet

Restructure: the savings banner stays; the **current** schedule keeps the existing `ScheduleTable` (the "Today's plan" what's-happening/cost view); the **recommended** side becomes `ScheduleSettings` (the what-to-set diff) instead of a second projection `ScheduleTable`. When `matches`, keep showing the current `ScheduleTable` + "already matches" (no settings sheet needed).

### O3. Solar forecast tile

`LiveTiles.vue`: add a **"Solar forecast"** tile — value `formatKwh(dashboard.expected_pv_kwh_today)` ("today"), sub-line `{formatKwh(dashboard.expected_pv_kwh_tomorrow)} tomorrow`. Sun/forecast icon, neutral/solar tone. (`expected_pv_kwh_today`/`tomorrow` already on `DashboardView`.)

---

## 3. Testing
- `ScheduleSettings`: renders a row per slot with SOC% + Charge On/Off; highlights + "(was …)" when a slot's target_soc or grid_charge differs; no "(was …)" when identical; footnote present.
- `ScheduleCompare`: when schedules differ → renders the current `ScheduleTable` + `ScheduleSettings` (not two projection tables) + savings banner; when identical → current table + "already matches", no settings sheet.
- `LiveTiles`: forecast tile shows today's kWh + tomorrow sub-line.

## 4. Decomposition
- **Plan O** — one frontend plan: O1 `ScheduleSettings` + O2 `ScheduleCompare` rewire (group 1), O3 forecast tile + full gate + final review (group 2). Same worktree → subagent → fast-forward-merge flow.

## 5. Non-goals (YAGNI)
- The grid-charge-power accuracy fix (max grid-charge 71 A ≈ 3.6 kW vs the 8 kW max charge) — a separate noted backend follow-up; it refines the savings number but isn't part of this display round.
- Writing settings to the inverter (still strictly advisory/read-only — the user applies them).
- Modelling "Sell"/export (zero-export inverter).
