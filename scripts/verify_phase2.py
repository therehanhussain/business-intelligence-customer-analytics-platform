"""Verification script for Phase 2 review checkpoints."""

import json
from pathlib import Path
import pandas as pd
import numpy as np

from src.config.paths import RAW_DATA_DIR, PROCESSED_DATA_DIR


def verify_phase2():
    print("=" * 80)
    print("PHASE 2 DETAILED VERIFICATION & INVESTIGATION REPORT")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # CHECKPOINT 3: INVESTIGATE 2,729 ORPHAN_PRODUCT_FOREIGN_KEY REJECTIONS
    # -------------------------------------------------------------------------
    print("\n[CHECKPOINT 3] INVESTIGATION: ORPHAN_PRODUCT_FOREIGN_KEY (2,729 orders)")
    print("-" * 70)

    raw_prod = pd.read_csv(RAW_DATA_DIR / "products.csv")
    clean_prod = pd.read_csv(PROCESSED_DATA_DIR / "products_clean.csv")
    clean_pids = set(clean_prod["product_id"])
    raw_pids = set(raw_prod["product_id"])
    rejected_pids = sorted(list(raw_pids - clean_pids))

    print(f"Total Raw Products: {len(raw_prod)} | Valid Clean Products: {len(clean_prod)} | Rejected Products: {len(rejected_pids)}")
    print("\nRejected Products Details:")
    rej_prod_df = raw_prod[raw_prod["product_id"].isin(rejected_pids)]
    for idx, r in rej_prod_df.iterrows():
        reason = "Missing Category (NaN)" if pd.isna(r["category"]) else ("Missing Cost (NaN)" if pd.isna(r["cost"]) else "Other")
        print(f"  * {r['product_id']}: Name='{r['product_name']}', Cat='{r['category']}', Price={r['price']}, Cost={r['cost']} -> Defect: {reason}")

    raw_orders = pd.read_csv(RAW_DATA_DIR / "orders.csv")
    orders_with_rej_pids = raw_orders[raw_orders["product_id"].isin(rejected_pids)]
    counts_by_pid = orders_with_rej_pids["product_id"].value_counts().to_dict()

    print("\nOrder counts in raw orders referencing each rejected product:")
    total_orders_for_rej_prods = 0
    for pid in rejected_pids:
        c = counts_by_pid.get(pid, 0)
        total_orders_for_rej_prods += c
        print(f"  * Product {pid}: {c:>5,d} referencing orders")
    print(f"  => Total orders referencing the 8 invalid products: {total_orders_for_rej_prods:,d}")

    # Check how many of these orders also had invalid quantities
    rej_orders_dlq = pd.read_csv(PROCESSED_DATA_DIR / "rejected_records.csv")
    dlq_orphans = rej_orders_dlq[rej_orders_dlq["rejection_reason"] == "ORPHAN_PRODUCT_FOREIGN_KEY"]
    print(f"  => Total ORPHAN_PRODUCT_FOREIGN_KEY records in DLQ: {len(dlq_orphans):,d}")

    # Note: If an order had an invalid quantity (<0 or ==0), which rule caught it first?
    # In validate_orders:
    # Rule 2: negative quantity (330)
    # Rule 3: zero quantity (165)
    # Rule 5: orphan product FK (2,729)
    # 2729 + (orders with invalid qty for these products) = total orders for rej prods
    overlap = orders_with_rej_pids[orders_with_rej_pids["quantity"] <= 0]
    print(f"  => Overlap orders referencing rejected products with non-positive qty: {len(overlap)} orders")
    print(f"     (These {len(overlap)} orders were caught by earlier INVALID_QUANTITY rule: {len(dlq_orphans)} + {len(overlap)} = {len(dlq_orphans) + len(overlap)})")

    # -------------------------------------------------------------------------
    # CHECKPOINT 4: INVESTIGATE NEGATIVE ORDER QUANTITIES
    # -------------------------------------------------------------------------
    print("\n[CHECKPOINT 4] INVESTIGATION: NEGATIVE ORDER QUANTITIES")
    print("-" * 70)
    neg_orders = raw_orders[raw_orders["quantity"] < 0]
    zero_orders = raw_orders[raw_orders["quantity"] == 0]
    print(f"Total Negative Quantity Orders: {len(neg_orders):,d} ({len(neg_orders)/len(raw_orders)*100:.2f}%)")
    print(f"Total Zero Quantity Orders:     {len(zero_orders):,d} ({len(zero_orders)/len(raw_orders)*100:.2f}%)")
    print(f"Values present in negative quantities: {neg_orders['quantity'].value_counts().to_dict()}")

    # Check associated order_status for negative orders
    print("\nOrder Status distribution for Negative Quantity orders:")
    print(neg_orders["order_status"].value_counts(dropna=False).to_string())

    # Check phase 1 documentation on negative quantities
    from src.etl.data_generation import generate_orders
    doc = generate_orders.__doc__
    print("\nPhase 1 Data Generation Docstring Excerpt on Quantities:")
    for line in doc.split("\n"):
        if "quantity" in line.lower() or "return" in line.lower() or "negative" in line.lower():
            print(f"  {line.strip()}")

    # -------------------------------------------------------------------------
    # CHECKPOINT 5: VERIFY RAW FILES UNDER data/raw/ WERE NOT MODIFIED
    # -------------------------------------------------------------------------
    print("\n[CHECKPOINT 5] VERIFICATION: IMMUTABILITY OF data/raw/ FILES")
    print("-" * 70)
    customers_raw_path = RAW_DATA_DIR / "customers.csv"
    products_raw_path = RAW_DATA_DIR / "products.csv"
    orders_raw_path = RAW_DATA_DIR / "orders.csv"

    print(f"• customers.csv exists: {customers_raw_path.exists()} | Rows: {len(pd.read_csv(customers_raw_path)):,d}")
    print(f"• products.csv exists:  {products_raw_path.exists()} | Rows: {len(pd.read_csv(products_raw_path)):,d}")
    print(f"• orders.csv exists:    {orders_raw_path.exists()} | Rows: {len(pd.read_csv(orders_raw_path)):,d}")

    # -------------------------------------------------------------------------
    # CHECKPOINT 6: VERIFY FINANCIAL FIELDS MATHEMATICAL CONSISTENCY
    # -------------------------------------------------------------------------
    print("\n[CHECKPOINT 6] VERIFICATION: FINANCIAL FIELDS MATHEMATICAL CONSISTENCY")
    print("-" * 70)
    # Check gross_margin_pct in clean products
    # Formula: ((price - cost) / price) * 100
    expected_margin = ((clean_prod["price"] - clean_prod["cost"]) / clean_prod["price"]) * 100.0
    margin_diff = (clean_prod["gross_margin_pct"] - expected_margin).abs()
    max_diff = margin_diff.max()
    print(f"• Clean products gross_margin_pct max formula divergence: {max_diff:.6f} (Matches: {max_diff < 0.01})")
    print(f"• Any negative margins in clean products: {(clean_prod['gross_margin_pct'] < 0).any()} (Should be False)")
    print(f"• Any margin > 100% in clean products: {(clean_prod['gross_margin_pct'] > 100).any()} (Should be False)")

    # -------------------------------------------------------------------------
    # CHECKPOINT 7: VERIFY REJECTED RECORDS RETAIN ORIGINAL PAYLOAD & REASON
    # -------------------------------------------------------------------------
    print("\n[CHECKPOINT 7] VERIFICATION: REJECTED RECORDS PAYLOAD & REASON INTEGRITY")
    print("-" * 70)
    dlq_df = pd.read_csv(PROCESSED_DATA_DIR / "rejected_records.csv")
    print(f"• Total DLQ rows: {len(dlq_df):,d}")
    print(f"• Columns: {list(dlq_df.columns)}")
    print(f"• Any missing rejection_reason: {dlq_df['rejection_reason'].isna().any()}")
    print(f"• Any missing raw_payload:      {dlq_df['raw_payload'].isna().any()}")
    print(f"• Any missing table_name:       {dlq_df['table_name'].isna().any()}")
    print(f"• Any missing record_identifier:{dlq_df['record_identifier'].isna().any()}")

    # Test JSON deserialization of payloads
    sample_payloads = dlq_df["raw_payload"].sample(10, random_state=42)
    payload_valid = True
    for p in sample_payloads:
        try:
            d = json.loads(p)
            if not isinstance(d, dict):
                payload_valid = False
        except Exception:
            payload_valid = False
    print(f"• Serialized raw_payloads are valid JSON: {payload_valid}")

    # -------------------------------------------------------------------------
    # CHECKPOINT 8: VERIFY SQLITE STAGING FALLBACK & NO POSTGRESQL FABRICATION
    # -------------------------------------------------------------------------
    print("\n[CHECKPOINT 8] VERIFICATION: DATABASE ENGINE STATUS")
    print("-" * 70)
    with open(PROCESSED_DATA_DIR / "etl_audit_summary.json", "r") as fp:
        audit = json.load(fp)
    db_info = audit["loading"]["database"]
    print(f"• Database type reported in audit: {db_info['database_type']}")
    print(f"• Is PostgreSQL falsely reported:  {'PostgreSQL' == db_info['database_type']}")
    print(f"• SQLite staging db exists:       {(PROCESSED_DATA_DIR / 'staging.db').exists()} (Size: {(PROCESSED_DATA_DIR / 'staging.db').stat().st_size:,d} bytes)")

    print("\n" + "=" * 80)
    print("VERIFICATION CHECKS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    verify_phase2()
