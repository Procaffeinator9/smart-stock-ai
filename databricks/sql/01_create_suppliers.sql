-- =============================================================================
-- 01_create_suppliers.sql
-- Suppliers: vendors that replenish stock. Referenced by products.supplier_id
-- and purchase_orders.supplier_id. Create this table first.
--
-- Rerunnable: CREATE TABLE IF NOT EXISTS is a no-op when the table exists.
-- It never drops, replaces, or alters an existing table or its data.
-- =============================================================================

CREATE TABLE IF NOT EXISTS workspace.smartstock_retail.suppliers (
  supplier_id             STRING        NOT NULL COMMENT 'Business key, e.g. SUP-0001',
  supplier_name           STRING        NOT NULL COMMENT 'Supplier display name',
  contact_email           STRING        NOT NULL COMMENT 'Ordering contact address (synthetic data uses example.com)',
  lead_time_days          INT           NOT NULL COMMENT 'Standard days from order placement to delivery',
  minimum_order_quantity  INT           NOT NULL COMMENT 'Smallest quantity accepted per purchase order line',
  reliability_score       DECIMAL(4,3)  NOT NULL COMMENT 'Share of orders delivered on time, 0.000 to 1.000',
  CONSTRAINT suppliers_pk PRIMARY KEY (supplier_id)
)
USING DELTA
COMMENT 'SmartStock AI: suppliers that replenish products. One row per supplier.';
