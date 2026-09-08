"""Loading module for the Customer Analytics Platform.

Persists validated clean datasets and Dead-Letter Queue (DLQ) rejected records:
1. File-based storage in `data/processed/` (clean CSVs & audit logs).
2. Relational database loading via SQLAlchemy:
   - Attempts direct PostgreSQL connection.
   - If PostgreSQL is offline/unavailable, gracefully falls back to a local SQLite
     staging warehouse database (`data/processed/staging.db`) without fabricating
     results or failing the pipeline.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.config.paths import PROCESSED_DATA_DIR, ensure_directories
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


def save_processed_files(
    valid_customers: pd.DataFrame,
    valid_products: pd.DataFrame,
    valid_orders: pd.DataFrame,
    rejected_records: pd.DataFrame,
    audit_summary: Dict[str, Any],
    output_dir: Path = PROCESSED_DATA_DIR,
) -> Dict[str, Path]:
    """Persist validated datasets, rejected records, and audit JSON to disk."""
    ensure_directories()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Persisting validated datasets to %s...", output_dir)

    paths = {
        "customers": output_dir / "customers_clean.csv",
        "products": output_dir / "products_clean.csv",
        "orders": output_dir / "orders_clean.csv",
        "rejected_records": output_dir / "rejected_records.csv",
        "audit_summary": output_dir / "etl_audit_summary.json",
    }

    valid_customers.to_csv(paths["customers"], index=False)
    valid_products.to_csv(paths["products"], index=False)
    valid_orders.to_csv(paths["orders"], index=False)
    rejected_records.to_csv(paths["rejected_records"], index=False)

    with open(paths["audit_summary"], "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2, default=str)

    logger.info("Processed CSVs and audit summary successfully written to disk.")
    return paths


def get_database_engine() -> Tuple[Engine, str]:
    """Initialize database engine, connecting to PostgreSQL or staging SQLite.

    Returns:
        Tuple of (SQLAlchemy Engine, db_type_label)
    """
    pg_url = settings.database.get_connection_url(masked=False)
    masked_url = settings.database.get_connection_url(masked=True)

    try:
        # Test PostgreSQL connection with 2-second timeout
        logger.info("Attempting connection to PostgreSQL at %s...", masked_url)
        pg_engine = create_engine(pg_url, connect_args={"connect_timeout": 2})
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Successfully established live PostgreSQL connection.")
        return pg_engine, "PostgreSQL"
    except Exception as err:
        logger.info(
            "PostgreSQL is not reachable (%s). Activating local SQLite staging warehouse engine...",
            err.__class__.__name__,
        )
        sqlite_path = PROCESSED_DATA_DIR / "staging.db"
        sqlite_url = f"sqlite:///{sqlite_path.as_posix()}"
        sqlite_engine = create_engine(sqlite_url)
        return sqlite_engine, "SQLite (Staging)"


def load_to_database(
    valid_customers: pd.DataFrame,
    valid_products: pd.DataFrame,
    valid_orders: pd.DataFrame,
    rejected_records: pd.DataFrame,
    audit_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Load validated data, Dead-Letter Queue records, and audit log into database."""
    engine, db_type = get_database_engine()
    logger.info("Loading tables into %s database...", db_type)

    load_metadata = {
        "database_type": db_type,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
        "tables_loaded": {},
    }

    # 1. Load Valid Customers
    valid_customers.to_sql("customers", con=engine, if_exists="replace", index=False, chunksize=5000)
    load_metadata["tables_loaded"]["customers"] = len(valid_customers)

    # 2. Load Valid Products
    valid_products.to_sql("products", con=engine, if_exists="replace", index=False)
    load_metadata["tables_loaded"]["products"] = len(valid_products)

    # 3. Load Valid Orders
    valid_orders.to_sql("orders", con=engine, if_exists="replace", index=False, chunksize=10000)
    load_metadata["tables_loaded"]["orders"] = len(valid_orders)

    # 4. Load Dead-Letter Queue (Rejected Records)
    rejected_records.to_sql("rejected_records", con=engine, if_exists="replace", index=False, chunksize=5000)
    load_metadata["tables_loaded"]["rejected_records"] = len(rejected_records)

    # 5. Load Pipeline Audit Log
    audit_row = pd.DataFrame([{
        "pipeline_run_id": audit_summary.get("pipeline_run_id"),
        "run_timestamp": audit_summary.get("run_timestamp"),
        "database_type": db_type,
        "total_extracted": audit_summary.get("extraction", {}).get("total_extracted"),
        "total_valid": audit_summary.get("validation", {}).get("total_valid"),
        "total_rejected": audit_summary.get("validation", {}).get("total_rejected"),
        "pass_rate_pct": audit_summary.get("validation", {}).get("overall_pass_rate_pct"),
        "audit_json": json.dumps(audit_summary, default=str),
    }])
    audit_row.to_sql("pipeline_audit_log", con=engine, if_exists="append", index=False)
    load_metadata["tables_loaded"]["pipeline_audit_log"] = len(audit_row)

    logger.info("Database loading completed successfully for %s.", db_type)
    return load_metadata
