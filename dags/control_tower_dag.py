from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

from simulator.step import run as simulate_hour
from kpi.refresh import run as refresh_kpis
from anomaly.detect import run as detect_anomalies
from alerts.notify import run as send_alerts


def forecast_task():
    from forecast.prophet_forecast import run   # imported here so DAG parsing stays fast
    return run()


default_args = {
    "owner": "control-tower",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="control_tower_hourly",
    description="Hourly refresh: new data, KPIs, anomalies, forecast, alerts",
    start_date=datetime(2026, 11, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["control-tower"],
) as dag:

    ingest = PythonOperator(task_id="simulate_hour", python_callable=simulate_hour)
    kpis = PythonOperator(task_id="refresh_kpis", python_callable=refresh_kpis)
    anomalies = PythonOperator(task_id="detect_anomalies", python_callable=detect_anomalies,
                               op_kwargs={"lookback_hours": 24})
    forecast = PythonOperator(task_id="forecast_demand", python_callable=forecast_task,
                              retries=0, execution_timeout=timedelta(minutes=15))
    alerts = PythonOperator(task_id="send_alerts", python_callable=send_alerts,
                            trigger_rule="all_done")

    ingest >> kpis >> anomalies >> forecast >> alerts
