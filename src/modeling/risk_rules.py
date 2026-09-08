"""Rule-Based Baseline Customer Risk & Churn Scoring Module.

Implements an interpretable, multi-factor rule engine mapping behavioral telemetry
into a composite risk score (0 to 100), categorical risk tiers (LOW, MEDIUM, HIGH, CRITICAL),
root-cause explanations, and recommended commercial actions.
"""

from typing import Any, Dict, Tuple
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


def apply_risk_rules(features_df: pd.DataFrame) -> pd.DataFrame:
    """Calculate transparent, multi-factor baseline risk scores and action playbooks.

    Scoring Dimensions:
    1. Recency Decay Penalty (Up to 40 pts):
       - > 365 days: 40 pts
       - 181 to 365 days: 25 pts
       - 91 to 180 days: 15 pts
       - <= 90 days: 0 pts
    2. Frequency Slowdown Penalty (Up to 25 pts):
       - Historical orders >= 5 with 0 recent orders: 25 pts
       - Historical orders 2-4 with 0 recent orders: 15 pts
    3. High-Value Account Inactivity Penalty (Up to 20 pts):
       - Total revenue > $3,000 with recency > 90 days: 20 pts
       - Total revenue $1,500-$3,000 with recency > 90 days: 10 pts
    4. Return & Fulfillment Friction (Up to 15 pts):
       - Refund rate > 15%: 15 pts
       - Cancellation rate > 15%: 10 pts
    5. Unactivated Penalty:
       - 0 completed orders: Base score 85 pts (Immediate Critical onboarding risk)

    Risk Levels:
    - CRITICAL : 75 - 100
    - HIGH     : 50 - 74
    - MEDIUM   : 25 - 49
    - LOW      :  0 - 24

    Returns:
        pd.DataFrame containing risk_score, risk_level, key_risk_driver, and recommended_action.
    """
    logger.info("Evaluating rule-based risk engine across %d customer records...", len(features_df))
    df = features_df.copy()

    risk_scores = np.zeros(len(df), dtype=float)
    primary_drivers = []
    recommended_actions = []

    for idx, row in df.iterrows():
        score = 0.0
        reasons = []

        completed_ords = row["completed_orders"]
        recency = row["recency_days"]
        hist_ords = row.get("historical_order_count", 0)
        recent_ords = row.get("recent_order_count", 0)
        revenue = row["total_revenue"]
        refund_rate = row.get("refund_rate", 0.0)

        # 1. Unactivated customer check
        if completed_ords == 0:
            score = 85.0
            reasons.append("Unactivated Account (0 Completed Purchases)")
        else:
            # 2. Recency Penalty
            if recency > 365:
                score += 40.0
                reasons.append("Severe Inactivity (>365 Days)")
            elif recency > 180:
                score += 25.0
                reasons.append("High Inactivity (181-365 Days)")
            elif recency > 90:
                score += 15.0
                reasons.append("Cooling Purchase Cadence (91-180 Days)")

            # 3. Frequency Slowdown Penalty
            if hist_ords >= 5 and recent_ords == 0:
                score += 25.0
                reasons.append("Discontinued Repeat Purchase Cadence")
            elif hist_ords >= 2 and recent_ords == 0:
                score += 15.0
                reasons.append("Zero Orders in Last 90 Days")

            # 4. High-Value Account Exposure
            if revenue > 3000.0 and recency > 90:
                score += 20.0
                reasons.append("High-Value Revenue Exposure ($3K+ Spend Dormant)")
            elif revenue > 1500.0 and recency > 90:
                score += 10.0
                reasons.append("Mid-Value Revenue Cooling")

            # 5. Return & Cancellation Friction
            if refund_rate > 0.15:
                score += 15.0
                reasons.append(f"High Return Friction ({refund_rate*100:.1f}% Refund Rate)")

        # Cap between 0 and 100
        final_score = int(min(100.0, max(0.0, score)))
        risk_scores[idx] = final_score

        # Determine Primary Driver
        primary_driver = reasons[0] if reasons else "Healthy Engagement Cadence"
        primary_drivers.append(primary_driver)

        # Map to Actionable Recommendation
        if final_score >= 75:
            action = "High-Touch Re-engagement / VIP Concierge Win-Back Promo"
        elif final_score >= 50:
            action = "Automated Multi-Channel Retention Flow (15% Reactivation Offer)"
        elif final_score >= 25:
            action = "Personalized Cross-Sell Campaign & Replenishment Nudge"
        else:
            action = "Loyalty Points Acceleration & Exclusive Product Previews"
        recommended_actions.append(action)

    df["risk_score"] = risk_scores.astype(int)

    # Categorical Risk Tiers
    df["risk_level"] = pd.cut(
        df["risk_score"],
        bins=[-1, 24, 49, 74, 100],
        labels=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    ).astype(str)

    df["key_risk_driver"] = primary_drivers
    df["recommended_action"] = recommended_actions

    logger.info("Rule-based risk scoring complete. Level breakdown:\n%s", df["risk_level"].value_counts().to_string())
    return df


def summarize_risk_levels(risk_df: pd.DataFrame) -> pd.DataFrame:
    """Compile business summary of risk distribution and historical revenue exposure."""
    summary = risk_df.groupby("risk_level").agg(
        customer_count=("customer_id", "count"),
        total_revenue=("total_revenue", "sum"),
        avg_revenue=("total_revenue", "mean"),
        avg_recency=("recency_days", "mean"),
        avg_completed_orders=("completed_orders", "mean"),
    ).reset_index()

    total_customers = len(risk_df)
    total_rev = summary["total_revenue"].sum()

    summary["pct_of_customers"] = (summary["customer_count"] * 100.0 / total_customers).round(2)
    summary["pct_of_revenue"] = (summary["total_revenue"] * 100.0 / max(total_rev, 1.0)).round(2)
    summary["total_revenue"] = summary["total_revenue"].round(2)
    summary["avg_revenue"] = summary["avg_revenue"].round(2)
    summary["avg_recency"] = summary["avg_recency"].round(1)
    summary["avg_completed_orders"] = summary["avg_completed_orders"].round(1)

    # Order logically by risk severity
    tier_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    summary["tier_rank"] = summary["risk_level"].map(tier_order)
    summary = summary.sort_values(by="tier_rank").drop(columns=["tier_rank"]).reset_index(drop=True)
    return summary
