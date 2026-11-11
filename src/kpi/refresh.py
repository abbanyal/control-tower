"""Creates/refreshes KPI views and the kpi_hourly table. Safe to run repeatedly."""
import os
import pathlib
import psycopg2

DB = dict(host=os.getenv("PGHOST", "localhost"),
          port=int(os.getenv("PGPORT", "5433")),
          dbname=os.getenv("PGDATABASE", "control_tower"),
          user=os.getenv("PGUSER", "ct_user"),
          password=os.getenv("PGPASSWORD", "ct_pass"))

SQL_FILE = pathlib.Path(__file__).with_name("kpis.sql")


def run():
    conn = psycopg2.connect(**DB)
    with conn, conn.cursor() as cur:
        cur.execute(SQL_FILE.read_text())
        cur.execute("SELECT COUNT(*), MAX(ts) FROM kpi_hourly")
        n, latest = cur.fetchone()
    conn.close()
    print(f"kpi_hourly: {n} rows, latest hour {latest}")
    return n


if __name__ == "__main__":
    run()
