-- =============================================================================
-- 03_create_sales.sql
-- Sales: units sold per store, product, and day (the demand signal for
-- forecasting). Returns are not modelled yet, so quantity_sold is always positive.
-- store_id is an identifier only; there is no stores table yet.
-- Requires: 02_create_products.sql (foreign key target).
--
-- Rerunnable: CREATE TABLE IF NOT EXISTS is a no-op when the table exists.
-- =============================================================================

CREATE TABLE IF NOT EXISTS workspace.smartstock_retail.sales (
  sale_id                 STRING         NOT NULL COMMENT 'Business key, e.g. SAL-00000001',
  sale_date               DATE           NOT NULL COMMENT 'Trading day of the sale',
  store_id                STRING         NOT NULL COMMENT 'Store identifier, e.g. STR-001',
  product_id              STRING         NOT NULL COMMENT 'References products.product_id',
  quantity_sold           INT            NOT NULL COMMENT 'Units sold (positive)',
  unit_selling_price      DECIMAL(10,2)  NOT NULL COMMENT 'Actual price paid per unit, after any promotion',
  promotion_applied       BOOLEAN        NOT NULL COMMENT 'True when the sale was at a promotional price',
  CONSTRAINT sales_pk PRIMARY KEY (sale_id),
  CONSTRAINT sales_product_fk FOREIGN KEY (product_id)
    REFERENCES workspace.smartstock_retail.products (product_id)
)
USING DELTA
CLUSTER BY (sale_date, store_id)
COMMENT 'SmartStock AI: sales by store, product, and day. Main demand history for forecasting.';
