-- =============================================================================
-- 00_preflight_check.sql
-- Read-only. Confirms the target schema exists before running the DDL scripts.
-- Expected: exactly one row, databaseName = 'smartstock_retail'.
-- This project never creates catalogs or schemas; workspace.smartstock_retail
-- must already exist (created manually by the workspace owner).
-- =============================================================================

SHOW SCHEMAS IN workspace LIKE 'smartstock_retail';

-- Lists any tables that already exist, so you know which CREATE TABLE IF NOT EXISTS
-- statements will be no-ops.
SHOW TABLES IN workspace.smartstock_retail;
