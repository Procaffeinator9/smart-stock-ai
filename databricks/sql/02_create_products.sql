-- =============================================================================
-- 02_create_products.sql
-- Products: the catalogue of items sold. Each product has one primary supplier.
-- Referenced by sales, inventory, and purchase_orders via product_id.
-- Requires: 01_create_suppliers.sql (foreign key target).
--
-- Rerunnable: CREATE TABLE IF NOT EXISTS is a no-op when the table exists.
-- =============================================================================

CREATE TABLE IF NOT EXISTS workspace.smartstock_retail.products (
  product_id              STRING         NOT NULL COMMENT 'Business key, e.g. PRD-00001',
  sku                     STRING         NOT NULL COMMENT 'Stock keeping unit code, e.g. SKU-DRY-00002',
  product_name            STRING         NOT NULL COMMENT 'Customer-facing product name',
  category                STRING         NOT NULL COMMENT 'Merchandise category, e.g. Dairy, Produce',
  unit_cost               DECIMAL(10,2)  NOT NULL COMMENT 'Standard purchase cost per unit',
  selling_price           DECIMAL(10,2)  NOT NULL COMMENT 'Regular (non-promotional) shelf price per unit',
  supplier_id             STRING         NOT NULL COMMENT 'Primary supplier; references suppliers.supplier_id',
  shelf_life_days         INT                     COMMENT 'Days until expiry; NULL for non-perishable items',
  created_at              TIMESTAMP      NOT NULL COMMENT 'When the product was added to the catalogue',
  CONSTRAINT products_pk PRIMARY KEY (product_id),
  CONSTRAINT products_supplier_fk FOREIGN KEY (supplier_id)
    REFERENCES workspace.smartstock_retail.suppliers (supplier_id)
)
USING DELTA
COMMENT 'SmartStock AI: product catalogue. One row per product.';
