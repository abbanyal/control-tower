\# Retail and Supply Chain Control Tower



A near real-time view of inventory, deliveries and suppliers that warns about problems before they hurt sales.

Built with PostgreSQL, Airflow, Python, Prophet, Superset and email alerts.



\## What it does

\- Refreshes simulated inventory, sales and shipment data \*\*every hour\*\* (Airflow).

\- Computes four KPIs: \*\*stock-out rate, on-time delivery, supplier lead time, days of inventory\*\*.

\- Detects \*\*supplier delays\*\* and \*\*demand spikes\*\* with z-scores, scored against injected ground truth.

\- Forecasts \*\*14 days of demand per product\*\* with Prophet and compares it with stock and inbound orders.

\- Shows everything in \*\*four Superset dashboards\*\*, including a \*\*what-if panel\*\* ("supplier delayed by N days").

\- Sends \*\*email alerts\*\* when thresholds are crossed (de-duplicated, one alert per day).



\## Architecture

See \[docs/architecture.md](docs/architecture.md).



DAG `control\_tower\_hourly`: `simulate\_hour >> refresh\_kpis >> detect\_anomalies >> forecast\_demand >> send\_alerts`



\## Screenshots

| | |

|---|---|

| Executive | !\[exec](docs/screenshots/exec.png) |

| Inventory | !\[inventory](docs/screenshots/inventory.png) |

| Suppliers | !\[suppliers](docs/screenshots/suppliers.png) |

| What-if (7-day delay) | !\[whatif](docs/screenshots/whatif\_delay7.png) |

| Email alert | !\[alert](docs/screenshots/mailpit\_alert.png) |



\## Data

Dataset option 5: simulated hourly feeds (60 days, 5 suppliers, 20 products, 3 warehouses).

Two anomalies are injected on purpose and stored in `anomaly\_truth`, so detection accuracy can be measured:

a +5 day delay from CorePack Ltd and a 5x demand spike on Soap 4-pack for 10 hours.

Full column documentation: \[docs/data\_dictionary.md](docs/data\_dictionary.md).



\## Setup

Requirements: Docker Desktop, Python 3.10+, Git. About 6 GB of free RAM.



```bash

git clone https://github.com/abbanyal/control-tower.git

cd control-tower

docker compose up -d --build

```

Wait 2 to 3 minutes for all services, then check `docker compose ps`.



Load the history (run on the host, in a virtual environment):

```bash

python -m venv .venv

.venv\\Scripts\\activate          # Windows. On Linux/Mac: source .venv/bin/activate

pip install numpy pandas psycopg2-binary pytest

python src/simulator/generate\_data.py

python src/anomaly/detect.py     # one-time backfill over the full history

```

Then open Airflow, switch on `control\_tower\_hourly` and trigger it once. The forecast task runs on

the first trigger and then once a day.



| Service | URL | Login |

|---|---|---|

| Airflow | http://localhost:8080 | admin / admin |

| Superset | http://localhost:8088 | admin / admin |

| Mailpit (alert inbox) | http://localhost:8025 | none |

| PostgreSQL | localhost:5433 | ct\_user / ct\_pass, db `control\_tower` |



\### Superset dashboards

Import `superset/control\_tower\_dashboards.zip` (Dashboards, then the import icon). When asked for the

database password, enter `ct\_pass`. If the import connection fails, create a PostgreSQL connection with

host `postgres`, port `5432`, database `control\_tower`, user `ct\_user`, then import again.



\## Alerts

`src/alerts/notify.py` runs as the last DAG task. Rules (override with environment variables):

\- Stock-out rate above 5 percent (`ALERT\_STOCKOUT\_RATE`)

\- Supplier on-time delivery below 80 percent over 7 days (`ALERT\_ONTIME\_MIN`)

\- Forecast days of cover below 5, or stock running out before delivery (`ALERT\_COVER\_DAYS`)

\- New anomalies in the last 2 hours



Alerts are emailed over SMTP. Locally they land in Mailpit. For real email, set `SMTP\_HOST`,

`SMTP\_PORT`, `SMTP\_USER`, `SMTP\_PASSWORD` and `ALERT\_EMAIL\_TO` in a `.env` file (git-ignored).

Each alert is logged in `alerts\_log` and sent once per day.



\## Results

Full tables in \[docs/results.md](docs/results.md).



\*\*Anomaly detection (scored against injected ground truth)\*\*



| Detector | Precision | Recall |

|---|---|---|

| Supplier delay (z >= 3, 3+ days late) | 1.00 | 1.00 |

| Demand spike, z >= 5.0 | 1.00 | 0.60 |

| Demand spike, z >= 3.5 | 0.30 | 1.00 |

| Demand spike, z >= 4.0 (final) | 0.71 | 1.00 |



\*\*Forecast (7-day holdout, 20 products):\*\* Prophet WAPE 13.0 percent, MAPE 13.7 percent. A naive

7-day average scored 11.4 percent WAPE, so \*\*Prophet did not beat the baseline\*\* on this simulated data.



\*\*What-if:\*\* a 3-day supplier delay puts at most 1 of 4 products per supplier at risk. A 7-day delay

puts all 4 at risk, with roughly 400 to 1,600 units of lost sales per supplier.



\*\*Tests:\*\* 14 pytest tests pass (`python -m pytest tests -v`). Output in `docs/pytest\_output.txt`.



\## Project layout

```

dags/        Airflow DAG

docker/      Dockerfiles and database init

sql/         schema, what-if and dashboard views

src/         simulator, kpi, anomaly, forecast, alerts

superset/    dashboard export and config

tests/       pytest suite

docs/        architecture, data dictionary, results, screenshots

```



\## Limitations and next steps

\- Data is simulated, so results are optimistic. The z >= 4 threshold was chosen after seeing this data.

\- Demand has no weekly pattern, which is why Prophet does not beat the naive baseline.

\- Spike detection would improve with a robust baseline (median and MAD), because the spike inflates the standard deviation.

\- The what-if model is simple: it uses days of cover and the supplier's average lead time when no order is open.

\- Next: real datasets (DataCo, Olist), Isolation Forest comparison, Slack alerts, per-warehouse forecasts.

