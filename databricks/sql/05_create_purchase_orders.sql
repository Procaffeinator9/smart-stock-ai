-- =============================================================================
-- 05_create_purchase_orders.sql
-- Purchase orders: replenishment orders placed with a supplier for one product
-- delivered to one store. actual_delivery_date is NULL until delivered.
-- Requires: 01_create_suppliers.sql and 02_create_products.sql (foreign key targets).
--
-- order_status values (enforced in 06_add_check_constraints.sql):
--   PLACED      order sent to supplier
--   IN_TRANSIT  supplier has shipped, not yet received
--   DELIVERED   received in store; actual_delivery_date is set
--   CANCELLED   will not be delivered
--
-- Rerunnable: CREATE TABLE IF NOT EXISTS is a no-op when the table exists.
-- =============================================================================

CREATE TABLE IF NOT EXISTS workspace.smartstock_retail.purchase_orders (
  purchase_order_id       STRING         NOT NULL COMMENT 'Business key, e.g. PO-0000001',
  supplier_id             STRING         NOT NULL COMMENT 'References suppliers.supplier_id',
  product_id              STRING         NOT NULL COMMENT 'References products.product_id',
  store_id                STRING         NOT NULL COMMENT 'Destination store, e.g. STR-001',
  order_date              DATE           NOT NULL COMMENT 'Day the order was placed',
  expected_delivery_date  DATE           NOT NULL COMMENT 'order_date plus the supplier lead time at ordering',
  actual_delivery_date    DATE                    COMMENT 'Day received; NULL unless order_status = DELIVERED',
  quantity_ordered        INT            NOT NULL COMMENT 'Units ordered (positive)',
  unit_cost               DECIMAL(10,2)  NOT NULL COMMENT 'Agreed cost per unit on this order',
  order_status            STRING         NOT NULL COMMENT 'PLACED, IN_TRANSIT, DELIVERED, or CANCELLED',
  CONSTRAINT purchase_orders_pk PRIMARY KEY (purchase_order_id),
  CONSTRAINT purchase_orders_supplier_fk FOREIGN KEY (supplier_id)
    REFERENCES workspace.smartstock_retail.suppliers (supplier_id),
  CONSTRAINT purchase_orders_product_fk FOREIGN KEY (product_id)
    REFERENCES workspace.smartstock_retail.products (product_id)
)
USING DELTA
CLUSTER BY (order_date, store_id)
COMMENT 'SmartStock AI: replenishment purchase orders by supplier, product, and store.';
