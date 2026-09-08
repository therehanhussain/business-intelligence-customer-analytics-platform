"""Phase 4 Customer Analytics & Churn Prediction Pipeline Runner.

Orchestrates:
1. Loading validated Phase 2 clean data.
2. Full customer feature engineering (anti-leakage verified).
3. RFM quintile segmentation & commercial tier classification.
4. Multi-factor rule-based baseline risk scoring & action playbooks.
5. Out-Of-Time (OOT) ML churn model training & evaluation (Logistic Regression & Random Forest).
6. Forward 90-day churn probability scoring.
7. Exporting customer_analytics.csv and staging.db table.
8. Generating comprehensive executive scorecard & reconciliation.
"""

import json
from pathlib import Path
import sqlite3
from typing import Any, Dict

import pandas as pd

from src.config.paths import PROCESSED_DATA_DIR
from src.modeling.churn_model import TimeAwareChurnPipeline
from src.modeling.features import build_customer_features
from src.modeling.rfm import calculate_rfm_scores, summarize_rfm_segments
from src.modeling.risk_rules import apply_risk_rules, summarize_risk_levels
from src.utils.logger import get_logger

logger = get_logger(__name__)


def load_cleaned_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load validated clean datasets from processed directory."""
    cust_path = PROCESSED_DATA_DIR / "customers_clean.csv"
    prod_path = PROCESSED_DATA_DIR / "products_clean.csv"
    ord_path = PROCESSED_DATA_DIR / "orders_clean.csv"

    if not cust_path.exists() or not prod_path.exists() or not ord_path.exists():
        # Fallback to SQLite staging if CSVs are missing
        db_path = PROCESSED_DATA_DIR / "staging.db"
        logger.info("Loading cleaned data from SQLite staging: %s", db_path)
        with sqlite3.connect(db_path) as conn:
            customers_df = pd.read_sql_query("SELECT * FROM customers", conn)
            products_df = pd.read_sql_query("SELECT * FROM products", conn)
            orders_df = pd.read_sql_query("SELECT * FROM orders", conn)
    else:
        logger.info("Loading cleaned datasets from CSV...")
        customers_df = pd.read_csv(cust_path)
        products_df = pd.read_csv(prod_path)
        orders_df = pd.read_csv(ord_path)

    logger.info(
        "Loaded: %d customers, %d products, %d orders.",
        len(customers_df), len(products_df), len(orders_df)
    )
    return customers_df, products_df, orders_df


def run_customer_analytics_pipeline() -> Dict[str, Any]:
    """Execute complete customer segmentation, risk scoring, and churn prediction pipeline."""
    print("=" * 80)
    print("  PHASE 4: CUSTOMER SEGMENTATION & CHURN / RISK ANALYSIS PIPELINE")
    print("=" * 80)

    # 1. Load Clean Data
    customers_df, products_df, orders_df = load_cleaned_data()

    # 2. Build Full Behavioral Features (as of latest date)
    logger.info("Step 1: Building comprehensive customer features across full history...")
    features_df = build_customer_features(
        orders_df=orders_df,
        customers_df=customers_df,
        products_df=products_df,
        cutoff_date=None,
        recent_window_days=90,
    )

    # 3. Calculate RFM Scores & Lifecycle Segments
    logger.info("Step 2: Computing statistical RFM quintiles and lifecycle segments...")
    rfm_df = calculate_rfm_scores(features_df)
    rfm_summary = summarize_rfm_segments(rfm_df)

    # 4. Apply Multi-Factor Baseline Risk Rules
    logger.info("Step 3: Evaluating transparent baseline risk engine and action playbooks...")
    scored_df = apply_risk_rules(rfm_df)
    risk_summary = summarize_risk_levels(scored_df)

    # 5. Out-Of-Time Machine Learning Pipeline
    logger.info("Step 4: Executing Out-Of-Time ML Churn Pipeline (Zero Leakage)...")
    ml_pipeline = TimeAwareChurnPipeline(
        train_cutoff="2023-12-31",
        train_outcome_start="2024-01-01",
        train_outcome_end="2024-03-31",
        test_cutoff="2024-03-31",
        test_outcome_start="2024-04-01",
        test_outcome_end="2024-06-30",
        artifacts_dir=PROCESSED_DATA_DIR / "models",
    )

    X_train, y_train, X_test, y_test, meta = ml_pipeline.prepare_datasets(
        orders_df=orders_df,
        customers_df=customers_df,
        products_df=products_df,
    )

    eval_results = ml_pipeline.train_and_evaluate(
        X_train=X_train,
        y_train=y_train,
        X_test=X_test,
        y_test=y_test,
    )

    # 6. Score Full Population with Churn Probabilities
    logger.info("Step 5: Scoring full population for forward 90-day churn probability...")
    churn_probabilities = ml_pipeline.predict_current_probabilities(scored_df)
    scored_df["churn_probability"] = churn_probabilities

    # 7. Format & Export Unified Customer Analytics Dataset
    ordered_cols = [
        "customer_id", "name", "gender", "age", "city", "state", "signup_date",
        "total_orders", "completed_orders", "total_units", "active_months",
        "first_order_date", "last_order_date", "last_completed_order_date",
        "recency_days", "account_age_days", "customer_lifetime_days",
        "total_gross_revenue", "total_revenue", "total_profit",
        "average_order_value", "order_frequency_monthly", "gross_margin_pct",
        "refund_count", "refund_amount", "refund_rate",
        "cancellation_count", "cancellation_amount", "cancellation_rate",
        "recent_revenue", "recent_order_count", "historical_revenue", "historical_order_count",
        "recent_revenue_ratio", "recent_order_ratio", "revenue_trend",
        "r_score", "f_score", "m_score", "rfm_score", "customer_segment",
        "risk_score", "risk_level", "key_risk_driver", "recommended_action",
        "churn_probability",
    ]
    export_df = scored_df[ordered_cols].copy()

    # Save CSV
    export_csv_path = PROCESSED_DATA_DIR / "customer_analytics.csv"
    export_df.to_csv(export_csv_path, index=False)
    logger.info("Saved final customer analytics table: %s (%d rows)", export_csv_path, len(export_df))

    # Save to SQLite staging database
    db_path = PROCESSED_DATA_DIR / "staging.db"
    with sqlite3.connect(db_path) as conn:
        export_df.to_sql("customer_analytics", conn, if_exists="replace", index=False)
        logger.info("Persisted 'customer_analytics' table into %s", db_path)

    # 8. Revenue & Customer Reconciliation Check
    total_customers = len(export_df)
    active_customers = int((export_df["completed_orders"] > 0).sum())
    unactivated_customers = int((export_df["completed_orders"] == 0).sum())
    total_net_rev = float(export_df["total_revenue"].sum())
    total_net_profit = float(export_df["total_profit"].sum())

    # 9. Print Executive Scorecard
    _print_executive_scorecard(
        total_customers=total_customers,
        active_customers=active_customers,
        unactivated_customers=unactivated_customers,
        total_net_rev=total_net_rev,
        total_net_profit=total_net_profit,
        rfm_summary=rfm_summary,
        risk_summary=risk_summary,
        meta=meta,
        eval_results=eval_results,
    )

    return {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "unactivated_customers": unactivated_customers,
        "total_net_revenue": total_net_rev,
        "total_net_profit": total_net_profit,
        "rfm_summary": rfm_summary.to_dict(orient="records"),
        "risk_summary": risk_summary.to_dict(orient="records"),
        "ml_metadata": meta,
        "ml_evaluation": eval_results,
        "output_csv": str(export_csv_path),
    }


def _print_executive_scorecard(
    total_customers: int,
    active_customers: int,
    unactivated_customers: int,
    total_net_rev: float,
    total_net_profit: float,
    rfm_summary: pd.DataFrame,
    risk_summary: pd.DataFrame,
    meta: Dict[str, Any],
    eval_results: Dict[str, Any],
) -> None:
    """Print structured, business-ready executive scorecard to console."""
    lr_metrics = eval_results["logistic_regression"]["metrics"]
    rf_metrics = eval_results["random_forest"]["metrics"]
    lr_cm = lr_metrics["confusion_matrix"]

    print("\n" + "=" * 80)
    print("                      EXECUTIVE ANALYTICS SCORECARD")
    print("=" * 80)
    print(f"Total Customer Population : {total_customers:,}")
    print(f"Active Paying Customers   : {active_customers:,} ({active_customers/total_customers*100:.1f}%)")
    print(f"Unactivated Accounts      : {unactivated_customers:,} ({unactivated_customers/total_customers*100:.1f}%)")
    print(f"Total Realized Net Revenue: ${total_net_rev:,.2f}")
    print(f"Total Gross Profit        : ${total_net_profit:,.2f}")
    print(f"Phase 3 Reconciliation    : {'CONFIRMED MATCH ($31,028,579.95)' if abs(total_net_rev - 31028579.95) < 0.01 else 'DISCREPANCY DETECTED'}")

    print("\n" + "-" * 80)
    print(" 1. RFM CUSTOMER SEGMENTATION BREAKDOWN")
    print("-" * 80)
    print(rfm_summary.to_string(index=False))

    print("\n" + "-" * 80)
    print(" 2. BASELINE RULE-BASED RISK PROFILE & EXPOSURE")
    print("-" * 80)
    print(risk_summary.to_string(index=False))

    print("\n" + "-" * 80)
    print(" 3. OUT-OF-TIME MACHINE LEARNING EVALUATION (ZERO LEAKAGE)")
    print("-" * 80)
    train_meta = meta["train"]
    test_meta = meta["test"]
    print(f"Training Window : Feature Cutoff <= {train_meta['feature_cutoff']} | Outcome: {train_meta['outcome_start']} to {train_meta['outcome_end']}")
    print(f"  - Eligible Customers : {train_meta['eligible_customers']:,}")
    print(f"  - Actual Churn Rate  : {train_meta['churn_rate_pct']}% ({train_meta['churned_customers']:,} churned)")
    print(f"Testing Window  : Feature Cutoff <= {test_meta['feature_cutoff']} | Outcome: {test_meta['outcome_start']} to {test_meta['outcome_end']}")
    print(f"  - Eligible Customers : {test_meta['eligible_customers']:,}")
    print(f"  - Actual Churn Rate  : {test_meta['churn_rate_pct']}% ({test_meta['churned_customers']:,} churned)")

    print("\nModel Comparison on Out-of-Time Test Set:")
    print(f"{'Metric':<20} | {'Logistic Regression (Primary)':<30} | {'Random Forest (Comparator)':<25}")
    print("-" * 80)
    print(f"{'ROC-AUC Score':<20} | {lr_metrics['roc_auc']:<30.4f} | {rf_metrics['roc_auc']:<25.4f}")
    print(f"{'Accuracy':<20} | {lr_metrics['accuracy']:<30.4f} | {rf_metrics['accuracy']:<25.4f}")
    print(f"{'Precision':<20} | {lr_metrics['precision']:<30.4f} | {rf_metrics['precision']:<25.4f}")
    print(f"{'Recall':<20} | {lr_metrics['recall']:<30.4f} | {rf_metrics['recall']:<25.4f}")
    print(f"{'F1-Score':<20} | {lr_metrics['f1']:<30.4f} | {rf_metrics['f1']:<25.4f}")
    print("-" * 80)
    print(f"Confusion Matrix (LR) : TN={lr_cm['true_negative']:,} | FP={lr_cm['false_positive']:,} | FN={lr_cm['false_negative']:,} | TP={lr_cm['true_positive']:,}")

    print("\nTop Predictive Features (Standardized Logistic Regression Coefficients):")
    coefs = eval_results["logistic_regression"]["coefficients"]
    for feat, val in list(coefs.items())[:5]:
        print(f"  (+) Higher Churn Risk : {feat:<25} (coef = {val:+.4f})")
    for feat, val in list(coefs.items())[-5:]:
        print(f"  (-) Retention Driver  : {feat:<25} (coef = {val:+.4f})")

    print("\nDecision Threshold Trade-Off Analysis (Logistic Regression):")
    print(f"{'Threshold':<10} | {'Precision':<10} | {'Recall':<10} | {'F1-Score':<10} | {'Targeted':<10} | {'False Alarms':<12}")
    print("-" * 72)
    for trade in eval_results["logistic_regression"]["threshold_tradeoffs"]:
        print(
            f"{trade['threshold']:<10.2f} | {trade['precision']:<10.4f} | "
            f"{trade['recall']:<10.4f} | {trade['f1']:<10.4f} | "
            f"{trade['targeted_count']:<10,d} | {trade['false_alarms']:<12,d}"
        )

    print("\n" + "=" * 80)
    print("  PHASE 4 EXECUTION COMPLETE & PERSISTED SUCCESSFULLY")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_customer_analytics_pipeline()
