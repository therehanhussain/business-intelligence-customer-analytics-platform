"""Inspect sample records in the Dead-Letter Queue (rejected_records)."""

import sqlite3
import pandas as pd
from src.config.paths import PROCESSED_DATA_DIR

def inspect_dlq():
    db_path = PROCESSED_DATA_DIR / "staging.db"
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT table_name, rejection_reason, COUNT(*) as count FROM rejected_records GROUP BY table_name, rejection_reason ORDER BY count DESC;", conn)
    print("\nDead-Letter Queue (DLQ) Aggregation by Reason:")
    print(df.to_string(index=False))

    print("\nSample Quarantined Records from rejected_records:")
    samples = pd.read_sql_query("SELECT table_name, record_identifier, rejection_reason, raw_payload FROM rejected_records GROUP BY rejection_reason LIMIT 6;", conn)
    for idx, row in samples.iterrows():
        print(f"\n[{row['table_name']}] ID: {row['record_identifier']} | Reason: {row['rejection_reason']}")
        print(f"  Payload: {row['raw_payload'][:120]}...")
    conn.close()

if __name__ == "__main__":
    inspect_dlq()
