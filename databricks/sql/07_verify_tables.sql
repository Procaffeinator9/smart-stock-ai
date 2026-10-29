-- =============================================================================
-- 07_verify_tables.sql
-- Read-only. Confirms the tables, keys, and CHECK constraints were created.
-- =============================================================================

-- Expect: inventory, products, purchase_orders, sales, suppliers.
SHOW TABLES IN workspace.smartstock_retail;

-- Primary and foreign keys (informational in Unity Catalog).
SELECT table_name, constraint_name, constraint_type
FROM workspace.information_schema.table_constraints
WHERE table_schema = 'smartstock_retail'
ORDER BY table_name, constraint_type, constraint_name;

-- Columns, types, and nullability for every project table.
SELECT table_name, ordinal_position, column_name, full_data_type, is_nullable
FROM workspace.information_schema.columns
WHERE table_schema = 'smartstock_retail'
ORDER BY table_name, ordinal_position;

-- CHECK constraints are stored as delta.constraints.* table properties.
SHOW TBLPROPERTIES workspace.smartstock_retail.suppliers;
SHOW TBLPROPERTIES workspace.smartstock_retail.products;
SHOW TBLPROPERTIES workspace.smartstock_retail.sales;
SHOW TBLPROPERTIES workspace.smartstock_retail.inventory;
SHOW TBLPROPERTIES workspace.smartstock_retail.purchase_orders;
