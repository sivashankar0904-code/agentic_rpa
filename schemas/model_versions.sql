-- Captcha CNN training-run history.
--
-- Lives in the same external Postgres instance as captcha_labels (see
-- schemas/captcha_labels.sql and app/core/config/config.py's db_* settings).
-- Applied by hand — this codebase has no migrations framework yet.
--
-- One row per train_captcha_model run. "The current model" = the row with
-- the latest created_at (or MAX(id)); minio_object_name points at that
-- run's timestamped weights in the rpa-captcha-models MinIO bucket (see
-- app/core/jobs/captcha_model_store.py). Kept alongside, not instead of,
-- the captcha-cnn-latest.pt MinIO alias — this table is the queryable
-- history/metadata, the alias is a zero-query convenience for inference.
--
-- created_at has no DB-side default — the application sets it explicitly
-- (see app/core/model_versions/model_versions.py), not Postgres.

CREATE TABLE IF NOT EXISTS model_versions (
    id BIGSERIAL PRIMARY KEY,
    minio_object_name TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    final_loss DOUBLE PRECISION,
    final_accuracy DOUBLE PRECISION,
    mlflow_run_id TEXT,
    created_at TIMESTAMPTZ NOT NULL
);
