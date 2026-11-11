from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

from simulator.step import run as simulate_hour

default_args = {
    "owner": "control-tower",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="control_tower_hourly",
    description="Hourly refresh: new inventory, sales and shipment data",
    start_date=datetime(2026, 11, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["control-tower"],
) as dag:

    ingest = PythonOperator(task_id="simulate_hour", python_callable=simulate_hour)

    # Later days add: kpis >> anomalies >> forecast >> alerts
