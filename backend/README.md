# Solar Advisor

Advisory-only companion for a self-hosted [SolarAssistant](https://solar-assistant.io)
instance. Reads inverter telemetry and the work-mode schedule over local MQTT, runs a
**deterministic** optimisation engine, and uses an LLM purely to explain the engine's
output. It never writes to the inverter.

> ⚠️ **Advisory only.** This app is strictly read-only against your inverter.
> Recommendations are shown for you to apply manually.

Clean-room personal project. See `docs/superpowers/specs/` for the design and
`docs/superpowers/plans/` for the build plans.

## Status
Plan A (data foundation): read-only MQTT ingest → SQLite storage.
