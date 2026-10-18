import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager, contextmanager
from typing import List, Generator, AsyncGenerator
from config import LOG_FILE, DEBUG_MODE

# ANSI color codes for readable terminal debugging
COLORS = {
    "DEBUG": "\033[36m",    # Cyan
    "INFO": "\033[32m",     # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",    # Red
    "CRITICAL": "\033[35m", # Magenta
    "RESET": "\033[0m"
}

class ColoredConsoleFormatter(logging.Formatter):
    def format(self, record):
        levelname = record.levelname
        color = COLORS.get(levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        record.colored_level = f"{color}{levelname:<8}{reset}"
        return super().format(record)

_initialized = False

def setup_logging():
    global _initialized
    if _initialized:
        return
    _initialized = True

    root_logger = logging.getLogger("chai")
    root_logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

    # 1. Rotating File Handler (Plain text, max 5MB, keep 3 backups)
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # 2. Terminal Console Handler (Colored)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
    console_formatter = ColoredConsoleFormatter(
        "[%(asctime)s] %(colored_level)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

setup_logging()

def get_logger(name: str = "chai") -> logging.Logger:
    """Returns a namespaced logger child under 'chai'."""
    if name == "chai":
        return logging.getLogger("chai")
    return logging.getLogger(f"chai.{name}")

logger = get_logger("core")

@contextmanager
def measure_time(label: str) -> Generator[dict, None, None]:
    """Context manager to measure and log synchronous elapsed time."""
    start = time.perf_counter()
    metrics = {"start": start, "duration": 0.0}
    try:
        yield metrics
    finally:
        duration = time.perf_counter() - start
        metrics["duration"] = duration
        logger.debug(f"[Timing] {label}: {duration:.3f}s")

@asynccontextmanager
async def async_measure_time(label: str) -> AsyncGenerator[dict, None]:
    """Context manager to measure and log asynchronous elapsed time."""
    start = time.perf_counter()
    metrics = {"start": start, "duration": 0.0}
    try:
        yield metrics
    finally:
        duration = time.perf_counter() - start
        metrics["duration"] = duration
        logger.debug(f"[Timing] {label}: {duration:.3f}s")

def tail_logs(n: int = 25) -> List[str]:
    """Reads the last n lines from the chai.log file safely."""
    if not LOG_FILE.exists():
        return ["Log file does not exist yet."]
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return lines[-n:] if len(lines) > n else lines
    except Exception as e:
        return [f"Failed to read logs: {str(e)}"]
