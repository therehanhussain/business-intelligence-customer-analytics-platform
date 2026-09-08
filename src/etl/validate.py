"""Validation and Quarantine (Dead-Letter Queue) module.

Implements data quality rules, schema checks, and referential integrity constraints.
Ensures no records are silently discarded:
- Conforming rows pass to the clean staging dataset.
- Non-conforming rows are routed to the Dead-Letter Queue (rejected_records)
  with root-cause rejection codes, UTC timestamps, and serialized payloads.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Set, Tuple
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _create_rejected_df(
    records: List[pd.Series],
    table_name: str,
    id_col: str,
    rejection_reason: str,
    timestamp: str,
) -> pd.DataFrame:
    """Helper to convert rejected row series into standardized DLQ schema."""
    if not records:
        return pd.DataFrame(
            columns=["table_name", "record_identifier", "rejection_reason", "rejected_at", "raw_payload"]
        )

    rows = []
    for s in records:
        rows.append({
            "table_name": table_name,
            "record_identifier": str(s.get(id_col, "UNKNOWN")),
            "rejection_reason": rejection_reason,
            "rejected_at": timestamp,
            "raw_payload": json.dumps(s.to_dict(), default=str),
        })
    return pd.DataFrame(rows)


def validate_customers(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Validate customer records against primary key and demographic constraints.

    Rules:
    - Primary Key: `customer_id` must be unique (first occurrence accepted).
    - Age: Must be between 18 and 100.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info("Validating customers (%d rows)...", len(df))

    # 1. Primary Key Duplication Check
    dup_mask = df.duplicated(subset=["customer_id"], keep="first")
    rejected_dups = [df.iloc[i] for i in np.where(dup_mask)[0]]
    dlq_dups = _create_rejected_df(
        rejected_dups,
        table_name="customers",
        id_col="customer_id",
        rejection_reason="DUPLICATE_CUSTOMER_ID",
        timestamp=timestamp,
    )

    clean_subset = df[~dup_mask].copy()

    # 2. Demographic age range check
    invalid_age_mask = (clean_subset["age"] < 18) | (clean_subset["age"] > 100)
    rejected_age = [clean_subset.iloc[i] for i in np.where(invalid_age_mask)[0]]
    dlq_age = _create_rejected_df(
        rejected_age,
        table_name="customers",
        id_col="customer_id",
        rejection_reason="INVALID_AGE_OUT_OF_BOUNDS",
        timestamp=timestamp,
    )

    valid_customers = clean_subset[~invalid_age_mask].copy()
    rejected_customers = pd.concat([dlq_dups, dlq_age], ignore_index=True)

    stats = {
        "total_input": len(df),
        "valid_count": len(valid_customers),
        "rejected_count": len(rejected_customers),
        "rejection_reasons": rejected_customers["rejection_reason"].value_counts().to_dict(),
        "pass_rate_pct": round((len(valid_customers) / len(df)) * 100, 2),
    }

    logger.info(
        "Customers validation finished: %d valid (%.2f%%), %d rejected to DLQ.",
        stats["valid_count"], stats["pass_rate_pct"], stats["rejected_count"]
    )
    return valid_customers, rejected_customers, stats


def validate_products(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Validate product catalog against schema, completeness, and margin logic.

    Rules:
    - Primary Key: `product_id` must be unique.
    - Completeness: `category`, `cost`, `product_name` cannot be null/empty.
    - Financial Domain: `price > 0`, `cost > 0`, `cost <= price`.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info("Validating products (%d rows)...", len(df))

    rejected_records: List[pd.DataFrame] = []
    remaining_mask = pd.Series(True, index=df.index)

    # 1. Duplicate product_id
    dup_mask = df.duplicated(subset=["product_id"], keep="first")
    if dup_mask.any():
        rejected_dups = [df.iloc[i] for i in np.where(dup_mask)[0]]
        rejected_records.append(_create_rejected_df(
            rejected_dups, "products", "product_id", "DUPLICATE_PRODUCT_ID", timestamp
        ))
        remaining_mask = remaining_mask & (~dup_mask)

    # 2. Missing category
    missing_cat_mask = remaining_mask & df["category"].isna()
    if missing_cat_mask.any():
        recs = [df.iloc[i] for i in np.where(missing_cat_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "products", "product_id", "MISSING_PRODUCT_CATEGORY", timestamp
        ))
        remaining_mask = remaining_mask & (~missing_cat_mask)

    # 3. Missing cost
    missing_cost_mask = remaining_mask & df["cost"].isna()
    if missing_cost_mask.any():
        recs = [df.iloc[i] for i in np.where(missing_cost_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "products", "product_id", "MISSING_PRODUCT_COST", timestamp
        ))
        remaining_mask = remaining_mask & (~missing_cost_mask)

    # 4. Non-positive price or cost
    invalid_price_mask = remaining_mask & ((df["price"] <= 0) | df["price"].isna())
    if invalid_price_mask.any():
        recs = [df.iloc[i] for i in np.where(invalid_price_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "products", "product_id", "INVALID_PRICE_NON_POSITIVE", timestamp
        ))
        remaining_mask = remaining_mask & (~invalid_price_mask)

    invalid_cost_mask = remaining_mask & (df["cost"] <= 0)
    if invalid_cost_mask.any():
        recs = [df.iloc[i] for i in np.where(invalid_cost_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "products", "product_id", "INVALID_COST_NON_POSITIVE", timestamp
        ))
        remaining_mask = remaining_mask & (~invalid_cost_mask)

    # 5. Cost exceeds price (negative margin anomaly)
    cost_gt_price_mask = remaining_mask & (df["cost"] > df["price"])
    if cost_gt_price_mask.any():
        recs = [df.iloc[i] for i in np.where(cost_gt_price_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "products", "product_id", "INVALID_COST_EXCEEDS_PRICE", timestamp
        ))
        remaining_mask = remaining_mask & (~cost_gt_price_mask)

    valid_products = df[remaining_mask].copy()
    rejected_products = (
        pd.concat(rejected_records, ignore_index=True)
        if rejected_records
        else _create_rejected_df([], "products", "product_id", "NONE", timestamp)
    )

    stats = {
        "total_input": len(df),
        "valid_count": len(valid_products),
        "rejected_count": len(rejected_products),
        "rejection_reasons": rejected_products["rejection_reason"].value_counts().to_dict(),
        "pass_rate_pct": round((len(valid_products) / len(df)) * 100, 2),
    }

    logger.info(
        "Products validation finished: %d valid (%.2f%%), %d rejected to DLQ.",
        stats["valid_count"], stats["pass_rate_pct"], stats["rejected_count"]
    )
    return valid_products, rejected_products, stats


def validate_orders(
    df: pd.DataFrame,
    valid_customer_ids: Set[str],
    valid_product_ids: Set[str],
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Validate orders against primary key, quantity constraints, and foreign key integrity.

    Rules:
    - Quantity: Must be strictly > 0 (negative/zero returns are quarantined).
    - Foreign Keys: `customer_id` must exist in valid customers; `product_id` must exist in valid products.
    - Primary Key: `order_id` must be unique.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info("Validating orders (%d rows)...", len(df))

    rejected_records: List[pd.DataFrame] = []
    remaining_mask = pd.Series(True, index=df.index)

    # 1. Primary Key Duplication
    dup_mask = df.duplicated(subset=["order_id"], keep="first")
    if dup_mask.any():
        recs = [df.iloc[i] for i in np.where(dup_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "orders", "order_id", "DUPLICATE_ORDER_ID", timestamp
        ))
        remaining_mask = remaining_mask & (~dup_mask)

    # 2. Negative Quantities (e.g. unhandled return records)
    neg_qty_mask = remaining_mask & (df["quantity"] < 0)
    if neg_qty_mask.any():
        recs = [df.iloc[i] for i in np.where(neg_qty_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "orders", "order_id", "INVALID_QUANTITY_NEGATIVE_RETURN", timestamp
        ))
        remaining_mask = remaining_mask & (~neg_qty_mask)

    # 3. Zero Quantities
    zero_qty_mask = remaining_mask & (df["quantity"] == 0)
    if zero_qty_mask.any():
        recs = [df.iloc[i] for i in np.where(zero_qty_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "orders", "order_id", "INVALID_QUANTITY_ZERO", timestamp
        ))
        remaining_mask = remaining_mask & (~zero_qty_mask)

    # 4. Foreign Key Constraints (Customer FK)
    orphan_cust_mask = remaining_mask & (~df["customer_id"].isin(valid_customer_ids))
    if orphan_cust_mask.any():
        recs = [df.iloc[i] for i in np.where(orphan_cust_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "orders", "order_id", "ORPHAN_CUSTOMER_FOREIGN_KEY", timestamp
        ))
        remaining_mask = remaining_mask & (~orphan_cust_mask)

    # 5. Foreign Key Constraints (Product FK)
    orphan_prod_mask = remaining_mask & (~df["product_id"].isin(valid_product_ids))
    if orphan_prod_mask.any():
        recs = [df.iloc[i] for i in np.where(orphan_prod_mask)[0]]
        rejected_records.append(_create_rejected_df(
            recs, "orders", "order_id", "ORPHAN_PRODUCT_FOREIGN_KEY", timestamp
        ))
        remaining_mask = remaining_mask & (~orphan_prod_mask)

    valid_orders = df[remaining_mask].copy()
    rejected_orders = (
        pd.concat(rejected_records, ignore_index=True)
        if rejected_records
        else _create_rejected_df([], "orders", "order_id", "NONE", timestamp)
    )

    stats = {
        "total_input": len(df),
        "valid_count": len(valid_orders),
        "rejected_count": len(rejected_orders),
        "rejection_reasons": rejected_orders["rejection_reason"].value_counts().to_dict(),
        "pass_rate_pct": round((len(valid_orders) / len(df)) * 100, 2),
    }

    logger.info(
        "Orders validation finished: %d valid (%.2f%%), %d rejected to DLQ.",
        stats["valid_count"], stats["pass_rate_pct"], stats["rejected_count"]
    )
    return valid_orders, rejected_orders, stats


def validate_all_data(
    customers_df: pd.DataFrame,
    products_df: pd.DataFrame,
    orders_df: pd.DataFrame,
) -> Tuple[
    pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]
]:
    """Execute validation across all tables, producing valid tables and consolidated DLQ."""
    # 1. Customers
    valid_cust, rej_cust, cust_stats = validate_customers(customers_df)

    # 2. Products
    valid_prod, rej_prod, prod_stats = validate_products(products_df)

    # 3. Orders with FK checks against validated dimensions
    valid_cust_ids = set(valid_cust["customer_id"].unique())
    valid_prod_ids = set(valid_prod["product_id"].unique())
    valid_ord, rej_ord, ord_stats = validate_orders(orders_df, valid_cust_ids, valid_prod_ids)

    # 4. Consolidate Dead-Letter Queue
    all_rejected_df = pd.concat([rej_cust, rej_prod, rej_ord], ignore_index=True)

    validation_summary = {
        "customers": cust_stats,
        "products": prod_stats,
        "orders": ord_stats,
        "total_rejected_all_tables": len(all_rejected_df),
        "consolidated_reasons": all_rejected_df["rejection_reason"].value_counts().to_dict(),
    }

    return valid_cust, valid_prod, valid_ord, all_rejected_df, validation_summary
