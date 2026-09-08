"""Unit test suite for Phase 4 Customer Analytics, Anti-Leakage Controls, and ML Models."""

import json
from pathlib import Path
import sqlite3
import unittest
import numpy as np
import pandas as pd

from src.config.paths import PROCESSED_DATA_DIR
from src.modeling.churn_model import MODEL_FEATURE_COLS, TimeAwareChurnPipeline
from src.modeling.features import build_customer_features, build_time_aware_churn_dataset
from src.modeling.rfm import calculate_rfm_scores
from src.modeling.risk_rules import apply_risk_rules


class TestCustomerModeling(unittest.TestCase):
    """Rigorous tests covering temporal integrity, anti-leakage, segmentation, and reconciliation."""

    @classmethod
    def setUpClass(cls):
        cust_path = PROCESSED_DATA_DIR / "customers_clean.csv"
        prod_path = PROCESSED_DATA_DIR / "products_clean.csv"
        ord_path = PROCESSED_DATA_DIR / "orders_clean.csv"

        if cust_path.exists() and prod_path.exists() and ord_path.exists():
            cls.customers = pd.read_csv(cust_path)
            cls.products = pd.read_csv(prod_path)
            cls.orders = pd.read_csv(ord_path)
        else:
            with sqlite3.connect(PROCESSED_DATA_DIR / "staging.db") as conn:
                cls.customers = pd.read_sql_query("SELECT * FROM customers", conn)
                cls.products = pd.read_sql_query("SELECT * FROM products", conn)
                cls.orders = pd.read_sql_query("SELECT * FROM orders", conn)

    def test_feature_engineering_strict_anti_leakage(self):
        """Verify that cutoff_date prevents any future transactions from entering feature calculations."""
        cutoff = "2023-12-31"
        feats = build_customer_features(
            orders_df=self.orders,
            customers_df=self.customers,
            products_df=self.products,
            cutoff_date=cutoff,
            recent_window_days=90,
        )

        # 1. No customer signed up after cutoff
        post_cutoff_signups = feats[pd.to_datetime(feats["signup_date"]) > pd.to_datetime(cutoff)]
        self.assertEqual(len(post_cutoff_signups), 0, "No customers after cutoff should be in dataset")

        # 2. No order after cutoff contributes to last_order_date
        active_feats = feats[feats["completed_orders"] > 0]
        max_order_date = pd.to_datetime(active_feats["last_order_date"]).max()
        self.assertLessEqual(
            max_order_date,
            pd.to_datetime(cutoff),
            f"Max order date ({max_order_date}) must be <= cutoff date ({cutoff})"
        )

        # 3. Recency days must be calculated relative to cutoff date
        # (e.g. order on 2023-12-30 relative to 2023-12-31 has recency = 1)
        sample = active_feats[active_feats["last_completed_order_date"] == "2023-12-31"]
        if len(sample) > 0:
            self.assertEqual(sample.iloc[0]["recency_days"], 0)

    def test_time_aware_churn_dataset_temporal_integrity(self):
        """Verify that training features strictly precede the outcome evaluation window."""
        cutoff = "2023-12-31"
        outcome_start = "2024-01-01"
        outcome_end = "2024-03-31"

        feat_df, y, meta = build_time_aware_churn_dataset(
            orders_df=self.orders,
            customers_df=self.customers,
            products_df=self.products,
            feature_cutoff=cutoff,
            outcome_start=outcome_start,
            outcome_end=outcome_end,
        )

        self.assertEqual(len(feat_df), len(y), "Features and target must have identical length")
        self.assertEqual(len(feat_df), meta["eligible_customers"])
        self.assertGreater(meta["eligible_customers"], 5000, "Expected at least 5,000 eligible customers by end 2023")

        # Churn rate sanity
        self.assertGreater(meta["churn_rate_pct"], 30.0)
        self.assertLess(meta["churn_rate_pct"], 80.0)

        # Anti-leakage: target column and identifiers must not be in feature columns
        self.assertNotIn("is_churned", feat_df[MODEL_FEATURE_COLS].columns)
        self.assertNotIn("customer_id", MODEL_FEATURE_COLS)

    def test_scaler_fitted_strictly_on_training_data(self):
        """Verify that StandardScaler parameters are derived solely from training features."""
        pipeline = TimeAwareChurnPipeline(
            train_cutoff="2023-12-31",
            train_outcome_start="2024-01-01",
            train_outcome_end="2024-03-31",
            test_cutoff="2024-03-31",
            test_outcome_start="2024-04-01",
            test_outcome_end="2024-06-30",
        )

        X_train, y_train, X_test, y_test, meta = pipeline.prepare_datasets(
            self.orders, self.customers, self.products
        )

        # Train cutoff must be strictly earlier than test cutoff
        self.assertLess(
            pd.to_datetime(meta["train"]["feature_cutoff"]),
            pd.to_datetime(meta["test"]["feature_cutoff"]),
            "Train cutoff must strictly precede test cutoff"
        )

        # Fit and evaluate
        pipeline.train_and_evaluate(X_train, y_train, X_test, y_test)

        # Verify scaler mean matches training set mean
        expected_train_means = X_train.mean(axis=0).values
        np.testing.assert_allclose(
            pipeline.scaler.mean_,
            expected_train_means,
            rtol=1e-3,
            err_msg="Scaler mean must match training feature mean"
        )

    def test_rfm_segmentation_coverage_and_unactivated(self):
        """Verify RFM quintile rules, score formatting, and unactivated handling."""
        feats = build_customer_features(self.orders, self.customers, self.products)
        rfm_df = calculate_rfm_scores(feats)

        self.assertEqual(len(rfm_df), 10000, "All 10,000 customers must be present in RFM output")

        # Unactivated customers (0 completed orders) must have R=0, F=0, M=0
        unactivated = rfm_df[rfm_df["completed_orders"] == 0]
        self.assertGreater(len(unactivated), 0, "Must have unactivated customers")
        self.assertTrue((unactivated["r_score"] == 0).all())
        self.assertTrue((unactivated["f_score"] == 0).all())
        self.assertTrue((unactivated["m_score"] == 0).all())
        self.assertTrue((unactivated["rfm_score"] == "000").all())
        self.assertTrue((unactivated["customer_segment"] == "Inactive / Unactivated").all())

        # Paying customers must have scores between 1 and 5
        paying = rfm_df[rfm_df["completed_orders"] > 0]
        self.assertTrue(paying["r_score"].isin([1, 2, 3, 4, 5]).all())
        self.assertTrue(paying["f_score"].isin([1, 2, 3, 4, 5]).all())
        self.assertTrue(paying["m_score"].isin([1, 2, 3, 4, 5]).all())

    def test_risk_engine_score_bounds_and_tiers(self):
        """Verify baseline risk scoring is bounded in [0, 100] and maps to valid tiers."""
        feats = build_customer_features(self.orders, self.customers, self.products)
        rfm_df = calculate_rfm_scores(feats)
        risk_df = apply_risk_rules(rfm_df)

        self.assertEqual(len(risk_df), 10000)
        self.assertTrue((risk_df["risk_score"] >= 0).all() and (risk_df["risk_score"] <= 100).all())
        valid_tiers = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        self.assertTrue(set(risk_df["risk_level"].unique()).issubset(valid_tiers))

        # Check unactivated customers get CRITICAL tier
        unactivated = risk_df[risk_df["completed_orders"] == 0]
        self.assertTrue((unactivated["risk_level"] == "CRITICAL").all())
        self.assertTrue((unactivated["risk_score"] >= 75).all())

    def test_customer_analytics_reconciliation_with_phase3(self):
        """Verify that customer_analytics.csv exists, has 10,000 rows, and strictly reconciles to Phase 3 revenue."""
        analytics_path = PROCESSED_DATA_DIR / "customer_analytics.csv"
        if not analytics_path.exists():
            # If runner hasn't finished yet in background, skip or assert existence
            self.skipTest("customer_analytics.csv not yet generated")

        df = pd.read_csv(analytics_path)
        self.assertEqual(len(df), 10000, "Must have exactly 10,000 customer rows")
        self.assertEqual(df["customer_id"].nunique(), 10000, "Customer IDs must be distinct")

        # Phase 3 Net Revenue was exactly $31,028,579.95
        total_rev = round(df["total_revenue"].sum(), 2)
        self.assertAlmostEqual(
            total_rev,
            31028579.95,
            places=2,
            msg="Phase 4 customer total_revenue must strictly match Phase 3 net revenue ($31,028,579.95)"
        )

        # Churn probability must be present and bounded in [0, 1]
        self.assertIn("churn_probability", df.columns)
        self.assertTrue((df["churn_probability"] >= 0.0).all() and (df["churn_probability"] <= 1.0).all())

    def test_model_metrics_and_artifacts_saved(self):
        """Verify saved model joblib artifacts and evaluation metrics."""
        models_dir = PROCESSED_DATA_DIR / "models"
        metrics_file = models_dir / "model_metrics.json"

        if not metrics_file.exists():
            self.skipTest("Model artifacts not yet saved")

        self.assertTrue((models_dir / "logistic_regression.joblib").exists())
        self.assertTrue((models_dir / "scaler.joblib").exists())
        self.assertTrue((models_dir / "random_forest.joblib").exists())

        with open(metrics_file, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        lr_metrics = metrics["logistic_regression"]["metrics"]
        self.assertGreater(lr_metrics["roc_auc"], 0.50, "ROC-AUC must exceed random guess (0.50)")
        self.assertGreater(lr_metrics["accuracy"], 0.50)
        self.assertGreater(lr_metrics["f1"], 0.50)

        # Confusion matrix checks
        cm = lr_metrics["confusion_matrix"]
        total_tested = cm["true_negative"] + cm["false_positive"] + cm["false_negative"] + cm["true_positive"]
        self.assertEqual(total_tested, 8873, "Test set size must match eligible customers as of 2024-03-31")


if __name__ == "__main__":
    unittest.main()
