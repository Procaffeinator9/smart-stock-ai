-- =============================================================================
-- 06_add_check_constraints.sql
-- Enforced data-quality rules (Delta CHECK constraints). Run after 01-05.
--
-- Delta rejects any write that violates these rules. Adding a constraint also
-- validates existing rows, so it fails if current data already violates it.
--
-- Rerunnable: Databricks has no ADD CONSTRAINT IF NOT EXISTS, so each rule is
-- dropped (IF EXISTS) and re-added. This only touches the constraint, never the
-- table or its data.
--
-- Every expression is written so it never evaluates to NULL; nullable columns
-- are handled explicitly with IS NULL.
-- =============================================================================

-- suppliers -------------------------------------------------------------------
ALTER TABLE workspace.smartstock_retail.suppliers DROP CONSTRAINT IF EXISTS suppliers_lead_time_positive;
ALTER TABLE workspace.smartstock_retail.suppliers ADD CONSTRAINT suppliers_lead_time_positive
  CHECK (lead_time_days > 0);

ALTER TABLE workspace.smartstock_retail.suppliers DROP CONSTRAINT IF EXISTS suppliers_moq_positive;
ALTER TABLE workspace.smartstock_retail.suppliers ADD CONSTRAINT suppliers_moq_positive
  CHECK (minimum_order_quantity > 0);

ALTER TABLE workspace.smartstock_retail.suppliers DROP CONSTRAINT IF EXISTS suppliers_reliability_range;
ALTER TABLE workspace.smartstock_retail.suppliers ADD CONSTRAINT suppliers_reliability_range
  CHECK (reliability_score BETWEEN 0 AND 1);

ALTER TABLE workspace.smartstock_retail.suppliers DROP CONSTRAINT IF EXISTS suppliers_email_format;
ALTER TABLE workspace.smartstock_retail.suppliers ADD CONSTRAINT suppliers_email_format
  CHECK (contact_email LIKE '%_@_%._%');

-- products --------------------------------------------------------------------
ALTER TABLE workspace.smartstock_retail.products DROP CONSTRAINT IF EXISTS products_unit_cost_non_negative;
ALTER TABLE workspace.smartstock_retail.products ADD CONSTRAINT products_unit_cost_non_negative
  CHECK (unit_cost >= 0);

ALTER TABLE workspace.smartstock_retail.products DROP CONSTRAINT IF EXISTS products_selling_price_positive;
ALTER TABLE workspace.smartstock_retail.products ADD CONSTRAINT products_selling_price_positive
  CHECK (selling_price > 0);

ALTER TABLE workspace.smartstock_retail.products DROP CONSTRAINT IF EXISTS products_shelf_life_positive;
ALTER TABLE workspace.smartstock_retail.products ADD CONSTRAINT products_shelf_life_positive
  CHECK (shelf_life_days IS NULL OR shelf_life_days > 0);

-- sales -----------------------------------------------------------------------
ALTER TABLE workspace.smartstock_retail.sales DROP CONSTRAINT IF EXISTS sales_quantity_positive;
ALTER TABLE workspace.smartstock_retail.sales ADD CONSTRAINT sales_quantity_positive
  CHECK (quantity_sold > 0);

ALTER TABLE workspace.smartstock_retail.sales DROP CONSTRAINT IF EXISTS sales_price_non_negative;
ALTER TABLE workspace.smartstock_retail.sales ADD CONSTRAINT sales_price_non_negative
  CHECK (unit_selling_price >= 0);

-- inventory -------------------------------------------------------------------
ALTER TABLE workspace.smartstock_retail.inventory DROP CONSTRAINT IF EXISTS inventory_on_hand_non_negative;
ALTER TABLE workspace.smartstock_retail.inventory ADD CONSTRAINT inventory_on_hand_non_negative
  CHECK (quantity_on_hand >= 0);

ALTER TABLE workspace.smartstock_retail.inventory DROP CONSTRAINT IF EXISTS inventory_reserved_within_on_hand;
ALTER TABLE workspace.smartstock_retail.inventory ADD CONSTRAINT inventory_reserved_within_on_hand
  CHECK (quantity_reserved >= 0 AND quantity_reserved <= quantity_on_hand);

ALTER TABLE workspace.smartstock_retail.inventory DROP CONSTRAINT IF EXISTS inventory_reorder_point_non_negative;
ALTER TABLE workspace.smartstock_retail.inventory ADD CONSTRAINT inventory_reorder_point_non_negative
  CHECK (reorder_point >= 0);

ALTER TABLE workspace.smartstock_retail.inventory DROP CONSTRAINT IF EXISTS inventory_safety_stock_non_negative;
ALTER TABLE workspace.smartstock_retail.inventory ADD CONSTRAINT inventory_safety_stock_non_negative
  CHECK (safety_stock >= 0);

-- purchase_orders -------------------------------------------------------------
ALTER TABLE workspace.smartstock_retail.purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_quantity_positive;
ALTER TABLE workspace.smartstock_retail.purchase_orders ADD CONSTRAINT purchase_orders_quantity_positive
  CHECK (quantity_ordered > 0);

ALTER TABLE workspace.smartstock_retail.purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_unit_cost_non_negative;
ALTER TABLE workspace.smartstock_retail.purchase_orders ADD CONSTRAINT purchase_orders_unit_cost_non_negative
  CHECK (unit_cost >= 0);

ALTER TABLE workspace.smartstock_retail.purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_status_valid;
ALTER TABLE workspace.smartstock_retail.purchase_orders ADD CONSTRAINT purchase_orders_status_valid
  CHECK (order_status IN ('PLACED', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED'));

ALTER TABLE workspace.smartstock_retail.purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_expected_after_order;
ALTER TABLE workspace.smartstock_retail.purchase_orders ADD CONSTRAINT purchase_orders_expected_after_order
  CHECK (expected_delivery_date >= order_date);

ALTER TABLE workspace.smartstock_retail.purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_actual_after_order;
ALTER TABLE workspace.smartstock_retail.purchase_orders ADD CONSTRAINT purchase_orders_actual_after_order
  CHECK (actual_delivery_date IS NULL OR actual_delivery_date >= order_date);

-- A delivery date is present exactly when the order is DELIVERED.
ALTER TABLE workspace.smartstock_retail.purchase_orders DROP CONSTRAINT IF EXISTS purchase_orders_delivery_matches_status;
ALTER TABLE workspace.smartstock_retail.purchase_orders ADD CONSTRAINT purchase_orders_delivery_matches_status
  CHECK ((order_status = 'DELIVERED' AND actual_delivery_date IS NOT NULL)
      OR (order_status <> 'DELIVERED' AND actual_delivery_date IS NULL));
