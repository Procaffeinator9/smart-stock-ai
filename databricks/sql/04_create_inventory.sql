-- =============================================================================
-- 04_create_inventory.sql
-- Inventory: end-of-day stock snapshot per store and product. Expected to hold
-- at most one row per (snapshot_date, store_id, product_id). Databricks has no
-- UNIQUE constraint, so the load pipeline must enforce this.
-- Requires: 02_create_products.sql (foreign key target).
--
-- Rerunnable: CREATE TABLE IF NOT EXISTS is a no-op when the table exists.
-- =============================================================================

CREATE TABLE IF NOT EXISTS workspace.smartstock_retail.inventory (
  inventory_id            STRING  NOT NULL COMMENT 'Business key, e.g. INV-00000001',
  snapshot_date           DATE    NOT NULL COMMENT 'Day the end-of-day snapshot was taken',
  store_id                STRING  NOT NULL COMMENT 'Store identifier, e.g. STR-001',
  product_id              STRING  NOT NULL COMMENT 'References products.product_id',
  quantity_on_hand        INT     NOT NULL COMMENT 'Physical units in store at end of day',
  quantity_reserved       INT     NOT NULL COMMENT 'Units on hand already allocated (e.g. online orders); not sellable',
  reorder_point           INT     NOT NULL COMMENT 'Position at or below which a purchase order should be raised',
  safety_stock            INT     NOT NULL COMMENT 'Buffer held against demand and lead time variability',
  CONSTRAINT inventory_pk PRIMARY KEY (inventory_id),
  CONSTRAINT inventory_product_fk FOREIGN KEY (product_id)
    REFERENCES workspace.smartstock_retail.products (product_id)
)
USING DELTA
CLUSTER BY (snapshot_date, store_id)
COMMENT 'SmartStock AI: daily end-of-day inventory snapshots by store and product.';
