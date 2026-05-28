"""GET /adaptation/* – drift reports, model registry, threshold analysis."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/drift-report", summary="Current drift detection report")
async def get_drift_report() -> Dict[str, Any]:
    try:
        from app.adaptation.drift_detector import DriftDetector
        detector = DriftDetector()
        report = detector.check()
        return {
            "has_drift": report.has_drift,
            "severity": report.severity,
            "drift_types": report.drift_types,
            "details": report.details,
            "checked_at": report.checked_at.isoformat(),
        }
    except Exception as exc:
        logger.exception("GET /adaptation/drift-report failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/model-registry", summary="Model registry status")
async def get_model_registry() -> Dict[str, Any]:
    try:
        from app.adaptation.model_registry import ModelRegistry
        registry = ModelRegistry()
        return registry.get_status()
    except Exception as exc:
        logger.exception("GET /adaptation/model-registry failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/threshold-analysis", summary="Advisory threshold optimization report")
async def get_threshold_analysis(
    days: int = Query(default=90, ge=14, le=365)
) -> Dict[str, Any]:
    try:
        from app.adaptation.threshold_optimizer import ThresholdOptimizer
        opt = ThresholdOptimizer()
        return opt.analyze(days_back=days)
    except Exception as exc:
        logger.exception("GET /adaptation/threshold-analysis failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/rolling-performance", summary="Rolling shadow signal performance")
async def get_rolling_performance(
    window: int = Query(default=30, ge=5, le=200)
) -> Dict[str, Any]:
    try:
        from app.runtime.shadow_outcome_evaluator import ShadowOutcomeEvaluator
        evaluator = ShadowOutcomeEvaluator()
        perf = evaluator.compute_rolling_performance(window=window)
        perf["generated_at"] = datetime.now(timezone.utc).isoformat()
        return perf
    except Exception as exc:
        logger.exception("GET /adaptation/rolling-performance failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
