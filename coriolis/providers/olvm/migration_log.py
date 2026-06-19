# Copyright 2024 CloudShift / Coriolis
# All Rights Reserved.

"""Migration Logger

Schreibt pro Migrations-Vorgang ein JSON-Lines Logfile.

Aufbau:  <log_dir>/<instance_name>_<YYYYMMDD-HHmmss>.log

Jede Zeile ist ein eigenes JSON-Objekt:
  {"event": "migration_start", "instance": "web01", "ts": "...", ...}
  {"event": "network_provisioned", "vlan_id": 100, "ts": "..."}
  {"event": "disk_transfer", "disk_id": "...", "size_gb": 80}
  {"event": "migration_end", "status": "success", "duration_seconds": 1842}
  {"event": "migration_end", "status": "error", "error": "..."}
"""

import datetime
import json
import os
import re
import threading

from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

_DEFAULT_LOG_DIR = "/var/log/coriolis/migrations"


def _safe_filename(name):
    """Bereinigt einen String für den Einsatz als Dateiname."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", name)[:80]


class MigrationLogger:
    """Schreibt ein strukturiertes JSON-Lines-Logfile für eine Migration.

    Verwendung::

        with MigrationLogger("webserver01") as mlog:
            mlog.event("network_provisioned", network="VLAN100", vlan_id=100)
            mlog.event("disk_transfer", disk_id="disk-2000", size_gb=80)
        # __exit__ schreibt automatisch migration_end mit Dauer und Status

    Bei einer Exception innerhalb des ``with``-Blocks wird ``status="error"``
    geschrieben und die Ausnahme weitergeleitet.
    """

    def __init__(self, instance_name, log_dir=None):
        self._instance_name = instance_name
        self._log_dir = log_dir or getattr(
            getattr(CONF, "olvm", None), "migration_log_dir", None
        ) or _DEFAULT_LOG_DIR
        self._start_ts = None
        self._file = None
        self._lock = threading.Lock()
        self._log_path = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self._start_ts = datetime.datetime.now(datetime.timezone.utc)
        stamp = self._start_ts.strftime("%Y%m%d-%H%M%S")
        safe_name = _safe_filename(self._instance_name)
        filename = "%s_%s.log" % (safe_name, stamp)

        try:
            os.makedirs(self._log_dir, exist_ok=True)
        except OSError as exc:
            LOG.warning(
                "MigrationLogger: cannot create log dir %s: %s",
                self._log_dir, exc)
            return self

        self._log_path = os.path.join(self._log_dir, filename)
        try:
            self._file = open(self._log_path, "w", encoding="utf-8")
        except OSError as exc:
            LOG.warning(
                "MigrationLogger: cannot open log file %s: %s",
                self._log_path, exc)
            return self

        self._write_raw({
            "event": "migration_start",
            "instance": self._instance_name,
        })
        LOG.info("Migration log started: %s", self._log_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = None
        if self._start_ts:
            end_ts = datetime.datetime.now(datetime.timezone.utc)
            duration = round(
                (end_ts - self._start_ts).total_seconds(), 1)

        if exc_type is None:
            self._write_raw({
                "event": "migration_end",
                "status": "success",
                "duration_seconds": duration,
            })
            LOG.info(
                "Migration finished successfully in %.1fs  log=%s",
                duration or 0, self._log_path)
        else:
            self._write_raw({
                "event": "migration_end",
                "status": "error",
                "error": "%s: %s" % (exc_type.__name__, exc_val),
                "duration_seconds": duration,
            })
            LOG.error(
                "Migration FAILED after %.1fs  error=%s  log=%s",
                duration or 0, exc_val, self._log_path)

        if self._file:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None

        return False  # Ausnahme immer weiterleiten

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def event(self, event_name, **kwargs):
        """Schreibt ein Ereignis in das Logfile.

        :param event_name: Eindeutiger Ereignis-Name (snake_case)
        :param kwargs: Beliebige zusätzliche Felder
        """
        self._write_raw({"event": event_name, **kwargs})

    @property
    def log_path(self):
        """Absoluter Pfad zur aktuellen Logdatei (oder None)."""
        return self._log_path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_raw(self, payload):
        """Schreibt eine JSON-Zeile mit automatischem Timestamp."""
        ts = datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds")
        payload["ts"] = ts
        line = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            if self._file:
                try:
                    self._file.write(line + "\n")
                    self._file.flush()
                except OSError as exc:
                    LOG.warning("MigrationLogger write error: %s", exc)
            LOG.debug("migration_event: %s", line)
