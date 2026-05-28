"""
GET  /daemon/status    – daemon health state
POST /daemon/stop      – request graceful stop (writes stop signal file)
POST /daemon/start     – clear stop signal file (daemon restarts via Docker restart policy)
POST /daemon/restart   – stop then clear (Docker restarts)
GET  /daemon/logs      – recent log lines
GET  /daemon/last-run  – last run details

NOTE: The daemon runs as a separate Docker service.
The API communicates via the state file and stop signal file.
SIGNAL ONLY – no live trading.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _read_state() -> Dict[str, Any]:
    state_path = Path(settings.daemon_state_file)
    if not state_path.exists():
        return {
            "running": False,
            "pid": None,
            "started_at": None,
            "last_run_at": None,
            "next_run_at": None,
            "cycle_count": 0,
            "consecutive_errors": 0,
            "last_error": None,
            "last_signal": None,
            "last_signal_at": None,
            "telegram_enabled": settings.telegram_enabled,
            "auto_retrain_enabled": settings.auto_retrain_enabled,
            "signal_mode": settings.signal_mode,
            "note": "Daemon state file not found — daemon may not be running",
        }
    try:
        return json.loads(state_path.read_text())
    except Exception:
        return {"running": False, "note": "State file unreadable"}


@router.get("/status", summary="Daemon health status")
async def get_daemon_status() -> Dict[str, Any]:
    state = _read_state()
    state["stop_signal_pending"] = Path(settings.daemon_stop_signal_file).exists()
    state["generated_at"] = datetime.now(timezone.utc).isoformat()
    return state


@router.post("/stop", summary="Request graceful daemon stop")
async def stop_daemon() -> Dict[str, Any]:
    stop_path = Path(settings.daemon_stop_signal_file)
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    stop_path.write_text(f"stop requested at {datetime.now(timezone.utc).isoformat()}")
    logger.info("Daemon stop signal written to %s", stop_path)
    return {
        "status": "stop_requested",
        "message": "Stop signal written. Daemon will finish current cycle and exit.",
        "stop_signal_file": str(stop_path),
    }


@router.post("/start", summary="Clear stop signal (daemon restarts via Docker)")
async def start_daemon() -> Dict[str, Any]:
    stop_path = Path(settings.daemon_stop_signal_file)
    if stop_path.exists():
        stop_path.unlink()
        logger.info("Daemon stop signal cleared")
    return {
        "status": "stop_signal_cleared",
        "message": "Stop signal cleared. If running via Docker, daemon will restart automatically.",
    }


@router.post("/restart", summary="Request daemon restart")
async def restart_daemon() -> Dict[str, Any]:
    stop_path = Path(settings.daemon_stop_signal_file)
    stop_path.parent.mkdir(parents=True, exist_ok=True)
    stop_path.write_text(f"restart requested at {datetime.now(timezone.utc).isoformat()}")
    return {
        "status": "restart_requested",
        "message": "Stop signal written. Docker will restart the daemon container automatically.",
    }


@router.get("/logs", summary="Recent daemon log lines")
async def get_daemon_logs(lines: int = 100) -> Dict[str, Any]:
    log_path = Path(settings.daemon_log_file)
    if not log_path.exists():
        return {"lines": [], "note": "Log file not found"}
    try:
        all_lines = log_path.read_text(errors="replace").splitlines()
        return {
            "lines": all_lines[-lines:],
            "total_lines": len(all_lines),
            "log_file": str(log_path),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/last-run", summary="Last daemon cycle details")
async def get_last_run() -> Dict[str, Any]:
    state = _read_state()
    return {
        "last_run_at": state.get("last_run_at"),
        "next_run_at": state.get("next_run_at"),
        "last_signal": state.get("last_signal"),
        "last_signal_at": state.get("last_signal_at"),
        "cycle_count": state.get("cycle_count"),
        "consecutive_errors": state.get("consecutive_errors"),
        "last_error": state.get("last_error"),
        "signal_mode": state.get("signal_mode"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
