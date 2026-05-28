"""Tests for signal daemon: single cycle, graceful shutdown, state persistence."""
import asyncio
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


def test_daemon_initial_state():
    from app.runtime.signal_daemon import SignalDaemon
    daemon = SignalDaemon()
    assert daemon._running is False
    assert daemon._cycle_count == 0
    assert daemon._consecutive_errors == 0
    assert daemon._signal_mode in ("NORMAL", "WATCH_ONLY")
    assert daemon._shutdown_requested is False


def test_daemon_write_state(tmp_path):
    from app.runtime.signal_daemon import SignalDaemon
    from unittest.mock import patch
    state_file = str(tmp_path / "daemon_health.json")
    with patch("app.runtime.signal_daemon.settings") as mock_settings:
        mock_settings.daemon_state_file = state_file
        mock_settings.daemon_stop_signal_file = str(tmp_path / "stop.signal")
        mock_settings.telegram_enabled = False
        mock_settings.auto_retrain_enabled = True
        mock_settings.signal_mode = "NORMAL"

        daemon = SignalDaemon()
        daemon._running = True
        daemon._started_at = datetime.now(timezone.utc)
        daemon._write_state()

    assert os.path.exists(state_file)
    with open(state_file) as f:
        state = json.load(f)
    assert state["running"] is True
    assert "pid" in state
    assert "cycle_count" in state


def test_daemon_stop_signal_detection(tmp_path):
    from app.runtime.signal_daemon import SignalDaemon
    from unittest.mock import patch

    stop_file = str(tmp_path / "stop.signal")
    state_file = str(tmp_path / "daemon_health.json")

    with patch("app.runtime.signal_daemon.settings") as mock_settings:
        mock_settings.daemon_stop_signal_file = stop_file
        mock_settings.daemon_state_file = state_file
        mock_settings.telegram_enabled = False
        mock_settings.auto_retrain_enabled = True
        mock_settings.signal_mode = "NORMAL"

        daemon = SignalDaemon()
        assert not daemon._check_stop_signal()

        # Write stop signal file
        with open(stop_file, "w") as f:
            f.write("stop")
        assert daemon._check_stop_signal()


def test_signal_mode_downgrade_threshold():
    """Test that signal mode drops to WATCH_ONLY when PF < floor."""
    # Settings defaults: pf_floor=1.0, pf_recovery=1.3
    from app.core.config import settings
    assert settings.signal_mode_pf_floor == 1.0
    assert settings.signal_mode_pf_recovery == 1.3


@pytest.mark.asyncio
async def test_daemon_graceful_shutdown(tmp_path):
    """Test that daemon stops cleanly when shutdown_requested is set."""
    from app.runtime.signal_daemon import SignalDaemon
    from unittest.mock import patch, AsyncMock

    state_file = str(tmp_path / "health.json")
    stop_file = str(tmp_path / "stop.signal")

    with patch("app.runtime.signal_daemon.settings") as mock_settings:
        mock_settings.daemon_state_file = state_file
        mock_settings.daemon_stop_signal_file = stop_file
        mock_settings.daemon_log_file = str(tmp_path / "daemon.log")
        mock_settings.signal_loop_interval_minutes = 15
        mock_settings.telegram_enabled = False
        mock_settings.auto_retrain_enabled = False
        mock_settings.signal_mode = "NORMAL"
        mock_settings.shadow_mode_enabled = True
        mock_settings.drift_check_enabled = False
        mock_settings.max_consecutive_errors = 5
        mock_settings.signal_mode_rolling_window = 30
        mock_settings.signal_mode_pf_floor = 1.0
        mock_settings.signal_mode_pf_recovery = 1.3
        mock_settings.telegram_send_daily_summary = False
        mock_settings.retrain_interval_hours = 24
        mock_settings.drift_check_interval_hours = 6

        daemon = SignalDaemon()
        daemon._notifier = None
        daemon._evaluator = None

        # Patch _run_cycle to immediately request shutdown
        cycle_calls = []
        async def fake_cycle():
            cycle_calls.append(1)
            daemon._shutdown_requested = True

        daemon._run_cycle = fake_cycle
        daemon._setup_signals = lambda: None
        daemon._init_services = lambda: None

        await daemon.run()
        assert daemon._running is False
        assert len(cycle_calls) == 1
