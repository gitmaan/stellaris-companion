-- D1 schema for feedback deduplication
-- Run: npx wrangler d1 execute feedback --file=schema.sql

CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL,
  github_issue_number INTEGER NOT NULL,
  report_count INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fingerprint ON reports(fingerprint);
