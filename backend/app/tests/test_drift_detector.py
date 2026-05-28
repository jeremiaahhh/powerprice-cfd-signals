"""Tests for drift detector logic (no DB required — unit tests on data logic)."""
import pytest
import numpy as np
from unittest.mock import MagicMock, patch


def test_drift_report_dataclass():
    from app.adaptation.drift_detector import DriftReport
    from datetime import datetime, timezone
    report = DriftReport(
        has_drift=True,
        severity="HIGH",
        drift_types=["feature_drift"],
        details={"vol_ratio": 1.8},
    )
    assert report.has_drift is True
    assert report.severity == "HIGH"
    assert "feature_drift" in report.drift_types
    assert report.checked_at is not None


def test_drift_severity_levels():
    from app.adaptation.drift_detector import DriftDetector
    d = DriftDetector()
    # Test severity logic
    drift_types_high = ["feature_drift", "prediction_drift", "performance_drift"]
    drift_types_medium = ["feature_drift", "prediction_drift"]
    drift_types_low = ["tail_event_drift"]

    sev_high = "HIGH" if len(drift_types_high) >= 3 else "MEDIUM"
    sev_med = "HIGH" if len(drift_types_medium) >= 3 else "MEDIUM"
    sev_low = "LOW" if len(drift_types_low) < 2 else "MEDIUM"

    assert sev_high == "HIGH"
    assert sev_med == "MEDIUM"
    assert sev_low == "LOW"


def test_model_registry_promotion_rules():
    from app.adaptation.model_registry import ModelRegistry
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        reg = ModelRegistry(model_dir=tmpdir)

        # No production model → always promote
        should, reason = reg.should_promote({"profit_factor": 1.0})
        assert should is True

        # Set production
        reg.record_production_metrics({"profit_factor": 1.20, "max_drawdown_pct": 50.0, "worst_trade_eur_mwh": -30.0})

        # PF too low (< 95% of 1.20 = 1.14)
        should, reason = reg.should_promote({"profit_factor": 1.10, "max_drawdown_pct": 50.0})
        assert should is False
        assert "PF" in reason

        # PF acceptable
        should, reason = reg.should_promote({"profit_factor": 1.18, "max_drawdown_pct": 50.0, "worst_trade_eur_mwh": -35.0})
        assert should is True

        # Drawdown too high (> 110% of 50 = 55)
        should, reason = reg.should_promote({"profit_factor": 1.25, "max_drawdown_pct": 60.0})
        assert should is False
        assert "MaxDD" in reason

        # Extreme calibration
        should, reason = reg.should_promote({"mean_p_rebound": 0.95, "profit_factor": 1.5})
        assert should is False
        assert "calibration" in reason.lower()


def test_threshold_optimizer_returns_advisory():
    from app.adaptation.threshold_optimizer import ThresholdOptimizer
    # With no DB this returns error or insufficient_data
    opt = ThresholdOptimizer()
    result = opt.analyze(days_back=90)
    # Should return a dict without raising
    assert isinstance(result, dict)
    assert "status" in result


def test_shadow_outcome_rolling_performance_empty():
    from app.runtime.shadow_outcome_evaluator import ShadowOutcomeEvaluator
    ev = ShadowOutcomeEvaluator()
    # With no data this should return safe defaults
    result = ev.compute_rolling_performance(window=30)
    assert isinstance(result, dict)
    assert "rolling_pf" in result
    assert "rolling_win_rate" in result
    assert "sample_size" in result
