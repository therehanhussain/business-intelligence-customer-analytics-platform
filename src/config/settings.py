"""Configuration loader and settings dataclasses."""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.config.paths import DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH

# Optional third-party imports with graceful fallbacks
try:
    from dotenv import load_dotenv

    _DOTENV_AVAILABLE = True
except ImportError:
    _DOTENV_AVAILABLE = False

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


@dataclass
class DatabaseConfig:
    """Relational database connection parameters."""

    host: str = "localhost"
    port: int = 5432
    name: str = "customer_analytics"
    user: str = "postgres"
    password: Optional[str] = None
    schema: str = "public"

    def get_connection_url(self, masked: bool = False) -> str:
        """Construct a SQLAlchemy-compatible PostgreSQL connection string.

        Args:
            masked: If True, replace the password with asterisks for safe logging.
        """
        pwd = self.password or ""
        display_pwd = "********" if (masked and pwd) else pwd
        auth = f"{self.user}:{display_pwd}" if pwd else self.user
        return f"postgresql://{auth}@{self.host}:{self.port}/{self.name}"


@dataclass
class LoggingConfig:
    """Logging module settings."""

    level: str = "INFO"
    format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    file_logging: bool = True
    file_name: str = "app.log"


@dataclass
class AnalyticsConfig:
    """Business analytics and modeling parameters."""

    rfm_recency_weight: float = 0.33
    rfm_frequency_weight: float = 0.33
    rfm_monetary_weight: float = 0.34
    segmentation_clusters: int = 4
    churn_inactivity_days: int = 90
    test_size: float = 0.2


@dataclass
class AppConfig:
    """Top-level application configuration."""

    project_name: str = "customer-analytics-platform"
    version: str = "0.1.0"
    environment: str = "development"
    random_seed: int = 42
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)


def _load_yaml_file(filepath: Path) -> Dict[str, Any]:
    """Safely load a YAML configuration file if PyYAML is installed."""
    if not filepath.exists() or not _YAML_AVAILABLE:
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}


def load_config(
    config_file: Optional[Path] = None,
    env_file: Optional[Path] = None,
) -> AppConfig:
    """Load configuration from config.yaml and environment variables.

    Hierarchy of settings (highest to lowest priority):
    1. Environment variables (os.environ or .env file)
    2. YAML configuration file (config.yaml)
    3. Dataclass defaults
    """
    cfg_path = config_file or DEFAULT_CONFIG_PATH
    dot_path = env_file or DEFAULT_ENV_PATH

    # Load environment variables from .env if available
    if _DOTENV_AVAILABLE and dot_path.exists():
        load_dotenv(dotenv_path=dot_path, override=False)

    yaml_data = _load_yaml_file(cfg_path)
    proj_yaml = yaml_data.get("project", {})
    db_yaml = yaml_data.get("database", {})
    log_yaml = yaml_data.get("logging", {})
    analytics_yaml = yaml_data.get("analytics", {})

    db_config = DatabaseConfig(
        host=os.getenv("DB_HOST", db_yaml.get("host", "localhost")),
        port=int(os.getenv("DB_PORT", db_yaml.get("port", 5432))),
        name=os.getenv("DB_NAME", db_yaml.get("name", "customer_analytics")),
        user=os.getenv("DB_USER", db_yaml.get("user", "postgres")),
        password=os.getenv("DB_PASSWORD"),
        schema=os.getenv("DB_SCHEMA", db_yaml.get("schema", "public")),
    )

    log_config = LoggingConfig(
        level=os.getenv("LOG_LEVEL", log_yaml.get("level", "INFO")).upper(),
        format=log_yaml.get(
            "format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ),
        file_logging=bool(log_yaml.get("file_logging", True)),
        file_name=log_yaml.get("file_name", "app.log"),
    )

    rfm_yaml = analytics_yaml.get("rfm", {})
    seg_yaml = analytics_yaml.get("segmentation", {})
    churn_yaml = analytics_yaml.get("churn_prediction", {})

    analytics_config = AnalyticsConfig(
        rfm_recency_weight=float(rfm_yaml.get("recency_weight", 0.33)),
        rfm_frequency_weight=float(rfm_yaml.get("frequency_weight", 0.33)),
        rfm_monetary_weight=float(rfm_yaml.get("monetary_weight", 0.34)),
        segmentation_clusters=int(seg_yaml.get("n_clusters", 4)),
        churn_inactivity_days=int(churn_yaml.get("inactivity_days_threshold", 90)),
        test_size=float(churn_yaml.get("test_size", 0.2)),
    )

    app_config = AppConfig(
        project_name=proj_yaml.get("name", "customer-analytics-platform"),
        version=proj_yaml.get("version", "0.1.0"),
        environment=os.getenv("APP_ENV", "development"),
        random_seed=int(os.getenv("RANDOM_SEED", proj_yaml.get("random_seed", 42))),
        database=db_config,
        logging=log_config,
        analytics=analytics_config,
    )

    return app_config


# Cached default settings instance
settings: AppConfig = load_config()
