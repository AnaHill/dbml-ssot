CREATE TABLE gold.widget_monthly AS
SELECT
    dw.widget_id   AS widget_id,
    dw.widget_name AS widget_name,
    COUNT(*)       AS event_count
FROM silver.fact_widget_event AS fwe
INNER JOIN silver.dim_widget AS dw
    ON fwe.widget_id = dw.widget_id
GROUP BY dw.widget_id, dw.widget_name;
