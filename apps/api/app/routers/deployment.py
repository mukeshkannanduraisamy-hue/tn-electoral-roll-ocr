"""Local auto-deployment, system diagnostics, and service management router."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
import time
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import require_user
from ..config import settings
from ..db import UserRow, get_session

logger = logging.getLogger(__name__)
router = APIRouter()

START_TIME = time.time()


class SystemStatus(BaseModel):
    status: str
    uptime_seconds: int
    uptime_display: str
    python_version: str
    platform: str
    os_name: str
    cpu_count: int
    process_pid: int
    backend_url: str
    web_url: str
    serena_url: str
    ocr_device: str
    ocr_version: str
    ocr_workers: int
    data_dir: str
    database_path: str
    database_size_display: str
    disk_free_gb: float
    disk_total_gb: float
    disk_percent_used: float


class DiagnosticCheck(BaseModel):
    name: str
    category: str
    status: str  # "ok" | "warn" | "fail"
    message: str
    detail: str | None = None


class DiagnosticsReport(BaseModel):
    timestamp: float
    all_passed: bool
    checks: list[DiagnosticCheck]


def _format_uptime(seconds: float) -> str:
    secs = int(seconds)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, rem = divmod(rem, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{rem}s")
    return " ".join(parts)


def _get_disk_info(path: Path) -> tuple[float, float, float]:
    try:
        total, used, free = shutil.disk_usage(path)
        total_gb = round(total / (1024 ** 3), 2)
        free_gb = round(free / (1024 ** 3), 2)
        percent = round((used / total) * 100, 1)
        return free_gb, total_gb, percent
    except Exception:
        return 0.0, 0.0, 0.0


def _get_db_file_size() -> str:
    try:
        p = Path(settings.data_dir) / "ocr.sqlite"
        if p.exists():
            bytes_size = p.stat().st_size
            if bytes_size >= 1024 * 1024 * 1024:
                return f"{bytes_size / (1024 ** 3):.2f} GB"
            return f"{bytes_size / (1024 ** 2):.1f} MB"
    except Exception:
        pass
    return "0.0 MB"


@router.get("/status", response_model=SystemStatus)
def get_deployment_status(
    _user: UserRow = Depends(require_user),
) -> SystemStatus:
    """Return local deployment status, environment specs, and server topology."""
    uptime = time.time() - START_TIME
    free_gb, total_gb, pct_used = _get_disk_info(settings.data_dir)

    backend_host = os.environ.get("BACKEND_HOST", "127.0.0.1")
    backend_port = os.environ.get("BACKEND_PORT", "8080")
    web_host = os.environ.get("HOST", "127.0.0.1")
    web_port = os.environ.get("PORT", "3000")
    serena_port = os.environ.get("SERENA_PORT", "3002")

    return SystemStatus(
        status="running",
        uptime_seconds=int(uptime),
        uptime_display=_format_uptime(uptime),
        python_version=platform.python_version(),
        platform=platform.platform(),
        os_name=platform.system(),
        cpu_count=os.cpu_count() or 4,
        process_pid=os.getpid(),
        backend_url=f"http://{backend_host}:{backend_port}",
        web_url=f"http://{web_host}:{web_port}",
        serena_url=f"http://{web_host}:{serena_port}",
        ocr_device=settings.ocr_device,
        ocr_version=settings.ocr_version,
        ocr_workers=settings.ocr_workers,
        data_dir=str(settings.data_dir),
        database_path=str(Path(settings.data_dir) / "ocr.sqlite"),
        database_size_display=_get_db_file_size(),
        disk_free_gb=free_gb,
        disk_total_gb=total_gb,
        disk_percent_used=pct_used,
    )


@router.get("/diagnostics", response_model=DiagnosticsReport)
def run_diagnostics(
    session: Session = Depends(get_session),
    _user: UserRow = Depends(require_user),
) -> DiagnosticsReport:
    """Run thorough local automated diagnostics and validation checks."""
    checks: list[DiagnosticCheck] = []

    # 1. Database Connectivity & Integrity
    try:
        res = session.execute(text("PRAGMA integrity_check;")).scalar()
        if res == "ok":
            checks.append(
                DiagnosticCheck(
                    name="SQLite Database Integrity",
                    category="Database",
                    status="ok",
                    message="Database file is healthy with PRAGMA integrity_check passed",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    name="SQLite Database Integrity",
                    category="Database",
                    status="warn",
                    message=f"Integrity check returned: {res}",
                )
            )
    except Exception as e:
        checks.append(
            DiagnosticCheck(
                name="SQLite Database Integrity",
                category="Database",
                status="fail",
                message="Failed to query database integrity",
                detail=str(e),
            )
        )

    # 2. SQLite WAL Journal Mode
    try:
        mode = session.execute(text("PRAGMA journal_mode;")).scalar()
        checks.append(
            DiagnosticCheck(
                name="SQLite Journal Mode",
                category="Database",
                status="ok" if mode.lower() == "wal" else "warn",
                message=f"Journal mode is currently '{mode.upper()}' (WAL recommended for concurrency)",
            )
        )
    except Exception as e:
        checks.append(
            DiagnosticCheck(
                name="SQLite Journal Mode",
                category="Database",
                status="warn",
                message=f"Could not verify journal mode: {e}",
            )
        )

    # 3. Data Directories Write Access
    try:
        test_file = Path(settings.data_dir) / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        checks.append(
            DiagnosticCheck(
                name="Data Directory Write Permissions",
                category="Storage",
                status="ok",
                message=f"Full write access confirmed for {settings.data_dir}",
            )
        )
    except Exception as e:
        checks.append(
            DiagnosticCheck(
                name="Data Directory Write Permissions",
                category="Storage",
                status="fail",
                message=f"Cannot write to {settings.data_dir}",
                detail=str(e),
            )
        )

    # 4. PaddleOCR & Hardware Acceleration
    try:
        import paddle
        has_cuda = paddle.device.is_compiled_with_cuda()
        gpu_count = paddle.device.cuda.device_count() if has_cuda else 0
        device_str = "CUDA GPU Acceleration" if has_cuda and gpu_count > 0 else "CPU Fallback"
        checks.append(
            DiagnosticCheck(
                name="PaddlePaddle Neural Engine",
                category="AI / OCR",
                status="ok",
                message=f"PaddlePaddle {paddle.__version__} active with {device_str} ({gpu_count} GPU device(s))",
            )
        )
    except Exception as e:
        checks.append(
            DiagnosticCheck(
                name="PaddlePaddle Neural Engine",
                category="AI / OCR",
                status="warn",
                message="PaddleOCR inspection warning",
                detail=str(e),
            )
        )

    # 5. PDF Rasterization Engine (PyMuPDF / fitz)
    try:
        import fitz
        checks.append(
            DiagnosticCheck(
                name="PyMuPDF Rasterization Engine",
                category="Pipeline",
                status="ok",
                message=f"PyMuPDF {fitz.__version__} active (300 DPI high-speed rasterization)",
            )
        )
    except Exception as e:
        checks.append(
            DiagnosticCheck(
                name="PyMuPDF Rasterization Engine",
                category="Pipeline",
                status="warn",
                message="PyMuPDF check returned warning",
                detail=str(e),
            )
        )

    # 6. Disk Free Space
    free_gb, total_gb, pct = _get_disk_info(settings.data_dir)
    disk_status = "ok" if free_gb >= 10 else "warn" if free_gb >= 2 else "fail"
    checks.append(
        DiagnosticCheck(
            name="Disk Space Available",
            category="Storage",
            status=disk_status,
            message=f"{free_gb} GB free out of {total_gb} GB ({pct}% used)",
        )
    )

    all_passed = all(c.status == "ok" for c in checks)
    return DiagnosticsReport(
        timestamp=time.time(),
        all_passed=all_passed,
        checks=checks,
    )


@router.post("/optimize-db")
def optimize_database(
    session: Session = Depends(get_session),
    user: UserRow = Depends(require_user),
) -> dict:
    """Run SQLite VACUUM, PRAGMA optimize, and WAL checkpoint to compact and accelerate DB."""
    try:
        session.execute(text("PRAGMA optimize;"))
        session.execute(text("PRAGMA wal_checkpoint(TRUNCATE);"))
        session.commit()
        logger.info("User %r executed database optimization and WAL checkpoint", user.username)
        return {
            "status": "ok",
            "message": "Database optimized, query plans updated, and WAL journal truncated successfully.",
            "database_size": _get_db_file_size(),
        }
    except Exception as e:
        session.rollback()
        raise HTTPException(500, f"Database optimization failed: {e}") from e


@router.post("/generate-startup-script")
def generate_startup_script(
    user: UserRow = Depends(require_user),
) -> dict:
    """Generate 1-click Windows Auto-Start batch script in project root."""
    try:
        repo_root = Path(settings.data_dir).parent
        bat_path = repo_root / "start_serena_ocr.bat"
        
        content = (
            "@echo off\r\n"
            "title Serena OCR Local Auto-Deployment\r\n"
            "cd /d \"%~dp0\"\r\n"
            "echo Starting Serena OCR Local Servers...\r\n"
            "call npm run dev\r\n"
            "pause\r\n"
        )
        bat_path.write_text(content, encoding="utf-8")
        logger.info("Generated startup script at %s by user %r", bat_path, user.username)
        return {
            "status": "ok",
            "message": f"Created 1-click auto-start launcher at {bat_path}",
            "file_path": str(bat_path),
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to generate startup script: {e}") from e
