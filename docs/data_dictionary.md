\# Data dictionary



All timestamps are UTC. Database: `control\_tower` (PostgreSQL).



\## Dimensions

| Table | Columns |

|---|---|

| dim\_supplier | supplier\_id, name, country, avg\_lead\_days, on\_time\_prob (simulator parameter) |

| dim\_product | product\_id, name, category, supplier\_id, reorder\_point |

| dim\_warehouse | warehouse\_id, name, city |



\## Facts (one row per hour, product and warehouse unless stated)

| Table | Columns | Notes |

|---|---|---|

| fact\_sales | ts, product\_id, warehouse\_id, units\_sold | Capped at available stock |

| fact\_inventory | ts, product\_id, warehouse\_id, stock\_units | End-of-hour stock |

| fact\_shipments | shipment\_id, supplier\_id, product\_id, warehouse\_id, order\_ts, promised\_ts, delivered\_ts, qty, status, sim\_arrival\_ts | One row per purchase order. delivered\_ts is NULL while in transit. sim\_arrival\_ts is the simulated true arrival |



\## Pipeline tables

| Table | Columns | Written by |

|---|---|---|

| kpi\_hourly | ts, stockout\_count, total\_items, stockout\_rate, avg\_days\_of\_inventory, units\_sold | refresh\_kpis |

| anomalies | anomaly\_key, anomaly\_type, supplier\_id, product\_id, shipment\_id, ts, value, baseline, score, detected\_at | detect\_anomalies |

| demand\_forecast | product\_id, ds, yhat, yhat\_lower, yhat\_upper, generated\_at | forecast\_demand |

| forecast\_accuracy | product\_id, mape, wape, baseline\_wape | forecast\_demand |

| alerts\_log | alert\_key, alert\_type, severity, message, channel, created\_at | send\_alerts |

| sim\_params | product\_id, warehouse\_id, base\_rate | simulator (hourly demand rate) |

| anomaly\_truth | anomaly\_type, supplier\_id, product\_id, start\_ts, end\_ts, description | simulator (ground truth, used only for evaluation) |



\## Views

| View | Purpose |

|---|---|

| v\_inventory\_doi | Days of inventory per product, warehouse and hour (stock / 7-day average daily sales) |

| v\_current\_inventory | Latest snapshot with status OK, LOW or STOCK-OUT |

| v\_supplier\_kpis | On-time %, average and p90 lead time per supplier |

| v\_supplier\_daily | Daily supplier trend |

| v\_kpi\_summary | One-row summary for the dashboard big numbers |

| v\_forecast\_vs\_stock | Forecast demand vs stock and inbound orders, with a risk flag |

| v\_demand\_actual\_vs\_forecast | Actual and forecast daily demand for charts |

| v\_anomaly\_feed | Readable anomaly list |

| v\_whatif, v\_whatif\_summary | Supplier-delay scenarios for 0, 3, 7 and 14 days |



\## KPI definitions

\- \*\*Stock-out rate\*\* = product-warehouse pairs with stock 0 / all pairs, per hour.

\- \*\*On-time delivery %\*\* = deliveries with delivered\_ts <= promised\_ts / all delivered.

\- \*\*Supplier lead time\*\* = delivered\_ts minus order\_ts, in days (average and p90).

\- \*\*Days of inventory\*\* = current stock / average daily sales over the last 7 days.

