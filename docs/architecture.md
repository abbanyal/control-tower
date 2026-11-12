\# Architecture



```mermaid

flowchart LR

&#x20; SIM\[Python simulator step.py] --> PG\[(PostgreSQL control\_tower)]

&#x20; subgraph Airflow\[Airflow DAG hourly]

&#x20;   T1\[simulate\_hour] --> T2\[refresh\_kpis] --> T3\[detect\_anomalies] --> T4\[forecast\_demand Prophet daily] --> T5\[send\_alerts]

&#x20; end

&#x20; Airflow <--> PG

&#x20; PG --> SS\[Superset dashboards: Executive, Inventory, Suppliers, What-If]

&#x20; T5 --> MP\[Email via SMTP, Mailpit inbox]

```



Data flow: the simulator appends hourly sales, inventory and shipments. SQL views compute the KPIs.

Z-score detectors flag supplier delays and demand spikes. Prophet forecasts 14 days of demand per

product, compared with stock and inbound shipments. Threshold alerts go out by email and are

de-duplicated through alerts\_log. Superset reads views directly from PostgreSQL.

