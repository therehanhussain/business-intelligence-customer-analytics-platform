"""Extraction module for the Customer Analytics Platform.

Responsible for ingesting raw tabular extracts (customers, products, orders)
from the immutable raw data storage layer with input validation, file existence
checks, and metadata tracking.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from src.config.paths import RAW_DATA_DIR
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RawDataExtractionError(Exception):
    """Raised when extraction of raw source files fails."""
    pass


def extract_raw_table(file_path: Path, table_name: str) -> pd.DataFrame:
    """Extract a single raw CSV file and attach extraction metadata.

    Args:
        file_path: Path to the raw CSV file.
        table_name: Logical name of the source table.

    Returns:
        pd.DataFrame containing the raw data.

    Raises:
        RawDataExtractionError: If the file does not exist or cannot be parsed.
    """
    if not file_path.exists():
        error_msg = f"Source file for '{table_name}' not found at: {file_path}"
        logger.error(error_msg)
        raise RawDataExtractionError(error_msg)

    try:
        logger.info("Extracting %s from %s...", table_name, file_path)
        df = pd.read_csv(file_path, low_memory=False)
        logger.info("Successfully extracted %s: %d rows, %d columns.", table_name, len(df), len(df.columns))
        return df
    except Exception as err:
        error_msg = f"Failed to parse '{table_name}' from {file_path}: {err}"
        logger.error(error_msg)
        raise RawDataExtractionError(error_msg) from err


def extract_all_raw_data(
    raw_dir: Path = RAW_DATA_DIR,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, any]]:
    """Extract all raw retail source datasets and return dataframes with metadata.

    Returns:
        Tuple of (customers_df, products_df, orders_df, extraction_metadata)
    """
    extraction_timestamp = datetime.now(timezone.utc).isoformat()
    logger.info("Initiating raw data extraction pipeline at %s...", extraction_timestamp)

    customers_path = raw_dir / "customers.csv"
    products_path = raw_dir / "products.csv"
    orders_path = raw_dir / "orders.csv"

    customers_raw = extract_raw_table(customers_path, "customers")
    products_raw = extract_raw_table(products_path, "products")
    orders_raw = extract_raw_table(orders_path, "orders")

    metadata = {
        "extracted_at": extraction_timestamp,
        "raw_directory": str(raw_dir),
        "source_counts": {
            "customers": len(customers_raw),
            "products": len(products_raw),
            "orders": len(orders_raw),
        },
    }

    logger.info("Raw data extraction phase completed successfully.")
    return customers_raw, products_raw, orders_raw, metadata


if __name__ == "__main__":
    cust_df, prod_df, ord_df, meta = extract_all_raw_data()
    print("Extraction Summary:", meta)
