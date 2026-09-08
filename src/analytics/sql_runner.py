"""SQL Execution and Business Analytics Engine.

Executes all analytical SQL scripts and views against the staging database,
validates reconciliation metrics, and compiles real quantitative insights.
"""

from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Tuple
import pandas as pd

from src.config.paths import PROCESSED_DATA_DIR, RAW_DATA_DIR, SQL_DIR
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLAnalyticsRunner:
    """Executes SQL analytics queries and compiles commercial scorecards."""

    def __init__(self, db_path: Path = PROCESSED_DATA_DIR / "staging.db"):
        self.db_path = db_path
        if not self.db_path.exists():
            raise FileNotFoundError(f"Staging database not found at {self.db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """Create and return an active sqlite3 connection."""
        return sqlite3.connect(self.db_path)

    def initialize_views(self) -> None:
        """Execute sql/views.sql to establish the core analytical view layer."""
        views_file = SQL_DIR / "views.sql"
        logger.info("Initializing analytical views from %s...", views_file)
        with open(views_file, "r", encoding="utf-8") as f:
            sql_script = f.read()

        with self.get_connection() as conn:
            conn.executescript(sql_script)
        logger.info("Successfully created view 'v_order_analytics'.")

    def execute_query(self, query: str) -> pd.DataFrame:
        """Execute a single SELECT query and return result as a pandas DataFrame."""
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn)

    def run_reconciliation(self) -> Dict[str, Any]:
        """Compute strict mathematical reconciliation from raw to analytical layers."""
        raw_cust_len = len(pd.read_csv(RAW_DATA_DIR / "customers.csv"))
        raw_prod_len = len(pd.read_csv(RAW_DATA_DIR / "products.csv"))
        raw_ord_len = len(pd.read_csv(RAW_DATA_DIR / "orders.csv"))
        total_raw = raw_cust_len + raw_prod_len + raw_ord_len

        with self.get_connection() as conn:
            valid_cust = pd.read_sql_query("SELECT COUNT(1) FROM customers", conn).iloc[0, 0]
            valid_prod = pd.read_sql_query("SELECT COUNT(1) FROM products", conn).iloc[0, 0]
            valid_ord = pd.read_sql_query("SELECT COUNT(1) FROM orders", conn).iloc[0, 0]
            total_valid = valid_cust + valid_prod + valid_ord

            rej_cust = pd.read_sql_query("SELECT COUNT(1) FROM rejected_records WHERE table_name = 'customers'", conn).iloc[0, 0]
            rej_prod = pd.read_sql_query("SELECT COUNT(1) FROM rejected_records WHERE table_name = 'products'", conn).iloc[0, 0]
            rej_ord = pd.read_sql_query("SELECT COUNT(1) FROM rejected_records WHERE table_name = 'orders'", conn).iloc[0, 0]
            total_rej = rej_cust + rej_prod + rej_ord

            view_ord = pd.read_sql_query("SELECT COUNT(1) FROM v_order_analytics", conn).iloc[0, 0]

        reconciliation = {
            "customers": {
                "raw": raw_cust_len,
                "valid": valid_cust,
                "rejected": rej_cust,
                "sum_valid_rejected": valid_cust + rej_cust,
                "reconciled": raw_cust_len == (valid_cust + rej_cust),
            },
            "products": {
                "raw": raw_prod_len,
                "valid": valid_prod,
                "rejected": rej_prod,
                "sum_valid_rejected": valid_prod + rej_prod,
                "reconciled": raw_prod_len == (valid_prod + rej_prod),
            },
            "orders": {
                "raw": raw_ord_len,
                "valid": valid_ord,
                "rejected": rej_ord,
                "sum_valid_rejected": valid_ord + rej_ord,
                "reconciled": raw_ord_len == (valid_ord + rej_ord),
                "analytical_view_rows": view_ord,
                "view_matches_valid_orders": valid_ord == view_ord,
            },
            "total_records": {
                "raw": total_raw,
                "valid": total_valid,
                "rejected": total_rej,
                "sum_valid_rejected": total_valid + total_rej,
                "fully_reconciled": total_raw == (total_valid + total_rej),
            },
        }
        return reconciliation

    def run_all_analytics(self) -> Dict[str, Any]:
        """Execute full suite of analytics queries and capture exact metrics."""
        self.initialize_views()
        reconciliation = self.run_reconciliation()

        logger.info("Executing customer analytics queries...")
        # 1. Customer summary
        cust_summary = self.execute_query("""
            WITH customer_order_summary AS (
                SELECT
                    c.customer_id,
                    COUNT(v.order_id) AS total_orders,
                    SUM(CASE WHEN v.is_completed = 1 THEN 1 ELSE 0 END) AS completed_orders,
                    SUM(v.net_revenue) AS total_net_revenue
                FROM customers c
                LEFT JOIN v_order_analytics v ON c.customer_id = v.customer_id
                GROUP BY c.customer_id
            )
            SELECT
                COUNT(1) AS total_customers,
                SUM(CASE WHEN total_orders > 0 THEN 1 ELSE 0 END) AS active_customers,
                SUM(CASE WHEN total_orders = 0 THEN 1 ELSE 0 END) AS dormant_zero_orders,
                SUM(CASE WHEN completed_orders > 0 THEN 1 ELSE 0 END) AS customers_with_completed_orders,
                SUM(CASE WHEN completed_orders = 1 THEN 1 ELSE 0 END) AS one_time_buyers,
                SUM(CASE WHEN completed_orders >= 2 THEN 1 ELSE 0 END) AS repeat_buyers,
                ROUND(SUM(CASE WHEN completed_orders >= 2 THEN 1 ELSE 0 END) * 100.0 / NULLIF(SUM(CASE WHEN completed_orders > 0 THEN 1 ELSE 0 END), 0), 2) AS repeat_buyer_rate_pct,
                ROUND(SUM(total_net_revenue), 2) AS total_net_revenue,
                ROUND(SUM(total_net_revenue) / NULLIF(SUM(CASE WHEN completed_orders > 0 THEN 1 ELSE 0 END), 0), 2) AS avg_rev_per_paying_cust
            FROM customer_order_summary;
        """)

        # 2. Customer Pareto Concentration (Deciles)
        pareto_cust = self.execute_query("""
            WITH customer_spend AS (
                SELECT
                    customer_id,
                    ROUND(SUM(net_revenue), 2) AS customer_revenue
                FROM v_order_analytics
                WHERE is_completed = 1
                GROUP BY customer_id
            ),
            ranked_deciles AS (
                SELECT
                    customer_id,
                    customer_revenue,
                    NTILE(10) OVER (ORDER BY customer_revenue DESC) AS revenue_decile
                FROM customer_spend
            )
            SELECT
                revenue_decile,
                COUNT(customer_id) AS customer_count,
                ROUND(SUM(customer_revenue), 2) AS decile_revenue,
                ROUND(SUM(customer_revenue) * 100.0 / SUM(SUM(customer_revenue)) OVER(), 2) AS pct_of_total_revenue,
                ROUND(SUM(SUM(customer_revenue)) OVER (ORDER BY revenue_decile ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) * 100.0 / SUM(SUM(customer_revenue)) OVER(), 2) AS cumulative_revenue_pct
            FROM ranked_deciles
            GROUP BY revenue_decile
            ORDER BY revenue_decile ASC;
        """)

        logger.info("Executing sales analytics queries...")
        # 3. Macro Sales Scorecard
        sales_scorecard = self.execute_query("""
            SELECT
                COUNT(order_id) AS total_order_volume,
                SUM(quantity) AS total_gross_units,
                SUM(is_completed) AS completed_orders,
                SUM(is_refunded) AS refunded_orders,
                SUM(is_cancelled) AS cancelled_orders,
                ROUND(SUM(gross_revenue), 2) AS total_gross_revenue,
                ROUND(SUM(refunded_amount), 2) AS total_refunded_amount,
                ROUND(SUM(cancelled_amount), 2) AS total_cancelled_amount,
                ROUND(SUM(net_revenue), 2) AS total_net_revenue,
                ROUND(SUM(CASE WHEN is_completed = 1 THEN total_cost ELSE 0 END), 2) AS total_realized_cogs,
                ROUND(SUM(net_profit), 2) AS total_net_profit,
                ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_gross_margin_pct,
                ROUND(SUM(net_revenue) / NULLIF(SUM(is_completed), 0), 2) AS aov
            FROM v_order_analytics;
        """)

        # 4. Annual Sales Performance
        annual_sales = self.execute_query("""
            WITH annual_metrics AS (
                SELECT
                    order_year,
                    SUM(is_completed) AS completed_orders,
                    ROUND(SUM(net_revenue), 2) AS annual_net_revenue,
                    ROUND(SUM(net_profit), 2) AS annual_net_profit,
                    ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS annual_margin_pct,
                    ROUND(SUM(net_revenue) / NULLIF(SUM(is_completed), 0), 2) AS annual_aov
                FROM v_order_analytics
                GROUP BY order_year
            )
            SELECT
                order_year,
                completed_orders,
                annual_net_revenue,
                annual_net_profit,
                annual_margin_pct,
                annual_aov,
                LAG(annual_net_revenue, 1) OVER (ORDER BY order_year) AS prev_year_revenue,
                ROUND((annual_net_revenue - LAG(annual_net_revenue, 1) OVER (ORDER BY order_year)) * 100.0 / NULLIF(LAG(annual_net_revenue, 1) OVER (ORDER BY order_year), 0), 2) AS yoy_revenue_growth_pct
            FROM annual_metrics
            ORDER BY order_year ASC;
        """)

        logger.info("Executing product analytics queries...")
        # 5. Category Performance
        category_perf = self.execute_query("""
            SELECT
                product_category,
                COUNT(DISTINCT product_id) AS active_products,
                SUM(is_completed) AS completed_orders,
                SUM(CASE WHEN is_completed = 1 THEN quantity ELSE 0 END) AS units_sold,
                ROUND(SUM(net_revenue), 2) AS total_net_revenue,
                ROUND(SUM(net_revenue) * 100.0 / SUM(SUM(net_revenue)) OVER(), 2) AS revenue_share_pct,
                ROUND(SUM(net_profit), 2) AS total_net_profit,
                ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_gross_margin_pct
            FROM v_order_analytics
            GROUP BY product_category
            ORDER BY total_net_revenue DESC;
        """)

        # 6. Top 5 Products
        top_products = self.execute_query("""
            SELECT
                product_id,
                product_name,
                product_category,
                unit_price,
                unit_cost,
                SUM(is_completed) AS completed_orders,
                ROUND(SUM(net_revenue), 2) AS product_net_revenue,
                ROUND(SUM(net_profit), 2) AS product_net_profit,
                ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_margin_pct
            FROM v_order_analytics
            WHERE is_completed = 1
            GROUP BY product_id, product_name, product_category, unit_price, unit_cost
            ORDER BY product_net_revenue DESC
            LIMIT 5;
        """)

        logger.info("Executing data quality analytics queries...")
        # 7. DLQ Breakdown
        dlq_breakdown = self.execute_query("""
            SELECT
                table_name,
                rejection_reason,
                COUNT(1) AS quarantined_count,
                ROUND(COUNT(1) * 100.0 / SUM(COUNT(1)) OVER(), 2) AS pct_of_dlq
            FROM rejected_records
            GROUP BY table_name, rejection_reason
            ORDER BY quarantined_count DESC;
        """)

        results = {
            "reconciliation": reconciliation,
            "customer_summary": cust_summary.to_dict(orient="records")[0],
            "customer_pareto": pareto_cust.to_dict(orient="records"),
            "sales_scorecard": sales_scorecard.to_dict(orient="records")[0],
            "annual_sales": annual_sales.to_dict(orient="records"),
            "category_performance": category_perf.to_dict(orient="records"),
            "top_products": top_products.to_dict(orient="records"),
            "dlq_breakdown": dlq_breakdown.to_dict(orient="records"),
        }
        return results


def main():
    runner = SQLAnalyticsRunner()
    results = runner.run_all_analytics()

    rec = results["reconciliation"]
    sales = results["sales_scorecard"]
    cust = results["customer_summary"]

    print("\n" + "=" * 80)
    print("PHASE 3 SQL BUSINESS ANALYTICS EXECUTION COMPLETE")
    print("=" * 80)

    print("\n[1] DATA RECONCILIATION SUMMARY")
    print("-" * 75)
    print(f"{'Entity':<12} | {'Raw Extracted':>14} | {'Valid (Staging)':>15} | {'DLQ Quarantined':>15} | {'Reconciled':>10}")
    print("-" * 75)
    for ent in ["customers", "products", "orders"]:
        r = rec[ent]
        print(f"{ent.capitalize():<12} | {r['raw']:>14,d} | {r['valid']:>15,d} | {r['rejected']:>15,d} | {str(r['reconciled']):>10}")
    print("-" * 75)
    t = rec["total_records"]
    print(f"{'TOTAL':<12} | {t['raw']:>14,d} | {t['valid']:>15,d} | {t['rejected']:>15,d} | {str(t['fully_reconciled']):>10}")
    print(f"Analytical View Rows (v_order_analytics) : {rec['orders']['analytical_view_rows']:,d} (Matches Valid Orders: {rec['orders']['view_matches_valid_orders']})")

    print("\n[2] MACRO COMMERCIAL SCORECARD")
    print("-" * 75)
    print(f"• Total Order Volume (Clean Staging) : {sales['total_order_volume']:,d}")
    print(f"• Completed / Shipped Orders        : {sales['completed_orders']:,d} ({sales['completed_orders']/sales['total_order_volume']*100:.2f}%)")
    print(f"• Legitimate Refunded Orders         : {sales['refunded_orders']:,d} ({sales['refunded_orders']/sales['total_order_volume']*100:.2f}%)")
    print(f"• Cancelled Orders                   : {sales['cancelled_orders']:,d} ({sales['cancelled_orders']/sales['total_order_volume']*100:.2f}%)")
    print(f"• Total Gross Invoiced Revenue       : ${sales['total_gross_revenue']:,.2f}")
    print(f"• Total Refunded Amount              : ${sales['total_refunded_amount']:,.2f}")
    print(f"• Total Cancelled Amount             : ${sales['total_cancelled_amount']:,.2f}")
    print(f"• Total Net Realized Revenue         : ${sales['total_net_revenue']:,.2f}")
    print(f"• Total Realized COGS                : ${sales['total_realized_cogs']:,.2f}")
    print(f"• Total Net Profit                   : ${sales['total_net_profit']:,.2f}")
    print(f"• Realized Gross Margin              : {sales['realized_gross_margin_pct']:.2f}%")
    print(f"• Average Order Value (AOV)          : ${sales['aov']:.2f}")

    print("\n[3] CUSTOMER BASE DYNAMICS")
    print("-" * 75)
    print(f"• Total Customer Accounts            : {cust['total_customers']:,d}")
    print(f"• Active Customers (with orders)     : {cust['active_customers']:,d}")
    print(f"• Dormant Customers (zero orders)    : {cust['dormant_zero_orders']:,d}")
    print(f"• Paying Customers (completed orders): {cust['customers_with_completed_orders']:,d}")
    print(f"• Repeat Buyers (>=2 orders)         : {cust['repeat_buyers']:,d} ({cust['repeat_buyer_rate_pct']:.2f}% of paying)")
    print(f"• One-Time Buyers                    : {cust['one_time_buyers']:,d}")
    print(f"• Average Revenue Per Paying Cust    : ${cust['avg_rev_per_paying_cust']:,.2f}")

    print("\n[4] CATEGORY CONTRIBUTION BREAKDOWN")
    print("-" * 75)
    for cat in results["category_performance"]:
        print(f"  * {cat['product_category']:<24} : Net Rev: ${cat['total_net_revenue']:>11,.2f} ({cat['revenue_share_pct']:>5.2f}%) | Profit: ${cat['total_net_profit']:>10,.2f} | Margin: {cat['realized_gross_margin_pct']:>5.2f}%")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
