"""Unit test suite for Phase 5 Power BI Data Model, Star Schema Integrity, and Metric Reconciliation."""

from pathlib import Path
import unittest
import pandas as pd

from src.config.paths import PROCESSED_DATA_DIR

PBI_DIR = PROCESSED_DATA_DIR / "powerbi"


class TestPowerBIDataModel(unittest.TestCase):
    """Rigorous QA verifying Power BI star-schema tables, referential integrity, and KPI reconciliation."""

    @classmethod
    def setUpClass(cls):
        cls.dim_date = pd.read_csv(PBI_DIR / "dim_date.csv")
        cls.dim_products = pd.read_csv(PBI_DIR / "dim_products.csv")
        cls.dim_customers = pd.read_csv(PBI_DIR / "dim_customers.csv")
        cls.fact_orders = pd.read_csv(PBI_DIR / "fact_orders.csv")
        cls.dim_customer_analytics = pd.read_csv(PBI_DIR / "dim_customer_analytics.csv")

    def test_star_schema_referential_integrity(self):
        """Verify that foreign keys in FactOrders resolve cleanly into primary dimension tables with zero orphans."""
        cust_ids = set(self.dim_customers["customer_id"])
        prod_ids = set(self.dim_products["product_id"])
        date_ids = set(self.dim_date["date_id"])

        fact_cust_ids = set(self.fact_orders["customer_id"])
        fact_prod_ids = set(self.fact_orders["product_id"])
        fact_date_ids = set(self.fact_orders["order_date_id"])

        self.assertTrue(fact_cust_ids.issubset(cust_ids), "All order customer_ids must exist in DimCustomer")
        self.assertTrue(fact_prod_ids.issubset(prod_ids), "All order product_ids must exist in DimProduct")
        self.assertTrue(fact_date_ids.issubset(date_ids), "All order date_ids must exist in DimDate")

        analytics_cust_ids = set(self.dim_customer_analytics["customer_id"])
        self.assertEqual(analytics_cust_ids, cust_ids, "DimCustomerAnalytics must match DimCustomer 1-to-1")

    def test_fact_orders_cardinality_and_uniqueness(self):
        """Verify row count and order ID uniqueness in FactOrders."""
        self.assertEqual(len(self.fact_orders), 103695, "FactOrders must have exactly 103,695 rows")
        self.assertEqual(self.fact_orders["order_id"].nunique(), 103695, "FactOrders order_id must be unique")

    def test_revenue_and_profit_reconciliation(self):
        """Verify that Net Revenue and Gross Profit match Phase 3 and Phase 4 figures to the cent."""
        net_revenue = round(self.fact_orders["net_revenue"].sum(), 2)
        gross_profit = round(self.fact_orders["net_profit"].sum(), 2)
        gross_margin = round((gross_profit / net_revenue) * 100.0, 2)

        self.assertEqual(net_revenue, 31028579.95, "Net revenue must equal Phase 3 total: $31,028,579.95")
        self.assertEqual(gross_profit, 12461250.73, "Gross profit must equal Phase 3 total: $12,461,250.73")
        self.assertEqual(gross_margin, 40.16, "Gross margin % must equal 40.16%")

    def test_customer_and_product_counts(self):
        """Verify dimension record counts."""
        self.assertEqual(len(self.dim_customers), 10000)
        self.assertEqual(self.dim_customers["customer_id"].nunique(), 10000)
        self.assertEqual(len(self.dim_products), 492)
        self.assertEqual(self.dim_products["product_id"].nunique(), 492)

    def test_rfm_segment_reconciliation(self):
        """Verify that customer counts and revenue per segment in DimCustomerAnalytics strictly match Phase 4."""
        seg_summary = self.dim_customer_analytics.groupby("customer_segment").agg(
            cust_count=("customer_id", "count"),
            revenue=("total_revenue", "sum")
        ).round(2).to_dict(orient="index")

        expected_segments = {
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

        for seg, (exp_count, exp_rev) in expected_segments.items():
            self.assertIn(seg, seg_summary)
            self.assertEqual(seg_summary[seg]["cust_count"], exp_count, f"Count mismatch for segment {seg}")
            self.assertAlmostEqual(seg_summary[seg]["revenue"], exp_rev, places=1, msg=f"Revenue mismatch for {seg}")

    def test_risk_tier_reconciliation(self):
        """Verify that risk populations and revenue exposure match Phase 4."""
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
            self.assertEqual(risk_summary[tier]["cust_count"], exp_count, f"Count mismatch for risk tier {tier}")
            self.assertAlmostEqual(risk_summary[tier]["revenue"], exp_rev, places=1, msg=f"Revenue mismatch for {tier}")

    def test_date_dimension_completeness(self):
        """Verify that DimDate covers the full transactional span with no gaps."""
        self.assertEqual(len(self.dim_date), 1096, "DimDate must have 1,096 days for 2022-2024")
        min_tx_date = self.fact_orders["order_date"].min()
        max_tx_date = self.fact_orders["order_date"].max()

        self.assertGreaterEqual(min_tx_date, self.dim_date["date"].min())
        self.assertLessEqual(max_tx_date, self.dim_date["date"].max())

    def test_fulfillment_and_friction_reconciliation(self):
        """Verify order status counts, refund metrics, and cancellation metrics match Phase 3."""
        status_counts = self.fact_orders["order_status"].value_counts().to_dict()
        self.assertEqual(status_counts["Completed"], 89283)
        self.assertEqual(status_counts["Shipped"], 6243)
        self.assertEqual(status_counts["Refunded"], 4087)
        self.assertEqual(status_counts["Cancelled"], 4082)

        total_refunded = round(self.fact_orders["refunded_amount"].sum(), 2)
        total_cancelled = round(self.fact_orders["cancelled_amount"].sum(), 2)
        self.assertEqual(total_refunded, 1334921.53)
        self.assertEqual(total_cancelled, 1363385.23)


if __name__ == "__main__":
    unittest.main()
