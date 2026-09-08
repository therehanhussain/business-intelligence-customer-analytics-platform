"""RFM (Recency, Frequency, Monetary) Customer Segmentation Module.

Calculates statistical quintile RFM scores and maps customers into actionable,
mutually exclusive commercial lifecycle segments.
"""

from typing import Any, Dict, Tuple
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


def calculate_rfm_scores(features_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate statistical quintile RFM scores (1 to 5) for all customer accounts.

    Methodology:
    - Unactivated accounts (0 completed orders): Assigned R=0, F=0, M=0, Score='000'.
    - Active paying accounts (>= 1 completed orders):
        * Recency (R): Inverted rank percentile (lowest days since purchase = score 5).
        * Frequency (F): Completed orders rank percentile (highest orders = score 5).
        * Monetary (M): Net realized revenue rank percentile (highest spend = score 5).

    Returns:
        pd.DataFrame containing original features with r_score, f_score, m_score, rfm_score, and customer_segment.
    """
    logger.info("Computing RFM quintiles across %d customer profiles...", len(features_df))
    df = features_df.copy()

    # Mask for paying customers vs unactivated
    paying_mask = df["completed_orders"] > 0

    # Initialize scores to 0
    df["r_score"] = 0
    df["f_score"] = 0
    df["m_score"] = 0
    df["rfm_score"] = "000"

    paying_df = df[paying_mask].copy()

    # 1. Recency Score (1-5: lower recency_days -> higher score)
    # Using rank percentile to prevent bin collision on tied boundaries
    r_pct = 1.0 - paying_df["recency_days"].rank(pct=True, method="average")
    df.loc[paying_mask, "r_score"] = pd.cut(
        r_pct,
        bins=[-0.01, 0.20, 0.40, 0.60, 0.80, 1.01],
        labels=[1, 2, 3, 4, 5],
    ).astype(int)

    # 2. Frequency Score (1-5: higher completed_orders -> higher score)
    f_pct = paying_df["completed_orders"].rank(pct=True, method="average")
    df.loc[paying_mask, "f_score"] = pd.cut(
        f_pct,
        bins=[-0.01, 0.20, 0.40, 0.60, 0.80, 1.01],
        labels=[1, 2, 3, 4, 5],
    ).astype(int)

    # 3. Monetary Score (1-5: higher total_revenue -> higher score)
    m_pct = paying_df["total_revenue"].rank(pct=True, method="average")
    df.loc[paying_mask, "m_score"] = pd.cut(
        m_pct,
        bins=[-0.01, 0.20, 0.40, 0.60, 0.80, 1.01],
        labels=[1, 2, 3, 4, 5],
    ).astype(int)

    # Combined RFM Score String
    df["rfm_score"] = (
        df["r_score"].astype(str) + df["f_score"].astype(str) + df["m_score"].astype(str)
    )

    # 4. Segment Assignment
    df["customer_segment"] = df.apply(_assign_rfm_segment, axis=1)

    logger.info("RFM segmentation completed across %d accounts.", len(df))
    return df


def _assign_rfm_segment(row: pd.Series) -> str:
    """Assign mutually exclusive business segment based on RFM score."""
    r = int(row["r_score"])
    f = int(row["f_score"])
    m = int(row["m_score"])

    # Zero orders
    if f == 0 or row["completed_orders"] == 0:
        return "Inactive / Unactivated"

    # Top VIPs: High recency, high frequency, high spend
    if r >= 4 and f >= 4 and m >= 4:
        return "Champions"

    # Cannot Lose Them: Top historical value but severely dormant
    if r == 1 and f >= 4 and m >= 4:
        return "Cannot Lose Them"

    # At Risk: Previously solid frequency/spend but cooling down
    if r <= 2 and f >= 3 and m >= 3:
        return "At Risk"

    # Loyal Customers: Steady, consistent repeat shoppers
    if r >= 3 and f >= 3 and m >= 3:
        return "Loyal Customers"

    # Potential Loyalists: Recent repeat buyers ready for cross-sell
    if r >= 4 and f in [2, 3]:
        return "Potential Loyalists"

    # New Customers: Recent single purchase
    if r >= 4 and f == 1:
        return "New Customers"

    # Hibernating: Inactive, low spend, low frequency
    if r <= 2 and f <= 2 and m <= 2:
        return "Hibernating"

    # Promising / Need Attention: Moderate middle-ground scores
    return "Promising"


def summarize_rfm_segments(rfm_df: pd.DataFrame) -> pd.DataFrame:
    """Generate business scorecard summarizing customer counts, revenue, profit, and averages per segment."""
    summary = rfm_df.groupby("customer_segment").agg(
        customer_count=("customer_id", "count"),
        total_revenue=("total_revenue", "sum"),
        total_profit=("total_profit", "sum"),
        avg_revenue_per_customer=("total_revenue", "mean"),
        avg_completed_orders=("completed_orders", "mean"),
        avg_recency_days=("recency_days", "mean"),
    ).reset_index()

    total_customers = len(rfm_df)
    total_revenue = summary["total_revenue"].sum()

    summary["pct_of_customers"] = (summary["customer_count"] * 100.0 / total_customers).round(2)
    summary["pct_of_revenue"] = (summary["total_revenue"] * 100.0 / max(total_revenue, 1.0)).round(2)
    summary["avg_revenue_per_customer"] = summary["avg_revenue_per_customer"].round(2)
    summary["avg_completed_orders"] = summary["avg_completed_orders"].round(1)
    summary["avg_recency_days"] = summary["avg_recency_days"].round(1)
    summary["total_revenue"] = summary["total_revenue"].round(2)
    summary["total_profit"] = summary["total_profit"].round(2)

    # Sort logically by commercial revenue impact
    summary = summary.sort_values(by="total_revenue", ascending=False).reset_index(drop=True)
    return summary
