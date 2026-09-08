"""Filesystem path definitions for the Customer Analytics Platform."""

from pathlib import Path
from typing import List


# Project root directory (3 levels up from src/config/paths.py)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# Core subdirectories
SRC_DIR: Path = PROJECT_ROOT / "src"
CONFIG_DIR: Path = SRC_DIR / "config"
ETL_DIR: Path = SRC_DIR / "etl"
ANALYTICS_DIR: Path = SRC_DIR / "analytics"
MODELING_DIR: Path = SRC_DIR / "modeling"
UTILS_DIR: Path = SRC_DIR / "utils"

DATA_DIR: Path = PROJECT_ROOT / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"

SQL_DIR: Path = PROJECT_ROOT / "sql"
TESTS_DIR: Path = PROJECT_ROOT / "tests"
NOTEBOOKS_DIR: Path = PROJECT_ROOT / "notebooks"
DASHBOARD_DIR: Path = PROJECT_ROOT / "dashboard"
DOCS_DIR: Path = PROJECT_ROOT / "docs"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# Config and environment file paths
DEFAULT_CONFIG_PATH: Path = CONFIG_DIR / "config.yaml"
DEFAULT_ENV_PATH: Path = PROJECT_ROOT / ".env"
DEFAULT_LOG_FILE: Path = LOGS_DIR / "app.log"


def ensure_directories() -> List[Path]:
    """Ensure all required runtime directories exist."""
    directories = [
        DATA_DIR,
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        LOGS_DIR,
        SQL_DIR,
        TESTS_DIR,
        NOTEBOOKS_DIR,
        DASHBOARD_DIR,
        DOCS_DIR,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    return directories
