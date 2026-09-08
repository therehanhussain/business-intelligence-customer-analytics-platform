"""Inspect database tables and row counts in the staging database."""

import sqlite3
from src.config.paths import PROCESSED_DATA_DIR

def inspect_db():
    db_path = PROCESSED_DATA_DIR / "staging.db"
    if not db_path.exists():
        print("staging.db does not exist.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Database Tables in Staging Warehouse:")
    for (tbl_name,) in sorted(tables):
        cursor.execute(f"SELECT COUNT(*) FROM {tbl_name};")
        row_cnt = cursor.fetchone()[0]
        print(f"  * Table '{tbl_name:<20}' : {row_cnt:>8,d} rows")
    conn.close()

if __name__ == "__main__":
    inspect_db()
