-- Excerpt in the shape pg_dump -s produces: settings, tables, indexes and
-- foreign keys as separate ALTER TABLE statements.
SET statement_timeout = 0;

CREATE TABLE staging.customer (
    customer_id integer NOT NULL,
    customer_name character varying(200),
    country_code character varying(2),
    PRIMARY KEY (customer_id)
);

CREATE TABLE staging.orders (
    order_id integer NOT NULL,
    customer_id integer,
    order_date date,
    PRIMARY KEY (order_id)
);

CREATE INDEX idx_orders_customer ON staging.orders (customer_id);

ALTER TABLE staging.orders
    ADD CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES staging.customer(customer_id);
