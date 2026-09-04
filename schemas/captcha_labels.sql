-- Captcha ground-truth labels table.
--
-- Lives in the external Postgres instance pointed to by the app's db_*
-- settings (see app/core/config/config.py). Run this once against that
-- database — this codebase has no migrations framework yet, so it isn't
-- applied automatically.
--
-- Lifecycle: gst_login captures a captcha, uploads it to MinIO, and inserts
-- an unlabeled row here (label NULL, is_solved false). A human fills in
-- `label` and flips `is_solved` to true by hand once they've read the
-- captcha image. The training task only reads rows where is_solved is true.
--
-- After each successful training run, validator-worker re-predicts every
-- solved captcha against the freshly trained model and writes
-- predicted_label + accuracy back here (see
-- app/tasks/validator_tasks.py) — accuracy is the fraction of characters
-- that matched label (0.0-1.0), letting you see per-captcha and aggregate
-- model quality directly in this table.
--
-- created_at/updated_at have no DB-side default — the application sets both
-- explicitly (see app/core/jobs/captcha_labels.py), not Postgres.

CREATE TABLE IF NOT EXISTS captcha_labels (
    object_name TEXT PRIMARY KEY,
    label TEXT,
    is_solved BOOLEAN NOT NULL DEFAULT false,
    predicted_label TEXT,
    accuracy DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ
);

-- Migration for an existing table created before this column existed:
ALTER TABLE captcha_labels ADD COLUMN IF NOT EXISTS predicted_label TEXT;
ALTER TABLE captcha_labels ADD COLUMN IF NOT EXISTS accuracy DOUBLE PRECISION;
