"""Investigate representation of returns and negative quantities."""

import sqlite3
import json
import pandas as pd

conn = sqlite3.connect("data/processed/staging.db")

print("--- 1. Order Status Breakdown in Clean Valid Orders (staging.db) ---")
q1 = "SELECT order_status, COUNT(1) as order_count, SUM(quantity) as total_units FROM orders GROUP BY order_status"
print(pd.read_sql_query(q1, conn))

print("\n--- 2. Quantity Distribution for Refunded Orders in Clean Orders ---")
q2 = "SELECT quantity, COUNT(1) as count FROM orders WHERE order_status = 'Refunded' GROUP BY quantity"
print(pd.read_sql_query(q2, conn))

print("\n--- 3. Quarantined Orders in Dead-Letter Queue (staging.db) ---")
q3 = "SELECT rejection_reason, COUNT(1) as count FROM rejected_records WHERE table_name = 'orders' GROUP BY rejection_reason"
print(pd.read_sql_query(q3, conn))

print("\n--- 4. Inspection of Payloads in INVALID_QUANTITY_NEGATIVE_RETURN in DLQ ---")
q4 = "SELECT raw_payload FROM rejected_records WHERE rejection_reason = 'INVALID_QUANTITY_NEGATIVE_RETURN' LIMIT 5"
samples = pd.read_sql_query(q4, conn)
for idx, r in samples.iterrows():
    p = json.loads(r["raw_payload"])
    print(f"  Order {p.get('order_id')}: status={p.get('order_status')}, qty={p.get('quantity')}, cust={p.get('customer_id')}, prod={p.get('product_id')}")

conn.close()
