-- Migration: Add `llm_usage` JSONB column to `interactions` table
-- File: backend/migrations/0001_add_llm_usage_to_interactions.sql
--
-- Usage:
--   psql "$DATABASE_URL" -f backend/migrations/0001_add_llm_usage_to_interactions.sql
--
-- Notes:
--  - The column is nullable and has no default, so existing rows are unaffected.
--  - This script is idempotent: it uses `IF NOT EXISTS` so re-running is safe.
--  - If you want to add indexes for querying JSON fields (e.g. provider or model),
--    there are example index statements below (commented out) to apply as needed.

BEGIN;

-- Add nullable JSONB column to store LLM usage metadata (provider, model,
-- estimated_tokens, response_time_ms, raw provider meta, etc).
ALTER TABLE interactions
  ADD COLUMN IF NOT EXISTS llm_usage JSONB NULL;

-- Optional: fast full-jsonb queries (uncomment if you want a general GIN index)
-- CREATE INDEX IF NOT EXISTS idx_interactions_llm_usage_gin
--   ON interactions USING gin (llm_usage);

-- Optional: index the 'provider' field inside the JSONB for fast equality searches
-- (creates a text index on llm_usage->>'provider'):
-- CREATE INDEX IF NOT EXISTS idx_interactions_llm_usage_provider
--   ON interactions ((llm_usage ->> 'provider'));

COMMIT;

-- Rollback / manual downgrade (if you need to remove the column):
--   ALTER TABLE interactions DROP COLUMN IF EXISTS llm_usage;
