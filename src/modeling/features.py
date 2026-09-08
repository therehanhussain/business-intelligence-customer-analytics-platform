"""Customer-level feature engineering module.

Constructs comprehensive behavioral, monetary, tenure, and recency features.
Includes cutoff-aware feature extraction to strictly guarantee ZERO data leakage
in time-aware predictive modeling.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


def build_customer_features(
    orders_df: pd.DataFrame,
    customers_df: pd.DataFrame,
    products_df: pd.DataFrame,
    cutoff_date: Optional[str] = None,
    recent_window_days: int = 90,
) -> pd.DataFrame:
    """Build customer-level behavioral and monetary features up to an optional cutoff date.

    ANTI-LEAKAGE GUARANTEE:
    When cutoff_date is provided, only orders with order_date <= cutoff_date and
    customers with signup_date <= cutoff_date are evaluated.
    Recency is calculated relative to cutoff_date.

    Args:
        orders_df: Validated orders dataframe (order_id, customer_id, product_id, order_date, quantity, order_status, payment_method)
        customers_df: Validated customers dataframe (customer_id, name, gender, age, city, state, signup_date, is_age_imputed)
        products_df: Validated products catalog (product_id, price, cost)
        cutoff_date: Optional ISO date string (YYYY-MM-DD). If None, evaluates across full history relative to max order_date.
        recent_window_days: Days prior to cutoff considered 'recent' (default: 90 days).

    Returns:
        pd.DataFrame containing one row per customer with engineered behavioral features.
    """
    logger.info("Building customer features (cutoff_date=%s, recent_window=%dd)...", cutoff_date, recent_window_days)

    # 1. Enforce Cutoff Filter
    if cutoff_date is not None:
        effective_date = pd.to_datetime(cutoff_date)
        ords = orders_df[pd.to_datetime(orders_df["order_date"]) <= effective_date].copy()
        custs = customers_df[pd.to_datetime(customers_df["signup_date"]) <= effective_date].copy()
    else:
        effective_date = pd.to_datetime(orders_df["order_date"]).max()
        ords = orders_df.copy()
        custs = customers_df.copy()

    recent_cutoff_date = effective_date - pd.Timedelta(days=recent_window_days)

    # 2. Enrich Orders with Product Pricing
    ords = ords.merge(
        products_df[["product_id", "price", "cost"]],
        on="product_id",
        how="left",
    )
    ords["order_datetime"] = pd.to_datetime(ords["order_date"])
    ords["gross_rev"] = ords["quantity"] * ords["price"]
    ords["gross_profit"] = (ords["price"] - ords["cost"]) * ords["quantity"]

    ords["is_completed"] = ords["order_status"].isin(["Completed", "Shipped"])
    ords["is_refunded"] = ords["order_status"] == "Refunded"
    ords["is_cancelled"] = ords["order_status"] == "Cancelled"
    ords["is_recent"] = ords["order_datetime"] > recent_cutoff_date

    # 3. Customer-Level Grouped Aggregations
    # All orders aggregations
    all_agg = ords.groupby("customer_id").agg(
        first_order_date=("order_datetime", "min"),
        last_order_date=("order_datetime", "max"),
        total_orders=("order_id", "count"),
        total_gross_revenue=("gross_rev", "sum"),
        active_months=("order_date", lambda s: len(set(s.str.slice(0, 7)))),
        refund_count=("is_refunded", "sum"),
        refund_amount=("gross_rev", lambda s: s[ords.loc[s.index, "is_refunded"]].sum()),
        cancellation_count=("is_cancelled", "sum"),
        cancellation_amount=("gross_rev", lambda s: s[ords.loc[s.index, "is_cancelled"]].sum()),
    )

    # Completed commercial orders aggregations
    comp_ords = ords[ords["is_completed"]].copy()
    comp_agg = comp_ords.groupby("customer_id").agg(
        completed_orders=("order_id", "count"),
        total_units=("quantity", "sum"),
        total_revenue=("gross_rev", "sum"),
        total_profit=("gross_profit", "sum"),
        last_completed_order_date=("order_datetime", "max"),
        first_completed_order_date=("order_datetime", "min"),
        recent_order_count=("is_recent", "sum"),
        recent_revenue=("gross_rev", lambda s: s[comp_ords.loc[s.index, "is_recent"]].sum()),
    )

    # 4. Assemble Customer Feature DataFrame
    features = custs.copy()
    features = features.merge(all_agg, on="customer_id", how="left")
    features = features.merge(comp_agg, on="customer_id", how="left")

    # Fill NaNs for inactive / zero-order customers
    numeric_fill_zero = [
        "total_orders", "total_gross_revenue", "active_months",
        "refund_count", "refund_amount", "cancellation_count", "cancellation_amount",
        "completed_orders", "total_units", "total_revenue", "total_profit",
        "recent_order_count", "recent_revenue"
    ]
    for col in numeric_fill_zero:
        features[col] = features[col].fillna(0)

    # 5. Derived Features
    # Recency (days since last completed order relative to cutoff)
    features["recency_days"] = (
        (effective_date - features["last_completed_order_date"]).dt.days
    ).fillna(999).astype(int)

    # Customer Lifetime Days (tenure span between first and last order)
    features["customer_lifetime_days"] = (
        (features["last_order_date"] - features["first_order_date"]).dt.days
    ).fillna(0).astype(int)

    # Account Age (days from signup to cutoff)
    features["account_age_days"] = (
        (effective_date - pd.to_datetime(features["signup_date"])).dt.days
    ).astype(int)

    # Average Order Value (AOV)
    features["average_order_value"] = np.where(
        features["completed_orders"] > 0,
        (features["total_revenue"] / features["completed_orders"]).round(2),
        0.0
    )

    # Average Order Frequency (orders per 30 days of tenure)
    features["order_frequency_monthly"] = np.where(
        features["account_age_days"] > 0,
        (features["completed_orders"] / (features["account_age_days"] / 30.0)).round(3),
        0.0
    )

    # Realized Gross Margin %
    features["gross_margin_pct"] = np.where(
        features["total_revenue"] > 0,
        ((features["total_profit"] / features["total_revenue"]) * 100.0).round(2),
        0.0
    )

    # Refund Rate & Cancellation Rate
    features["refund_rate"] = np.where(
        features["total_orders"] > 0,
        (features["refund_count"] / features["total_orders"]).round(4),
        0.0
    )
    features["cancellation_rate"] = np.where(
        features["total_orders"] > 0,
        (features["cancellation_count"] / features["total_orders"]).round(4),
        0.0
    )

    # Recent vs Historical Dynamics
    features["historical_revenue"] = (features["total_revenue"] - features["recent_revenue"]).clip(lower=0)
    features["historical_order_count"] = (features["completed_orders"] - features["recent_order_count"]).clip(lower=0)

    features["recent_revenue_ratio"] = np.where(
        features["total_revenue"] > 0,
        (features["recent_revenue"] / features["total_revenue"]).round(4),
        0.0
    )
    features["recent_order_ratio"] = np.where(
        features["completed_orders"] > 0,
        (features["recent_order_count"] / features["completed_orders"]).round(4),
        0.0
    )

    # Normalized Revenue Momentum / Trend
    # Positive = accelerating spend; Negative = declining spend
    features["revenue_trend"] = np.where(
        features["total_revenue"] > 0,
        ((features["recent_revenue"] - (features["historical_revenue"] / 3.0)) / (features["total_revenue"] + 10.0)).round(4),
        0.0
    )

    # Format dates as string
    features["first_order_date"] = features["first_order_date"].dt.strftime("%Y-%m-%d").fillna("")
    features["last_order_date"] = features["last_order_date"].dt.strftime("%Y-%m-%d").fillna("")
    features["last_completed_order_date"] = features["last_completed_order_date"].dt.strftime("%Y-%m-%d").fillna("")

    logger.info("Successfully extracted %d customer feature rows.", len(features))
    return features


def build_time_aware_churn_dataset(
    orders_df: pd.DataFrame,
    customers_df: pd.DataFrame,
    products_df: pd.DataFrame,
    feature_cutoff: str,
    outcome_start: str,
    outcome_end: str,
    recent_window_days: int = 90,
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, Any]]:
    """Construct an out-of-time (OOT) feature matrix and churn label with zero data leakage.

    Eligibility:
    Only customers who made at least one completed/shipped purchase ON OR BEFORE
    the feature_cutoff date are eligible for churn evaluation.

    Target Label:
    is_churned = 1 if the customer made ZERO completed/shipped orders during
    [outcome_start, outcome_end], and 0 otherwise.

    Returns:
        Tuple of (feature_dataframe, target_series, metadata_dict)
    """
    logger.info(
        "Constructing OOT dataset (Feature Cutoff: %s | Outcome Window: %s to %s)...",
        feature_cutoff, outcome_start, outcome_end
    )

    # 1. Generate Cutoff-Safe Features
    features_df = build_customer_features(
        orders_df=orders_df,
        customers_df=customers_df,
        products_df=products_df,
        cutoff_date=feature_cutoff,
        recent_window_days=recent_window_days,
    )

    # 2. Filter to Eligible Customers (those with at least 1 completed order prior to cutoff)
    eligible_mask = features_df["completed_orders"] >= 1
    eligible_features = features_df[eligible_mask].copy().reset_index(drop=True)
    eligible_cust_ids = set(eligible_features["customer_id"])

    # 3. Determine Churn Outcome in Horizon Window [outcome_start, outcome_end]
    horizon_ords = orders_df[
        (orders_df["order_date"] >= outcome_start)
        & (orders_df["order_date"] <= outcome_end)
        & (orders_df["order_status"].isin(["Completed", "Shipped"]))
    ]
    retained_cust_ids = set(horizon_ords["customer_id"]).intersection(eligible_cust_ids)

    # Target: 1 = Churned (No purchase in horizon), 0 = Retained (>= 1 purchase in horizon)
    y_series = pd.Series(
        np.where(eligible_features["customer_id"].isin(retained_cust_ids), 0, 1),
        index=eligible_features.index,
        name="is_churned",
    )

    churn_count = int(y_series.sum())
    retained_count = int((y_series == 0).sum())
    churn_rate = round((churn_count / len(y_series)) * 100.0, 2)

    meta = {
        "feature_cutoff": feature_cutoff,
        "outcome_start": outcome_start,
        "outcome_end": outcome_end,
        "eligible_customers": len(eligible_features),
        "churned_customers": churn_count,
        "retained_customers": retained_count,
        "churn_rate_pct": churn_rate,
        "imbalance_ratio": round(churn_count / max(1, retained_count), 2),
    }

    logger.info(
        "OOT dataset complete: %d customers, %d churned (%.2f%%), %d retained.",
        len(eligible_features), churn_count, churn_rate, retained_count
    )
    return eligible_features, y_series, meta
