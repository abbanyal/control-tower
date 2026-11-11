from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

from simulator.step import run as simulate_hour
from kpi.refresh import run as refresh_kpis

default_args = {
    "owner": "control-tower",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="control_tower_hourly",
    description="Hourly refresh: new data, then KPIs",
    start_date=datetime(2026, 11, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["control-tower"],
) as dag:

    ingest = PythonOperator(task_id="simulate_hour", python_callable=simulate_hour)
    kpis = PythonOperator(task_id="refresh_kpis", python_callable=refresh_kpis)

    ingest >> kpis

    # Later days add: >> anomalies >> forecast >> alerts
