# src/solar_advisor/api/app.py
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from solar_advisor.api.schemas import (
    DashboardView,
    ExplanationView,
    HistoryPoint,
    HistoryView,
    RecommendationView,
    SlotView,
)
from solar_advisor.config import AppConfig, load_config
from solar_advisor.estimation.estimator import ParameterEstimator
from solar_advisor.explain.client import Explainer, anthropic_complete
from solar_advisor.explain.context import build_context
from solar_advisor.forecast.static_provider import StaticForecastProvider
from solar_advisor.ingest.live import LiveState, run_live_ingest
from solar_advisor.services.recommendation import DashboardData, RecommendationService
from solar_advisor.storage.sqlite_store import SqliteTelemetryStore
from solar_advisor.storage.store import TelemetryStore


def get_state(request: Request) -> LiveState:
    state = getattr(request.app.state, "live", None)
    if not isinstance(state, LiveState):
        raise HTTPException(status_code=500, detail="state not initialised")
    return state


def get_service(request: Request) -> RecommendationService:
    service = getattr(request.app.state, "service", None)
    if not isinstance(service, RecommendationService):
        raise HTTPException(status_code=500, detail="service not initialised")
    return service


def get_store(request: Request) -> TelemetryStore:
    store = getattr(request.app.state, "store", None)
    if not isinstance(store, TelemetryStore):
        raise HTTPException(status_code=500, detail="store not initialised")
    return store


def get_explainer(request: Request) -> Explainer:
    explainer = getattr(request.app.state, "explainer", None)
    if not isinstance(explainer, Explainer):
        raise HTTPException(status_code=500, detail="explainer not initialised")
    return explainer


def _to_view(data: DashboardData) -> DashboardView:
    return DashboardView(
        objective=data.objective,
        battery_soc=data.telemetry.battery_soc,
        pv_power=data.telemetry.pv_power,
        grid_power=data.telemetry.grid_power,
        load_power=data.telemetry.load_power,
        month_to_date_grid_import_kwh=data.telemetry.month_to_date_grid_import_kwh,
        usable_kwh=data.usable_kwh,
        usable_kwh_confidence=data.usable_kwh_confidence,
        daily_consumption_kwh=data.daily_consumption_kwh,
        daily_consumption_confidence=data.daily_consumption_confidence,
        tariff_rate=data.tariff_rate,
        expected_pv_kwh_today=round(data.expected_pv_kwh_today, 2),
        expected_pv_kwh_tomorrow=round(data.expected_pv_kwh_tomorrow, 2),
        slots=[
            SlotView(
                start=a.slot.start.isoformat(timespec="minutes"),
                end=a.slot.end.isoformat(timespec="minutes"),
                target_soc=a.slot.target_soc,
                grid_charge=a.slot.grid_charge,
                behavior=a.behavior.value,
                end_soc=round(a.end_soc, 1),
                grid_import_kwh=round(a.grid_import_kwh, 2),
                cost=round(a.cost, 2),
            )
            for a in data.slot_assessments
        ],
        recommendation=RecommendationView(
            reserve_target_soc=round(data.recommendation.reserve_target_soc, 1),
            enable_overnight_grid_charge=data.recommendation.enable_overnight_grid_charge,
            grid_charge_kwh=round(data.recommendation.grid_charge_kwh, 2),
            expected_daily_grid_import_kwh=round(
                data.recommendation.expected_daily_grid_import_kwh, 2
            ),
            expected_daily_cost=round(data.recommendation.expected_daily_cost, 2),
            backup_hours=round(data.recommendation.backup_hours, 1),
            monthly_cost_so_far=round(data.recommendation.monthly_cost_so_far, 2),
        ),
        disclaimer=data.disclaimer,
    )


def build_app(state: LiveState, config: AppConfig | None = None) -> FastAPI:
    """Build the FastAPI app around a given LiveState. The live MQTT loop is
    started in the lifespan only when a config is supplied (skipped in tests)."""

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        if config is not None:
            task = asyncio.create_task(
                run_live_ingest(
                    state,
                    host=config.mqtt_host,
                    port=config.mqtt_port,
                    username=config.mqtt_user,
                    password=config.mqtt_pass,
                )
            )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Solar Advisor", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],  # Vite dev server (Plan E)
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.state.live = state

    @app.get("/api/health")
    def health(state: LiveState = Depends(get_state)) -> dict[str, object]:  # noqa: B008
        return {
            "status": "ok",
            "telemetry_ready": state.telemetry is not None,
            "schedule_ready": state.schedule is not None,
            "telemetry_ts": (
                state.telemetry.ts.isoformat() if state.telemetry is not None else None
            ),
        }

    @app.get("/api/dashboard", response_model=DashboardView)
    def dashboard(
        objective: float | None = Query(default=None, ge=0.0, le=1.0),
        service: RecommendationService = Depends(get_service),  # noqa: B008
        state: LiveState = Depends(get_state),  # noqa: B008
    ) -> DashboardView:
        try:
            data = service.build(state, objective=objective)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _to_view(data)

    @app.get("/api/explain", response_model=ExplanationView)
    def explain(
        objective: float | None = Query(default=None, ge=0.0, le=1.0),
        service: RecommendationService = Depends(get_service),  # noqa: B008
        state: LiveState = Depends(get_state),  # noqa: B008
        explainer: Explainer = Depends(get_explainer),  # noqa: B008
    ) -> ExplanationView:
        try:
            data = service.build(state, objective=objective)
        except LookupError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        result = explainer.explain(build_context(data))
        return ExplanationView(
            explanation=result.text,
            generated=result.generated,
            guard_ok=result.guard_ok,
            unverified_numbers=result.unverified,
            disclaimer=data.disclaimer,
        )

    @app.get("/api/history", response_model=HistoryView)
    def history(
        hours: int = Query(default=24, ge=1, le=168),
        store: TelemetryStore = Depends(get_store),  # noqa: B008
    ) -> HistoryView:
        end = datetime.now(UTC)
        rows = store.query_range(end - timedelta(hours=hours), end)
        return HistoryView(
            points=[
                HistoryPoint(
                    ts=r.ts.isoformat(),
                    battery_soc=r.battery_soc,
                    pv_power=r.pv_power,
                    grid_power=r.grid_power,
                    load_power=r.load_power,
                )
                for r in rows
            ]
        )

    return app


def create_production_app() -> FastAPI:
    """Entry point for uvicorn: wires real config, store, estimator, forecast."""
    config = load_config()
    store = SqliteTelemetryStore(config.db_path)
    state = LiveState(store=store)
    estimator = ParameterEstimator(store, nominal_kwh=config.battery_nominal_kwh)
    forecast = StaticForecastProvider(
        today_kwh=config.forecast_today_kwh, tomorrow_kwh=config.forecast_tomorrow_kwh
    )
    service = RecommendationService(config=config, estimator=estimator, forecast=forecast)
    explainer = Explainer(
        complete=anthropic_complete(config.explain_model, max_tokens=config.explain_max_tokens),
        enabled=config.explain_enabled,
        min_interval_s=config.explain_min_interval_s,
    )
    app = build_app(state=state, config=config)
    app.state.store = store
    app.state.service = service
    app.state.explainer = explainer
    return app
