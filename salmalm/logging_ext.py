from __future__ import annotations
"""SalmAlm Production Logging — structured JSON logs, rotation, request tracking.

Upgrades from basic logging to:
  - Structured JSON log format (machine-parseable)
  - Log rotation (max 10MB per file, keep 5 backups)
  - Request/response logging middleware
  - Performance metrics (request duration)
  - Error aggregation
  - Correlation IDs for request tracing
"""


import json
import logging
import logging.handlers
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from .constants import BASE_DIR, KST, LOG_FILE

# ── Structured JSON Formatter ────────────────────────────────

class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'ts': datetime.now(KST).isoformat(),
            'level': record.levelname,
            'msg': record.getMessage(),
            'module': record.module,
            'func': record.funcName,
            'line': record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
            }
        # Add extra fields
        for key in ('correlation_id', 'user', 'duration_ms', 'status_code',
                     'method', 'path', 'ip'):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, ensure_ascii=False)


# ── Rotating File Handler ────────────────────────────────────

def setup_production_logging(json_log: bool = True, max_bytes: int = 10_000_000,
                              backup_count: int = 5):
    """Configure production-grade logging with rotation."""
    logger = logging.getLogger('salmalm')

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        str(LOG_FILE), maxBytes=max_bytes, backupCount=backup_count,
        encoding='utf-8'
    )
    if json_log:
        file_handler.setFormatter(JSONFormatter())
    else:
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(file_handler)

    # Console handler (human-readable)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(console)

    logger.setLevel(logging.INFO)
    return logger


# ── Request Logger ───────────────────────────────────────────

_request_context = threading.local()


def get_correlation_id() -> str:
    """Get or create correlation ID for current request."""
    cid = getattr(_request_context, 'correlation_id', None)
    if not cid:
        cid = str(uuid.uuid4())[:8]
        _request_context.correlation_id = cid
    return cid


def set_correlation_id(cid: str):
    _request_context.correlation_id = cid


class RequestLogger:
    """Middleware-style request/response logger."""

    def __init__(self):
        self._logger = logging.getLogger('salmalm.requests')
        self._metrics: dict = {
            'total_requests': 0,
            'total_errors': 0,
            'by_status': {},
            'by_path': {},
            'avg_duration_ms': 0,
            '_durations': [],
        }
        self._lock = threading.Lock()

    def log_request(self, method: str, path: str, ip: str = '',
                    user: str = '', status_code: int = 200,
                    duration_ms: float = 0, error: str = ''):
        """Log a request with structured data."""
        extra = {
            'correlation_id': get_correlation_id(),
            'method': method,
            'path': path,
            'ip': ip,
            'user': user,
            'status_code': status_code,
            'duration_ms': round(duration_ms, 2),
        }

        if status_code >= 500:
            self._logger.error(f"{method} {path} -> {status_code} ({duration_ms:.0f}ms)",
                              extra=extra)
        elif status_code >= 400:
            self._logger.warning(f"{method} {path} -> {status_code} ({duration_ms:.0f}ms)",
                                extra=extra)
        else:
            self._logger.info(f"{method} {path} -> {status_code} ({duration_ms:.0f}ms)",
                             extra=extra)

        # Update metrics
        with self._lock:
            self._metrics['total_requests'] += 1
            if status_code >= 400:
                self._metrics['total_errors'] += 1
            sc = str(status_code)
            self._metrics['by_status'][sc] = self._metrics['by_status'].get(sc, 0) + 1
            # Track top paths
            self._metrics['by_path'][path] = self._metrics['by_path'].get(path, 0) + 1
            # Rolling average duration
            self._metrics['_durations'].append(duration_ms)
            if len(self._metrics['_durations']) > 1000:
                self._metrics['_durations'] = self._metrics['_durations'][-500:]
            if self._metrics['_durations']:
                self._metrics['avg_duration_ms'] = round(
                    sum(self._metrics['_durations']) / len(self._metrics['_durations']), 2)

    def get_metrics(self) -> dict:
        """Get request metrics (exclude internal durations list)."""
        with self._lock:
            m = {k: v for k, v in self._metrics.items() if not k.startswith('_')}
            m['error_rate'] = round(
                self._metrics['total_errors'] / max(self._metrics['total_requests'], 1) * 100, 2)
            # Top 10 paths
            m['top_paths'] = dict(sorted(
                self._metrics['by_path'].items(), key=lambda x: -x[1])[:10])
            return m


# ── Module instances ─────────────────────────────────────────

request_logger = RequestLogger()
