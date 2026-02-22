BEGIN;

-- 1) Clean up tables from the previous (failed) attempt
DROP TABLE IF EXISTS interaction_categories CASCADE;
DROP TABLE IF EXISTS interaction_mistakes CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS mistaketypes CASCADE;

-- 2) Add JSONB list columns to interactions table
ALTER TABLE interactions
  ADD COLUMN IF NOT EXISTS categories JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE interactions
  ADD COLUMN IF NOT EXISTS mistake_types JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
