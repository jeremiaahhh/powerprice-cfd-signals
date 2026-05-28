"""Tests for Telegram notification formatting and deduplication."""
import pytest
import time


def test_format_signal_high_confidence():
    from app.notifications.message_templates import format_signal
    sig = {
        "action": "HIGH_CONFIDENCE_SIGNAL",
        "current_price": -42.30,
        "p_rebound": 0.74,
        "net_edge": 38.20,
        "tail_risk_score": 0.12,
        "regime": "PV_OVERSUPPLY_REBOUND",
        "stop_loss": -62.30,
        "take_profit": 12.0,
        "max_holding_hours": 4,
        "reason": "Preis negativ, Rebound-Wahrscheinlichkeit hoch",
        "risk_warnings": [],
    }
    text = format_signal(sig)
    assert "HIGH_CONFIDENCE_SIGNAL" in text
    assert "-42.30" in text
    assert "0.74" in text
    assert "Signal only" in text
    assert "Keine Order" in text


def test_format_signal_html_escape():
    from app.notifications.message_templates import format_signal
    sig = {
        "action": "WATCH_LONG_REBOUND",
        "current_price": -5.0,
        "regime": "<script>alert('xss')</script>",
        "risk_warnings": ["<b>danger</b>"],
    }
    text = format_signal(sig)
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_format_blocked_signal():
    from app.notifications.message_templates import format_signal
    sig = {
        "action": "TAIL_RISK_BLOCKED",
        "current_price": -200.0,
        "tail_risk_score": 0.82,
    }
    text = format_signal(sig)
    assert "TAIL_RISK_BLOCKED" in text
    assert "Signal only" in text


def test_format_daily_summary():
    from app.notifications.message_templates import format_daily_summary
    summary = {
        "signals_today": 96,
        "enter_signals": 3,
        "blocked_signals": 12,
        "rolling_pf": 1.25,
        "rolling_win_rate": 62.5,
        "current_regime": "WINTER_LOW",
        "signal_mode": "NORMAL",
    }
    text = format_daily_summary(summary)
    assert "NORMAL" in text
    assert "WINTER_LOW" in text
    assert "Signal only" in text


def test_dedup_prevents_repeat():
    from app.notifications.notification_service import NotificationService
    svc = NotificationService.__new__(NotificationService)
    svc._dedup_cache = {}
    svc._dedup_ttl_s = 3600
    svc._enabled = False
    svc._client = None

    fp = svc._make_fingerprint("signal:HIGH_CONFIDENCE_SIGNAL", "bucket_-45")
    assert not svc._is_duplicate(fp)
    svc._mark_sent(fp)
    assert svc._is_duplicate(fp)


def test_dedup_expires():
    from app.notifications.notification_service import NotificationService
    svc = NotificationService.__new__(NotificationService)
    svc._dedup_cache = {}
    svc._dedup_ttl_s = 1  # 1 second TTL for testing
    svc._enabled = False
    svc._client = None

    fp = svc._make_fingerprint("signal:test", "bucket_0")
    svc._mark_sent(fp)
    assert svc._is_duplicate(fp)
    time.sleep(1.1)
    # After TTL expires, is_duplicate cleans expired and returns False
    assert not svc._is_duplicate(fp)


def test_format_retrain_report():
    from app.notifications.message_templates import format_retrain_report
    report = {
        "promoted": True,
        "model": "rebound_classifier",
        "new_pf": 1.35,
        "old_pf": 1.22,
        "new_win_rate": 68.5,
        "reason": "AUC improved",
    }
    text = format_retrain_report(report)
    assert "Promoviert" in text
    assert "1.35" in text
    assert "Signal only" in text


def test_format_drift_alert():
    from app.notifications.message_templates import format_drift_alert
    report = {
        "drift_types": ["feature_drift", "performance_drift"],
        "severity": "HIGH",
        "details": {"vol_ratio": 1.8, "mean_shift": 35.5},
    }
    text = format_drift_alert(report)
    assert "feature_drift" in text
    assert "HIGH" in text
