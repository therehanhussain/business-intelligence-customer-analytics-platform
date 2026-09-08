"""Comprehensive Phase 6 Quality Assurance and Production Readiness Test Suite.

Audits and validates the complete Business Intelligence & Customer Analytics Platform
across all phases (Phase 2 ETL, Phase 3 SQL Analytics, Phase 4 Customer Modeling,
and Phase 5 Power BI Data Architecture).

Verifications covered:
1. TestETLDataQualityQA: DLQ invariants, edge case handling, raw-to-valid reconciliation.
2. TestSQLAnalyticsQA: Financial invariants, fulfillment breakdown, cross-dimensional reconciliation.
3. TestCustomerSegmentationQA: RFM coverage, mutual exclusivity, exact segment counts & revenues, Pareto.
4. TestChurnModelAntiLeakageQA: Temporal cutoff safety, zero future leakage, scaler isolation.
5. TestModelPerformanceQA: Model scorecard verification, metrics file artifacts, decision threshold trade-offs.
6. TestPowerBIDataModelQA: Star-schema referential integrity, zero orphans, 103,695 rows, metric equivalence.
7. TestPipelineReproducibilityQA: Configuration integrity, random seed control, environment dependencies.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import unittest
import numpy as np
import pandas as pd
import joblib

from src.config.paths import (
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    CONFIG_DIR,
)
from src.config.settings import settings, load_config
from src.etl.extract import extract_all_raw_data
from src.etl.transform import transform_customers, transform_products, transform_orders
from src.etl.validate import (
    validate_customers,
    validate_products,
    validate_orders,
    validate_all_data,
)
from src.modeling.features import (
    build_customer_features,
    build_time_aware_churn_dataset,
)
from src.modeling.churn_model import MODEL_FEATURE_COLS, TimeAwareChurnPipeline
from src.modeling.rfm import calculate_rfm_scores
from src.modeling.risk_rules import apply_risk_rules


PBI_DIR = PROCESSED_DATA_DIR / "powerbi"
MODELS_DIR = PROCESSED_DATA_DIR / "models"


class TestETLDataQualityQA(unittest.TestCase):
    """Section 3: Rigorous ETL data quality, edge-case rejection, and DLQ invariants."""

    @classmethod
    def setUpClass(cls):
        cls.raw_cust, cls.raw_prod, cls.raw_ord, cls.meta = extract_all_raw_data(RAW_DATA_DIR)
        cls.clean_cust = pd.read_csv(PROCESSED_DATA_DIR / "customers_clean.csv")
        cls.clean_prod = pd.read_csv(PROCESSED_DATA_DIR / "products_clean.csv")
        cls.clean_ord = pd.read_csv(PROCESSED_DATA_DIR / "orders_clean.csv")
        cls.dlq = pd.read_csv(PROCESSED_DATA_DIR / "rejected_records.csv")
        with open(PROCESSED_DATA_DIR / "etl_audit_summary.json", "r", encoding="utf-8") as f:
            cls.audit = json.load(f)

    def test_raw_to_valid_dlq_invariant_reconciliation(self):
        """Invariant: Total Raw = Valid Clean + Rejected DLQ across all tables."""
        # 1. Customers: 10,080 = 10,000 + 80
        cust_raw_count = len(self.raw_cust)
        cust_valid_count = len(self.clean_cust)
        cust_rejected_count = len(self.dlq[self.dlq["table_name"] == "customers"])
        self.assertEqual(cust_raw_count, 10080, "Raw customers count must be 10,080")
        self.assertEqual(cust_valid_count, 10000, "Clean valid customers count must be 10,000")
        self.assertEqual(cust_rejected_count, 80, "Rejected customers count must be 80")
        self.assertEqual(cust_raw_count, cust_valid_count + cust_rejected_count)

        # 2. Products: 500 = 492 + 8
        prod_raw_count = len(self.raw_prod)
        prod_valid_count = len(self.clean_prod)
        prod_rejected_count = len(self.dlq[self.dlq["table_name"] == "products"])
        self.assertEqual(prod_raw_count, 500, "Raw products count must be 500")
        self.assertEqual(prod_valid_count, 492, "Clean valid products count must be 492")
        self.assertEqual(prod_rejected_count, 8, "Rejected products count must be 8")
        self.assertEqual(prod_raw_count, prod_valid_count + prod_rejected_count)

        # 3. Orders: 106,919 = 103,695 + 3,224
        ord_raw_count = len(self.raw_ord)
        ord_valid_count = len(self.clean_ord)
        ord_rejected_count = len(self.dlq[self.dlq["table_name"] == "orders"])
        self.assertEqual(ord_raw_count, 106919, "Raw orders count must be 106,919")
        self.assertEqual(ord_valid_count, 103695, "Clean valid orders count must be 103,695")
        self.assertEqual(ord_rejected_count, 3224, "Rejected orders count must be 3,224")
        self.assertEqual(ord_raw_count, ord_valid_count + ord_rejected_count)

        # 4. Total records: 117,499 = 114,187 + 3,312
        total_raw = cust_raw_count + prod_raw_count + ord_raw_count
        total_valid = cust_valid_count + prod_valid_count + ord_valid_count
        total_dlq = len(self.dlq)
        self.assertEqual(total_raw, 117499)
        self.assertEqual(total_valid, 114187)
        self.assertEqual(total_dlq, 3312)
        self.assertEqual(total_raw, total_valid + total_dlq)

    def test_dead_letter_queue_schema_and_invariants(self):
        """Invariant: Every rejected record has complete metadata and valid serialized JSON payload."""
        expected_cols = {"table_name", "record_identifier", "rejection_reason", "rejected_at", "raw_payload"}
        self.assertTrue(expected_cols.issubset(set(self.dlq.columns)))

        # No null or empty values in critical DLQ columns
        self.assertEqual(self.dlq["table_name"].isna().sum(), 0)
        self.assertEqual(self.dlq["record_identifier"].isna().sum(), 0)
        self.assertEqual(self.dlq["rejection_reason"].isna().sum(), 0)
        self.assertEqual(self.dlq["rejected_at"].isna().sum(), 0)
        self.assertEqual(self.dlq["raw_payload"].isna().sum(), 0)

        self.assertTrue((self.dlq["table_name"].str.strip() != "").all())
        self.assertTrue((self.dlq["record_identifier"].str.strip() != "").all())
        self.assertTrue((self.dlq["rejection_reason"].str.strip() != "").all())

        # Sample 50 payloads to verify valid JSON format
        sample_payloads = self.dlq["raw_payload"].sample(n=min(50, len(self.dlq)), random_state=42)
        for payload in sample_payloads:
            parsed = json.loads(payload)
            self.assertIsInstance(parsed, dict)

    def test_quarantine_isolation_invariants(self):
        """Invariant: Zero leakage between valid clean tables and rejected DLQ records."""
        # 1. Valid customer IDs must have zero internal duplicates
        self.assertEqual(len(self.clean_cust), 10000)
        self.assertEqual(self.clean_cust["customer_id"].duplicated().sum(), 0)

        # 2. Valid products must have 0 overlap with quarantined product IDs
        valid_prod_ids = set(self.clean_prod["product_id"])
        rej_prod_ids = set(self.dlq[self.dlq["table_name"] == "products"]["record_identifier"])
        overlap_prod = valid_prod_ids.intersection(rej_prod_ids)
        self.assertEqual(len(overlap_prod), 0, f"Rejected products leaked into clean products: {overlap_prod}")

        # 3. Valid orders must have 0 overlap with quarantined order IDs
        valid_ord_ids = set(self.clean_ord["order_id"])
        rej_ord_ids = set(self.dlq[self.dlq["table_name"] == "orders"]["record_identifier"])
        overlap_ord = valid_ord_ids.intersection(rej_ord_ids)
        self.assertEqual(len(overlap_ord), 0, f"Quarantined orders leaked into clean orders: {overlap_ord}")

    def test_approved_phase2_baseline_breakdown(self):
        """Verify exact approved DLQ rejection breakdown from Phase 2 audit log."""
        dlq_reasons = self.dlq["rejection_reason"].value_counts().to_dict()

        expected_dlq = {
            "ORPHAN_PRODUCT_FOREIGN_KEY": 2729,
            "INVALID_QUANTITY_NEGATIVE_RETURN": 330,
            "INVALID_QUANTITY_ZERO": 165,
            "DUPLICATE_CUSTOMER_ID": 80,
            "MISSING_PRODUCT_CATEGORY": 5,
            "MISSING_PRODUCT_COST": 3,
        }

        for reason, expected_count in expected_dlq.items():
            self.assertIn(reason, dlq_reasons)
            self.assertEqual(dlq_reasons[reason], expected_count, f"Mismatch for rejection reason {reason}")

    def test_edge_case_duplicate_customers_handling(self):
        """Edge Case: Exact duplicates and differing attribute duplicates with same customer_id."""
        synthetic_cust = pd.DataFrame([
            {"customer_id": "CUST_99999", "name": "Alice Smith", "email": "alice@example.com", "age": 30.0},
            {"customer_id": "CUST_99999", "name": "Alice Smith", "email": "alice@example.com", "age": 30.0},
            {"customer_id": "CUST_99999", "name": "Alice Brown", "email": "alice.b@example.com", "age": 32.0},
        ])
        valid_c, rej_c, _ = validate_customers(synthetic_cust)
        self.assertEqual(len(valid_c), 1, "Only first occurrence should be kept")
        self.assertEqual(len(rej_c), 2, "Both duplicates should be quarantined")
        self.assertTrue((rej_c["rejection_reason"] == "DUPLICATE_CUSTOMER_ID").all())

    def test_edge_case_missing_critical_fields_and_types(self):
        """Edge Case: Missing critical product fields, non-positive price/cost, and inverted margin."""
        synthetic_prod = pd.DataFrame([
            {"product_id": "PROD_01", "product_name": "P1", "category": None, "price": 100.0, "cost": 50.0},
            {"product_id": "PROD_02", "product_name": "P2", "category": "Audio", "price": 100.0, "cost": np.nan},
            {"product_id": "PROD_03", "product_name": "P3", "category": "Audio", "price": 0.0, "cost": 10.0},
            {"product_id": "PROD_04", "product_name": "P4", "category": "Audio", "price": -50.0, "cost": 10.0},
            {"product_id": "PROD_05", "product_name": "P5", "category": "Audio", "price": 100.0, "cost": 0.0},
            {"product_id": "PROD_06", "product_name": "P6", "category": "Audio", "price": 50.0, "cost": 80.0},
            {"product_id": "PROD_07", "product_name": "P7", "category": "Audio", "price": 100.0, "cost": 40.0},
        ])
        valid_p, rej_p, _ = validate_products(synthetic_prod)
        self.assertEqual(len(valid_p), 1)
        self.assertEqual(valid_p.iloc[0]["product_id"], "PROD_07")
        self.assertEqual(len(rej_p), 6)

        reasons = set(rej_p["rejection_reason"].unique())
        self.assertIn("MISSING_PRODUCT_CATEGORY", reasons)
        self.assertIn("MISSING_PRODUCT_COST", reasons)
        self.assertIn("INVALID_PRICE_NON_POSITIVE", reasons)
        self.assertIn("INVALID_COST_NON_POSITIVE", reasons)
        self.assertIn("INVALID_COST_EXCEEDS_PRICE", reasons)

    def test_edge_case_order_quantities_and_referential_integrity(self):
        """Edge Case: Order validation with negative/zero quantities and orphaned foreign keys."""
        valid_c_ids = {"CUST_100"}
        valid_p_ids = {"PROD_100"}

        synthetic_ord = pd.DataFrame([
            {"order_id": "O_01", "customer_id": "CUST_100", "product_id": "PROD_100", "quantity": -2},
            {"order_id": "O_02", "customer_id": "CUST_100", "product_id": "PROD_100", "quantity": 0},
            {"order_id": "O_03", "customer_id": "CUST_GHOST", "product_id": "PROD_100", "quantity": 1},
            {"order_id": "O_04", "customer_id": "CUST_100", "product_id": "PROD_GHOST", "quantity": 1},
            {"order_id": "O_05", "customer_id": "CUST_100", "product_id": "PROD_100", "quantity": 3},
        ])

        valid_o, rej_o, _ = validate_orders(synthetic_ord, valid_c_ids, valid_p_ids)
        self.assertEqual(len(valid_o), 1)
        self.assertEqual(valid_o.iloc[0]["order_id"], "O_05")
        self.assertEqual(len(rej_o), 4)

        ord_reasons = set(rej_o["rejection_reason"].unique())
        self.assertIn("INVALID_QUANTITY_NEGATIVE_RETURN", ord_reasons)
        self.assertIn("INVALID_QUANTITY_ZERO", ord_reasons)
        self.assertIn("ORPHAN_CUSTOMER_FOREIGN_KEY", ord_reasons)
        self.assertIn("ORPHAN_PRODUCT_FOREIGN_KEY", ord_reasons)

    def test_clean_order_dates_within_bounds(self):
        """Verify that order_date in clean orders contains zero nulls and falls within valid 2022-2024 range."""
        self.assertEqual(self.clean_ord["order_date"].isna().sum(), 0)
        min_date = self.clean_ord["order_date"].min()
        max_date = self.clean_ord["order_date"].max()
        self.assertGreaterEqual(min_date, "2022-01-01")
        self.assertLessEqual(max_date, "2024-12-31")


class TestSQLAnalyticsQA(unittest.TestCase):
    """Section 4: SQL financial invariants, status breakdown, and multi-dimensional reconciliations."""

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(PROCESSED_DATA_DIR / "staging.db")
        cls.order_view = pd.read_sql_query("SELECT * FROM v_order_analytics", cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_financial_invariants_exact_values(self):
        """Verify financial identity: Gross = Net + Refunded + Cancelled, and exact cent totals."""
        gross_rev = round(self.order_view["gross_revenue"].sum(), 2)
        net_rev = round(self.order_view["net_revenue"].sum(), 2)
        refunded_amt = round(self.order_view["refunded_amount"].sum(), 2)
        cancelled_amt = round(self.order_view["cancelled_amount"].sum(), 2)
        gross_profit = round(self.order_view["net_profit"].sum(), 2)
        gross_margin = round((gross_profit / net_rev) * 100.0, 2)

        # Exact dollar checks
        self.assertEqual(gross_rev, 33726886.71, "Gross revenue must be exactly $33,726,886.71")
        self.assertEqual(net_rev, 31028579.95, "Net revenue must be exactly $31,028,579.95")
        self.assertEqual(refunded_amt, 1334921.53, "Refunded amount must be exactly $1,334,921.53")
        self.assertEqual(cancelled_amt, 1363385.23, "Cancelled amount must be exactly $1,363,385.23")
        self.assertEqual(gross_profit, 12461250.73, "Gross profit must be exactly $12,461,250.73")
        self.assertEqual(gross_margin, 40.16, "Gross margin must be exactly 40.16%")

        # Financial identity
        reconciled_gross = round(net_rev + refunded_amt + cancelled_amt, 2)
        diff = abs(gross_rev - reconciled_gross)
        self.assertLessEqual(diff, 0.05, f"Discrepancy in revenue identity: {diff}")

    def test_order_status_distribution_and_fulfillment(self):
        """Verify order status counts, revenue-generating orders, and friction metrics."""
        status_counts = self.order_view["order_status"].value_counts().to_dict()

        self.assertEqual(status_counts.get("Completed", 0), 89283)
        self.assertEqual(status_counts.get("Shipped", 0), 6243)
        self.assertEqual(status_counts.get("Refunded", 0), 4087)
        self.assertEqual(status_counts.get("Cancelled", 0), 4082)
        self.assertEqual(len(self.order_view), 103695)

        # Revenue-generating orders = Completed (89,283) + Shipped (6,243) = 95,526
        revenue_orders = self.order_view[self.order_view["is_completed"] == 1]
        self.assertEqual(len(revenue_orders), 95526)

        # Friction orders must yield zero net revenue
        refunded_orders = self.order_view[self.order_view["order_status"] == "Refunded"]
        cancelled_orders = self.order_view[self.order_view["order_status"] == "Cancelled"]
        self.assertEqual(refunded_orders["net_revenue"].sum(), 0.0)
        self.assertEqual(cancelled_orders["net_revenue"].sum(), 0.0)
        self.assertTrue((refunded_orders["refunded_amount"] > 0).all())
        self.assertTrue((cancelled_orders["cancelled_amount"] > 0).all())
        self.assertTrue((refunded_orders["quantity"] > 0).all())

    def test_cross_dimensional_reconciliation(self):
        """Cross-Dimensional Invariant: Revenue sum across dimensions equals $31,028,579.95."""
        target_net = 31028579.95

        # 1. Customer dimension sum
        cust_rev_sum = round(self.order_view.groupby("customer_id")["net_revenue"].sum().sum(), 2)
        self.assertEqual(cust_rev_sum, target_net)

        # 2. Product dimension sum
        prod_rev_sum = round(self.order_view.groupby("product_id")["net_revenue"].sum().sum(), 2)
        self.assertEqual(prod_rev_sum, target_net)

        # 3. Date dimension sum
        date_rev_sum = round(self.order_view.groupby("order_date")["net_revenue"].sum().sum(), 2)
        self.assertEqual(date_rev_sum, target_net)

        # 4. Monthly aggregation sum (30 active transaction months: 2022-01 to 2024-06)
        self.order_view["year_month"] = self.order_view["order_date"].str.slice(0, 7)
        monthly_summary = self.order_view.groupby("year_month")["net_revenue"].sum()
        self.assertEqual(len(monthly_summary), 30, "Must span exactly 30 transaction months")
        monthly_rev_sum = round(monthly_summary.sum(), 2)
        self.assertEqual(monthly_rev_sum, target_net)

        # 5. Average Order Value (AOV) on revenue-generating orders
        aov = target_net / 95526
        self.assertEqual(round(aov, 2), 324.82)

    def test_analytical_view_cardinality_and_referential_completeness(self):
        """Verify join integrity in v_order_analytics: 103,695 rows and zero orphaned attributes."""
        self.assertEqual(len(self.order_view), 103695)
        self.assertEqual(self.order_view["customer_name"].isna().sum(), 0)
        self.assertEqual(self.order_view["product_name"].isna().sum(), 0)
        self.assertTrue((self.order_view["customer_name"].str.strip() != "").all())
        self.assertTrue((self.order_view["product_name"].str.strip() != "").all())


class TestCustomerSegmentationQA(unittest.TestCase):
    """Section 5: Customer segmentation, RFM scoring, mutual exclusivity, and Pareto invariants."""

    @classmethod
    def setUpClass(cls):
        cls.cust_analytics = pd.read_csv(PROCESSED_DATA_DIR / "customer_analytics.csv")

    def test_rfm_scoring_invariants_and_coverage(self):
        """RFM Invariant: 100% customer coverage, unactivated handled cleanly, scores in {1..5}."""
        self.assertEqual(len(self.cust_analytics), 10000)
        self.assertEqual(self.cust_analytics["customer_id"].nunique(), 10000)

        # Unactivated customers: completed_orders == 0
        unactivated = self.cust_analytics[self.cust_analytics["completed_orders"] == 0]
        self.assertEqual(len(unactivated), 1075, "Exactly 1,075 customers must be unactivated")
        self.assertTrue((unactivated["r_score"] == 0).all())
        self.assertTrue((unactivated["f_score"] == 0).all())
        self.assertTrue((unactivated["m_score"] == 0).all())
        self.assertTrue((unactivated["rfm_score"].astype(str).isin(["0", "000"])).all())
        self.assertTrue((unactivated["customer_segment"] == "Inactive / Unactivated").all())

        # Active paying customers: completed_orders > 0
        paying = self.cust_analytics[self.cust_analytics["completed_orders"] > 0]
        self.assertEqual(len(paying), 8925)
        self.assertTrue(paying["r_score"].isin([1, 2, 3, 4, 5]).all())
        self.assertTrue(paying["f_score"].isin([1, 2, 3, 4, 5]).all())
        self.assertTrue(paying["m_score"].isin([1, 2, 3, 4, 5]).all())

    def test_rfm_mutual_exclusivity_and_completeness(self):
        """Segmentation Invariant: Mutually exclusive & collectively exhaustive (sum = 10,000)."""
        segment_counts = self.cust_analytics["customer_segment"].value_counts()
        self.assertEqual(segment_counts.sum(), 10000)
        self.assertEqual(self.cust_analytics["customer_segment"].isna().sum(), 0)

    def test_segment_counts_and_revenue_exact_reconciliation(self):
        """Reconciliation: Every segment matches approved Phase 4 count and revenue to the cent."""
        seg_summary = self.cust_analytics.groupby("customer_segment").agg(
            cust_count=("customer_id", "count"),
            revenue=("total_revenue", "sum")
        ).round(2).to_dict(orient="index")

        expected = {
            "Champions": (2150, 17187268.70),
            "Loyal Customers": (1654, 6444598.27),
            "At Risk": (1000, 4099567.19),
            "Promising": (1441, 1426446.27),
            "Hibernating": (1976, 705553.51),
            "Cannot Lose Them": (110, 587672.52),
            "Potential Loyalists": (570, 572474.59),
            "New Customers": (24, 4998.90),
            "Inactive / Unactivated": (1075, 0.00),
        }

        total_rev_check = 0.0
        for seg, (exp_count, exp_rev) in expected.items():
            self.assertIn(seg, seg_summary)
            self.assertEqual(seg_summary[seg]["cust_count"], exp_count, f"Count mismatch for segment {seg}")
            self.assertAlmostEqual(seg_summary[seg]["revenue"], exp_rev, places=1, msg=f"Revenue mismatch for {seg}")
            total_rev_check += exp_rev

        self.assertAlmostEqual(round(total_rev_check, 2), 31028579.95, places=2)

    def test_pareto_distribution_invariant(self):
        """Pareto Invariant: Champions and Loyal Customers represent 38.04% of customers but 76.16% of revenue."""
        top2 = self.cust_analytics[self.cust_analytics["customer_segment"].isin(["Champions", "Loyal Customers"])]
        top2_count = len(top2)
        top2_rev = round(top2["total_revenue"].sum(), 2)

        self.assertEqual(top2_count, 3804)
        self.assertEqual(top2_rev, 23631866.97)

        cust_pct = round((top2_count / 10000.0) * 100.0, 2)
        rev_pct = round((top2_rev / 31028579.95) * 100.0, 2)

        self.assertEqual(cust_pct, 38.04)
        self.assertEqual(rev_pct, 76.16)


class TestChurnModelAntiLeakageQA(unittest.TestCase):
    """Section 6: Temporal anti-leakage audit, out-of-time cutoffs, and preprocessor isolation."""

    @classmethod
    def setUpClass(cls):
        cls.customers = pd.read_csv(PROCESSED_DATA_DIR / "customers_clean.csv")
        cls.products = pd.read_csv(PROCESSED_DATA_DIR / "products_clean.csv")
        cls.orders = pd.read_csv(PROCESSED_DATA_DIR / "orders_clean.csv")

    def test_oot_validation_cohort_windows(self):
        """Temporal Invariant: Train and Test cohorts follow strictly non-overlapping temporal design."""
        pipeline = TimeAwareChurnPipeline(
            train_cutoff="2023-12-31",
            train_outcome_start="2024-01-01",
            train_outcome_end="2024-03-31",
            test_cutoff="2024-03-31",
            test_outcome_start="2024-04-01",
            test_outcome_end="2024-06-30",
        )

        # Verify temporal boundaries
        train_cutoff_dt = pd.to_datetime(pipeline.train_cutoff)
        train_outcome_start_dt = pd.to_datetime(pipeline.train_outcome_start)
        train_outcome_end_dt = pd.to_datetime(pipeline.train_outcome_end)
        test_cutoff_dt = pd.to_datetime(pipeline.test_cutoff)
        test_outcome_start_dt = pd.to_datetime(pipeline.test_outcome_start)
        test_outcome_end_dt = pd.to_datetime(pipeline.test_outcome_end)

        self.assertLess(train_cutoff_dt, train_outcome_start_dt)
        self.assertLessEqual(train_outcome_start_dt, train_outcome_end_dt)
        self.assertEqual(train_outcome_end_dt, test_cutoff_dt, "Train outcome ends exactly on test cutoff date")
        self.assertLess(test_cutoff_dt, test_outcome_start_dt)
        self.assertLessEqual(test_outcome_start_dt, test_outcome_end_dt)

    def test_feature_engineering_temporal_anti_leakage(self):
        """Feature Invariant: Zero orders after cutoff date enter feature calculations."""
        cutoff = "2023-12-31"
        feats = build_customer_features(
            orders_df=self.orders,
            customers_df=self.customers,
            products_df=self.products,
            cutoff_date=cutoff,
            recent_window_days=90,
        )

        # 1. No customer who signed up after cutoff is present
        post_cutoff_signups = feats[pd.to_datetime(feats["signup_date"]) > pd.to_datetime(cutoff)]
        self.assertEqual(len(post_cutoff_signups), 0, "No post-cutoff signups should be in feature matrix")

        # 2. Max order date in active customers must be <= cutoff
        active = feats[feats["completed_orders"] > 0]
        max_order_dt = pd.to_datetime(active["last_order_date"]).max()
        self.assertLessEqual(max_order_dt, pd.to_datetime(cutoff))

        # 3. Recency days >= 0
        self.assertTrue((feats["recency_days"] >= 0).all())

        # 4. Account age days >= 0
        self.assertTrue((feats["account_age_days"] >= 0).all())

        # 5. Customer lifetime days >= 0
        self.assertTrue((feats["customer_lifetime_days"] >= 0).all())

        # 6. Recent ratios in [0, 1]
        self.assertTrue(((feats["recent_revenue_ratio"] >= 0.0) & (feats["recent_revenue_ratio"] <= 1.0)).all())
        self.assertTrue(((feats["recent_order_ratio"] >= 0.0) & (feats["recent_order_ratio"] <= 1.0)).all())

    def test_scaler_preprocessor_isolation(self):
        """Preprocessor Isolation: StandardScaler is fit solely on training data with zero test leakage."""
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
        pipeline.train_and_evaluate(X_train, y_train, X_test, y_test)

        # Verify scaler mean matches training features mean exactly
        expected_train_means = X_train.mean(axis=0).values
        np.testing.assert_allclose(
            pipeline.scaler.mean_,
            expected_train_means,
            rtol=1e-3,
            err_msg="StandardScaler mean_ must derive exclusively from training set"
        )


class TestModelPerformanceQA(unittest.TestCase):
    """Section 6 (cont): Model performance verification, scorecard audit, and threshold trade-offs."""

    @classmethod
    def setUpClass(cls):
        metrics_path = MODELS_DIR / "model_metrics.json"
        with open(metrics_path, "r", encoding="utf-8") as f:
            cls.metrics = json.load(f)

    def test_model_artifacts_exist_and_load(self):
        """Verify that persisted model artifacts exist and load without error."""
        lr_path = MODELS_DIR / "logistic_regression.joblib"
        rf_path = MODELS_DIR / "random_forest.joblib"
        scaler_path = MODELS_DIR / "scaler.joblib"

        self.assertTrue(lr_path.exists())
        self.assertTrue(rf_path.exists())
        self.assertTrue(scaler_path.exists())

        lr_model = joblib.load(lr_path)
        rf_model = joblib.load(rf_path)
        scaler = joblib.load(scaler_path)

        self.assertIsNotNone(lr_model)
        self.assertIsNotNone(rf_model)
        self.assertIsNotNone(scaler)

    def test_logistic_regression_scorecard(self):
        """Verify Logistic Regression (Primary Model) test set metrics and confusion matrix."""
        lr_m = self.metrics["logistic_regression"]["metrics"]
        self.assertEqual(lr_m["roc_auc"], 0.9481, "ROC-AUC must be 0.9481")
        self.assertEqual(lr_m["accuracy"], 0.8729, "Accuracy must be 0.8729")
        self.assertEqual(lr_m["precision"], 0.9439, "Precision must be 0.9439")
        self.assertEqual(lr_m["recall"], 0.8418, "Recall must be 0.8418")
        self.assertEqual(lr_m["f1"], 0.8900, "F1 must be 0.8900")

        cm = lr_m["confusion_matrix"]
        self.assertEqual(cm["true_negative"], 3184)
        self.assertEqual(cm["false_positive"], 271)
        self.assertEqual(cm["false_negative"], 857)
        self.assertEqual(cm["true_positive"], 4561)
        total = cm["true_negative"] + cm["false_positive"] + cm["false_negative"] + cm["true_positive"]
        self.assertEqual(total, 8873, "Test set size must be 8,873")

    def test_random_forest_scorecard(self):
        """Verify Random Forest (Comparator Model) test set metrics and confusion matrix."""
        rf_m = self.metrics["random_forest"]["metrics"]
        self.assertEqual(rf_m["roc_auc"], 0.9510, "ROC-AUC must be 0.9510")
        self.assertEqual(rf_m["accuracy"], 0.8756, "Accuracy must be 0.8756")
        self.assertEqual(rf_m["precision"], 0.9687, "Precision must be 0.9687")
        self.assertEqual(rf_m["recall"], 0.8228, "Recall must be 0.8228")
        self.assertEqual(rf_m["f1"], 0.8898, "F1 must be 0.8898")

        cm = rf_m["confusion_matrix"]
        self.assertEqual(cm["true_negative"], 3311)
        self.assertEqual(cm["false_positive"], 144)
        self.assertEqual(cm["false_negative"], 960)
        self.assertEqual(cm["true_positive"], 4458)
        total = cm["true_negative"] + cm["false_positive"] + cm["false_negative"] + cm["true_positive"]
        self.assertEqual(total, 8873)

    def test_decision_threshold_tradeoffs(self):
        """Verify decision threshold trade-offs across {0.3, 0.4, 0.5, 0.6, 0.7}."""
        tradeoffs = self.metrics["logistic_regression"]["threshold_tradeoffs"]
        self.assertEqual(len(tradeoffs), 5)

        thresholds = [t["threshold"] for t in tradeoffs]
        precisions = [t["precision"] for t in tradeoffs]
        recalls = [t["recall"] for t in tradeoffs]

        self.assertEqual(thresholds, [0.3, 0.4, 0.5, 0.6, 0.7])

        # Precision strictly increases as threshold increases
        for i in range(len(precisions) - 1):
            self.assertLess(precisions[i], precisions[i + 1], "Precision must monotonically increase with threshold")

        # Recall strictly decreases as threshold increases
        for i in range(len(recalls) - 1):
            self.assertGreater(recalls[i], recalls[i + 1], "Recall must monotonically decrease with threshold")

        # Threshold 0.5 is balanced
        default_t = [t for t in tradeoffs if t["threshold"] == 0.5][0]
        self.assertEqual(default_t["precision"], 0.9439)
        self.assertEqual(default_t["recall"], 0.8418)


class TestPowerBIDataModelQA(unittest.TestCase):
    """Section 7: Power BI star-schema integrity, referential integrity, and metric equivalence."""

    @classmethod
    def setUpClass(cls):
        cls.dim_date = pd.read_csv(PBI_DIR / "dim_date.csv")
        cls.dim_products = pd.read_csv(PBI_DIR / "dim_products.csv")
        cls.dim_customers = pd.read_csv(PBI_DIR / "dim_customers.csv")
        cls.fact_orders = pd.read_csv(PBI_DIR / "fact_orders.csv")
        cls.dim_customer_analytics = pd.read_csv(PBI_DIR / "dim_customer_analytics.csv")

    def test_star_schema_tables_and_row_counts(self):
        """Verify exact row counts and primary key uniqueness across all star schema tables."""
        self.assertEqual(len(self.dim_date), 1096, "DimDate must have 1,096 rows")
        self.assertEqual(self.dim_date["date_id"].nunique(), 1096)

        self.assertEqual(len(self.dim_customers), 10000, "DimCustomers must have 10,000 rows")
        self.assertEqual(self.dim_customers["customer_id"].nunique(), 10000)

        self.assertEqual(len(self.dim_products), 492, "DimProducts must have 492 rows")
        self.assertEqual(self.dim_products["product_id"].nunique(), 492)

        self.assertEqual(len(self.fact_orders), 103695, "FactOrders must have 103,695 rows")
        self.assertEqual(self.fact_orders["order_id"].nunique(), 103695)

        self.assertEqual(len(self.dim_customer_analytics), 10000, "DimCustomerAnalytics must have 10,000 rows")
        self.assertEqual(self.dim_customer_analytics["customer_id"].nunique(), 10000)

    def test_star_schema_referential_integrity_zero_orphans(self):
        """Verify that every foreign key in FactOrders resolves cleanly with zero orphans."""
        cust_ids = set(self.dim_customers["customer_id"])
        prod_ids = set(self.dim_products["product_id"])
        date_ids = set(self.dim_date["date_id"])

        self.assertTrue(set(self.fact_orders["customer_id"]).issubset(cust_ids))
        self.assertTrue(set(self.fact_orders["product_id"]).issubset(prod_ids))
        self.assertTrue(set(self.fact_orders["order_date_id"]).issubset(date_ids))
        self.assertEqual(set(self.dim_customer_analytics["customer_id"]), cust_ids)

    def test_financial_and_metric_reconciliation(self):
        """Verify FactOrders and DimCustomerAnalytics match Phase 3 and Phase 4 financials exactly."""
        net_revenue = round(self.fact_orders["net_revenue"].sum(), 2)
        gross_profit = round(self.fact_orders["net_profit"].sum(), 2)
        gross_margin = round((gross_profit / net_revenue) * 100.0, 2)
        analytics_rev = round(self.dim_customer_analytics["total_revenue"].sum(), 2)

        self.assertEqual(net_revenue, 31028579.95)
        self.assertEqual(gross_profit, 12461250.73)
        self.assertEqual(gross_margin, 40.16)
        self.assertEqual(analytics_rev, 31028579.95)

    def test_risk_tier_distribution_and_exposure(self):
        """Verify risk tiers, customer counts, and historical revenue exposure."""
        risk_summary = self.dim_customer_analytics.groupby("risk_level").agg(
            cust_count=("customer_id", "count"),
            revenue=("total_revenue", "sum")
        ).round(2).to_dict(orient="index")

        expected_risk = {
            "LOW": (3684, 19662873.78),
            "MEDIUM": (2042, 898811.08),
            "HIGH": (2495, 7757734.63),
            "CRITICAL": (1779, 2709160.46),
        }

        for tier, (exp_count, exp_rev) in expected_risk.items():
            self.assertIn(tier, risk_summary)
            self.assertEqual(risk_summary[tier]["cust_count"], exp_count)
            self.assertAlmostEqual(risk_summary[tier]["revenue"], exp_rev, places=1)

        # High + Critical combined
        high_crit = self.dim_customer_analytics[self.dim_customer_analytics["risk_level"].isin(["HIGH", "CRITICAL"])]
        self.assertEqual(len(high_crit), 4274)
        combined_exposure = round(high_crit["total_revenue"].sum(), 2)
        self.assertEqual(combined_exposure, 10466895.09)


class TestPipelineReproducibilityQA(unittest.TestCase):
    """Section 8: Pipeline configuration integrity, random seed control, and environment verification."""

    def test_random_seed_and_config_determinism(self):
        """Verify global random seed and configuration settings."""
        self.assertEqual(settings.random_seed, 42)
        self.assertEqual(settings.project_name, "customer-analytics-platform")

        # Load raw config dictionary directly
        cfg = load_config()
        self.assertEqual(cfg.random_seed, 42)
        self.assertEqual(cfg.project_name, "customer-analytics-platform")
        self.assertTrue(hasattr(cfg, "database"))
        self.assertTrue(hasattr(cfg, "analytics"))

    def test_critical_dependencies_and_environment(self):
        """Verify that all production runtime packages are installed and importable."""
        import pandas as pd
        import numpy as np
        import sklearn
        import scipy
        import joblib
        import yaml
        import sqlalchemy
        import sqlite3

        self.assertTrue(pd.__version__ != "")
        self.assertTrue(np.__version__ != "")
        self.assertTrue(sklearn.__version__ != "")
        self.assertTrue(scipy.__version__ != "")
        self.assertTrue(joblib.__version__ != "")
        self.assertTrue(yaml.__version__ != "")
        self.assertTrue(sqlalchemy.__version__ != "")
        self.assertTrue(sqlite3.sqlite_version != "")


if __name__ == "__main__":
    unittest.main()
