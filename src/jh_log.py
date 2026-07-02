"""
Central logging for Job Hunter AI.

Every module obtains its logger via:

    from jh_log import get_logger
    logger = get_logger(__name__)

Behaviour:
  * DEBUG and above go to a rotating log file in the user's AppData folder
    (%APPDATA%/Job Hunter AI/job_hunter.log, 1 MB x 3 backups) so end users
    can attach logs to bug reports.
  * INFO and above are mirrored to the console when one exists (dev runs);
    silently skipped under pythonw/PyInstaller windowed builds where
    sys.stderr is None.
  * Configuration happens lazily on the first get_logger() call and is
    idempotent -- safe regardless of module import order.
"""

import logging
import logging.handlers
import os
import sys

# Same location convention as jh_storage_manager.APPDATA_DIR (duplicated on
# purpose: jh_log must stay import-dependency-free so every module can use it).
APPDATA_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "Job Hunter AI"
)
LOG_FILE = os.path.join(APPDATA_DIR, "job_hunter.log")

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(funcName)s:%(lineno)d | %(message)s"

# Parent logger for the whole application; module loggers hang off it.
_app_logger = logging.getLogger("jobhunter")


def _configure() -> None:
    """Attach handlers once. Presence of handlers doubles as the guard flag."""
    if _app_logger.handlers:
        return
    _app_logger.setLevel(logging.DEBUG)
    _app_logger.propagate = False  # don't leak into the root logger
    formatter = logging.Formatter(_FORMAT)

    # File handler: never let logging setup crash the app (read-only profile,
    # full disk, AV lock, ...) -- fall back to console-only operation.
    try:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        _app_logger.addHandler(file_handler)
    except OSError:
        pass

    # Console mirror for development runs. sys.stderr is None in windowed
    # builds (pythonw / PyInstaller --noconsole); StreamHandler would raise
    # on emit, so only attach when a real stream exists.
    if sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        _app_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger namespaced under 'jobhunter'."""
    _configure()
    short = name.rsplit(".", 1)[-1]
    if short in ("__main__", "jobhunter", ""):
        return _app_logger
    return logging.getLogger(f"jobhunter.{short}")
