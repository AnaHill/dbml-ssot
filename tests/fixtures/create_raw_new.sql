CREATE TABLE bronze.RawWidgetEvents (
    event_id     INT PRIMARY KEY,
    widget_id    INT,
    event_time   TIMESTAMP,
    event_count  DECIMAL(10, 2)
);
