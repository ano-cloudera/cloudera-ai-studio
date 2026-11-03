# Semantic model for the fulfillment sample

Create **one model** (for example `fulfillment_delivery`) with the three entities below, then **Publish**. Pin it in
Settings -> General -> Ask Data -> Default semantic model. One model is required so two metrics from different tables can be combined (drill-across).

## Entity 1: `fulfillment_orders` (table `fulfillment_orders`)

Dimensions: `order_date` (time), `region_name`, `warehouse`, `channel`, `product_category`, `order_status`.

| Metric | Expression | Synonyms |
|---|---|---|
| Total Orders | `COUNT(order_id)` | number of orders, order count |
| Total Order Value (IDR) | `SUM(order_value)` | order value, revenue, sales |
| Average Fulfillment Time (hours) | `AVG(fulfillment_hours)` | pick and pack time, fulfillment time |
| Cancellation Rate (%) | `COUNT(CASE WHEN order_status = 'Cancelled' THEN 1 END) * 100.0 / COUNT(order_id)` | cancel rate |

## Entity 2: `delivery_shipments` (table `delivery_shipments`)

Dimensions: `ship_date` (time), `region_name`, `carrier`, `service_level`, `delivery_status`.

| Metric | Expression | Synonyms |
|---|---|---|
| Total Shipments | `COUNT(shipment_id)` | shipments, parcels |
| Late Delivery Rate (%) | `COUNT(CASE WHEN is_late THEN 1 END) * 100.0 / COUNT(shipment_id)` | late rate, delay rate, SLA breach rate |
| Average Delivery Days | `AVG(delivery_days)` | delivery time, transit time |
| Failed Delivery Rate (%) | `COUNT(CASE WHEN delivery_status = 'Failed' THEN 1 END) * 100.0 / COUNT(shipment_id)` | failed delivery, delivery failure |
| Return Rate (%) | `COUNT(CASE WHEN delivery_status = 'Returned' THEN 1 END) * 100.0 / COUNT(shipment_id)` | returns, return share |

## Entity 3: `v_fulfillment_delivery` (the joined view)

Dimensions: `order_date` (time), `region_name`, `channel`, `product_category`, `carrier`, `service_level`.

| Metric | Expression | Synonyms |
|---|---|---|
| Late Rate by Order Attributes (%) | `COUNT(CASE WHEN is_late THEN 1 END) * 100.0 / COUNT(shipment_id)` | late rate by category, late rate by channel |
| Order Value of Late Shipments (IDR) | `SUM(CASE WHEN is_late THEN order_value END)` | value at risk from delays |

Keep the metric names distinct from entity 2 (the view metric has "by Order Attributes" in its name), so a question that needs
`product_category` or `channel` can only be answered from the view.
