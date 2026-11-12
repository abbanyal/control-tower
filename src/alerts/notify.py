"""Threshold alerts -> Slack (or console if no webhook is set).
De-duplicated through alerts_log, so the same alert is not re-sent every hour."""
import os
import sys
import json
import urllib.request
from datetime import datetime
import psycopg2

DB = dict(host=os.getenv("PGHOST", "localhost"),
          port=int(os.getenv("PGPORT", "5433")),
          dbname=os.getenv("PGDATABASE", "control_tower"),
          user=os.getenv("PGUSER", "ct_user"),
          password=os.getenv("PGPASSWORD", "ct_pass"))

WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "")
STOCKOUT_RATE_MAX = float(os.getenv("ALERT_STOCKOUT_RATE", "0.05"))   # 5% of items out of stock
ONTIME_MIN_PCT = float(os.getenv("ALERT_ONTIME_MIN", "80"))           # supplier on-time % (7 days)
COVER_MIN_DAYS = float(os.getenv("ALERT_COVER_DAYS", "5"))            # forecast days of cover

DDL = """CREATE TABLE IF NOT EXISTS alerts_log (
  id SERIAL PRIMARY KEY, alert_key TEXT UNIQUE, alert_type TEXT, severity TEXT,
  message TEXT, channel TEXT, created_at TIMESTAMP DEFAULT now())"""


def send_slack(text):
    req = urllib.request.Request(WEBHOOK, data=json.dumps({"text": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status == 200


def collect(cur):
    """Returns a list of (alert_key, alert_type, severity, message)."""
    day = datetime.utcnow().strftime("%Y%m%d")
    out = []

    cur.execute("SELECT ts, stockout_rate FROM kpi_hourly ORDER BY ts DESC LIMIT 1")
    row = cur.fetchone()
    if row and row[1] is not None and row[1] > STOCKOUT_RATE_MAX:
        out.append((f"stockout_rate:{day}", "stockout_rate", "HIGH",
                    f"Stock-out rate is {row[1]:.1%} (limit {STOCKOUT_RATE_MAX:.0%}) at {row[0]}"))

    cur.execute("""SELECT product_id, product, supplier, days_of_cover, risk
                   FROM v_forecast_vs_stock
                   WHERE days_of_cover < %s OR risk IN ('RUNS OUT BEFORE DELIVERY', 'REORDER NOW')""",
                (COVER_MIN_DAYS,))
    for pid, prod, sup, cover, risk in cur.fetchall():
        sev = "HIGH" if risk in ("RUNS OUT BEFORE DELIVERY", "REORDER NOW") else "MEDIUM"
        out.append((f"cover:{pid}:{day}", "low_cover", sev,
                    f"{prod} ({sup}): {cover} days of cover, status {risk}"))

    cur.execute("""SELECT s.supplier_id, s.name, 100.0 * AVG((f.delivered_ts <= f.promised_ts)::int), COUNT(*)
                   FROM fact_shipments f JOIN dim_supplier s ON s.supplier_id = f.supplier_id
                   WHERE f.delivered_ts >= (SELECT MAX(ts) FROM fact_inventory) - interval '7 days'
                   GROUP BY 1, 2
                   HAVING COUNT(*) >= 5 AND 100.0 * AVG((f.delivered_ts <= f.promised_ts)::int) < %s""",
                (ONTIME_MIN_PCT,))
    for sid, name, pct, n in cur.fetchall():
        out.append((f"ontime:{sid}:{day}", "supplier_ontime", "HIGH",
                    f"{name}: on-time delivery {float(pct):.0f}% over the last 7 days ({n} deliveries, limit {ONTIME_MIN_PCT:.0f}%)"))

    cur.execute("""SELECT a.anomaly_key, a.anomaly_type, a.ts, a.value, a.baseline, a.score,
                          sp.name, p.name
                   FROM anomalies a
                   LEFT JOIN dim_product p ON p.product_id = a.product_id
                   LEFT JOIN dim_supplier sp ON sp.supplier_id = COALESCE(a.supplier_id, p.supplier_id)
                   WHERE a.detected_at > now()::timestamp - interval '2 hours'""")
    for key, typ, ts, val, base, score, sup, prod in cur.fetchall():
        what = "Demand spike" if typ == "demand_spike" else "Supplier delay"
        out.append((f"anom:{key}", typ, "HIGH",
                    f"{what}: {prod or ''} ({sup or ''}) value {val:.1f} vs normal {base:.1f}, z={score:.1f}, at {ts}"))
    return out


def run():
    conn = psycopg2.connect(**DB)
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        new = []
        for key, typ, sev, msg in collect(cur):
            cur.execute("SELECT 1 FROM alerts_log WHERE alert_key = %s", (key,))
            if not cur.fetchone():
                new.append((key, typ, sev, msg))
        if not new:
            print("No new alerts.")
            return 0
        lines = [f"[{sev}] {msg}" for _, _, sev, msg in new[:15]]
        if len(new) > 15:
            lines.append(f"...and {len(new) - 15} more")
        text = ":rotating_light: *Supply chain control tower*\n" + "\n".join(lines)
        channel = "console"
        if WEBHOOK:
            try:
                send_slack(text)
                channel = "slack"
            except Exception as e:
                print(f"Slack send failed, will retry next run: {e}")
                return 0          # nothing logged, so it is retried
        for key, typ, sev, msg in new:
            cur.execute("""INSERT INTO alerts_log (alert_key, alert_type, severity, message, channel)
                           VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                        (key, typ, sev, msg, channel))
        print(f"{len(new)} new alert(s) sent via {channel}:\n{text}")
        return len(new)


if __name__ == "__main__":
    if "--test" in sys.argv:
        if not WEBHOOK:
            sys.exit("SLACK_WEBHOOK_URL is not set")
        send_slack(":white_check_mark: Control Tower test alert. Slack is connected.")
        print("Test message sent.")
    else:
        run()
