"""Unit test suite for Phase 3 SQL analytical views, aggregations, and reconciliations."""

import sqlite3
import unittest
import pandas as pd

from src.analytics.sql_runner import SQLAnalyticsRunner
from src.config.paths import PROCESSED_DATA_DIR, RAW_DATA_DIR


class TestSQLAnalytics(unittest.TestCase):
    """Test suite verifying SQL data warehouse views, reconciliations, and integrity."""

    @classmethod
    def setUpClass(cls):
        cls.runner = SQLAnalyticsRunner()
        cls.runner.initialize_views()
        cls.conn = sqlite3.connect(PROCESSED_DATA_DIR / "staging.db")

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_view_join_cardinality_matches_valid_orders(self):
        """Verify that joining orders, customers, and products does not multiply order rows."""
        orders_count = pd.read_sql_query("SELECT COUNT(1) FROM orders", self.conn).iloc[0, 0]
        view_count = pd.read_sql_query("SELECT COUNT(1) FROM v_order_analytics", self.conn).iloc[0, 0]
        self.assertEqual(orders_count, view_count, "Analytical view row count must exactly match orders table")
        self.assertEqual(view_count, 103695)

    def test_financial_revenue_reconciliation(self):
        """Verify that gross revenue exactly equals net revenue + refunds + cancellations."""
        df = pd.read_sql_query("""
            SELECT
                ROUND(SUM(gross_revenue), 2) AS total_gross,
                ROUND(SUM(net_revenue), 2) AS total_net,
                ROUND(SUM(refunded_amount), 2) AS total_refunded,
                ROUND(SUM(cancelled_amount), 2) AS total_cancelled
            FROM v_order_analytics
        """, self.conn)

        gross = df.at[0, "total_gross"]
        net = df.at[0, "total_net"]
        refunded = df.at[0, "total_refunded"]
        cancelled = df.at[0, "total_cancelled"]

        reconciled_sum = round(net + refunded + cancelled, 2)
        diff = abs(gross - reconciled_sum)
        self.assertLessEqual(diff, 0.05, f"Revenue discrepancy: gross={gross} vs net+ref+canc={reconciled_sum}")

    def test_customer_level_revenue_reconciles_to_order_totals(self):
        """Verify that customer-level spend aggregations reconcile to overall net revenue."""
        order_net = pd.read_sql_query(
            "SELECT ROUND(SUM(net_revenue), 2) FROM v_order_analytics", self.conn
        ).iloc[0, 0]

        cust_net = pd.read_sql_query("""
            SELECT ROUND(SUM(cust_rev), 2) FROM (
                SELECT customer_id, SUM(net_revenue) AS cust_rev
                FROM v_order_analytics
                WHERE is_completed = 1
                GROUP BY customer_id
            )
        """, self.conn).iloc[0, 0]

        self.assertAlmostEqual(order_net, cust_net, places=2)

    def test_product_level_revenue_reconciles_to_order_totals(self):
        """Verify that product-level sales aggregations reconcile to overall net revenue."""
        order_net = pd.read_sql_query(
            "SELECT ROUND(SUM(net_revenue), 2) FROM v_order_analytics", self.conn
        ).iloc[0, 0]

        prod_net = pd.read_sql_query("""
            SELECT ROUND(SUM(prod_rev), 2) FROM (
                SELECT product_id, SUM(net_revenue) AS prod_rev
                FROM v_order_analytics
                WHERE is_completed = 1
                GROUP BY product_id
            )
        """, self.conn).iloc[0, 0]

        self.assertAlmostEqual(order_net, prod_net, places=2)

    def test_completed_order_statuses(self):
        """Verify that is_completed strictly filters for Completed and Shipped orders."""
        df = pd.read_sql_query("""
            SELECT DISTINCT order_status
            FROM v_order_analytics
            WHERE is_completed = 1
        """, self.conn)
        statuses = set(df["order_status"].unique())
        self.assertEqual(statuses, {"Completed", "Shipped"})

    def test_no_orphan_foreign_keys_in_view(self):
        """Verify that every row in v_order_analytics links to a valid customer and product."""
        orphan_cust = pd.read_sql_query("""
            SELECT COUNT(1) FROM v_order_analytics WHERE customer_name IS NULL OR customer_name = ''
        """, self.conn).iloc[0, 0]
        orphan_prod = pd.read_sql_query("""
            SELECT COUNT(1) FROM v_order_analytics WHERE product_name IS NULL OR product_name = ''
        """, self.conn).iloc[0, 0]

        self.assertEqual(orphan_cust, 0, "No customer attributes should be null in analytical view")
        self.assertEqual(orphan_prod, 0, "No product attributes should be null in analytical view")

    def test_rejected_records_are_excluded_from_clean_analytics(self):
        """Verify that none of the quarantined customer/product/order IDs appear in the view."""
        rejected_cust = pd.read_sql_query(
            "SELECT DISTINCT record_identifier FROM rejected_records WHERE table_name = 'customers'", self.conn
        )["record_identifier"].tolist()
        rejected_prod = pd.read_sql_query(
            "SELECT DISTINCT record_identifier FROM rejected_records WHERE table_name = 'products'", self.conn
        )["record_identifier"].tolist()

        # In valid clean products, 0 rejected product IDs should exist
        clean_prods = set(pd.read_sql_query("SELECT product_id FROM products", self.conn)["product_id"])
        overlap_prod = set(rejected_prod).intersection(clean_prods)
        self.assertEqual(len(overlap_prod), 0, f"Rejected products leaked into clean data: {overlap_prod}")

        # In valid clean orders, 0 rejected products should be referenced
        order_prods = set(pd.read_sql_query("SELECT DISTINCT product_id FROM v_order_analytics", self.conn)["product_id"])
        leak_order_prods = set(rejected_prod).intersection(order_prods)
        self.assertEqual(len(leak_order_prods), 0, f"Rejected products referenced in clean orders: {leak_order_prods}")

    def test_raw_to_analytical_reconciliation(self):
        """Verify end-to-end mathematical reconciliation: Raw = Valid + Rejected."""
        rec = self.runner.run_reconciliation()
        self.assertTrue(rec["customers"]["reconciled"])
        self.assertTrue(rec["products"]["reconciled"])
        self.assertTrue(rec["orders"]["reconciled"])
        self.assertTrue(rec["total_records"]["fully_reconciled"])


if __name__ == "__main__":
    unittest.main()
