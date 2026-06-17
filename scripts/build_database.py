from pathlib import Path
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "placement_analytics.db"
SCHEMA_PATH = ROOT / "database" / "schema.sql"
DATA_DIR = ROOT / "data"


def load_csv(conn: sqlite3.Connection, table_name: str, file_name: str) -> None:
    frame = pd.read_csv(DATA_DIR / file_name)
    frame.to_sql(table_name, conn, if_exists="append", index=False)


def main() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as schema_file:
        conn.executescript(schema_file.read())

    load_csv(conn, "students", "students.csv")
    load_csv(conn, "companies", "companies.csv")
    load_csv(conn, "company_required_skills", "company_required_skills.csv")
    load_csv(conn, "placements", "placements.csv")
    load_csv(conn, "student_skills", "student_skills.csv")
    load_csv(conn, "users", "users.csv")
    conn.commit()
    conn.close()

    print(f"Database created: {DB_PATH}")


if __name__ == "__main__":
    main()
