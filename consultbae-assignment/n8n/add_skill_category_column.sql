-- Run once against scripts/consultbae.db before building the n8n flow:
--   sqlite3 scripts/consultbae.db < n8n/add_skill_category_column.sql
ALTER TABLE person ADD COLUMN skill_category TEXT;
