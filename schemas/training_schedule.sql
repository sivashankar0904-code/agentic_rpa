-- Training-run lock/audit trail.
--
-- Lives in the same external Postgres instance as captcha_labels and
-- model_versions (see their schema files and app/core/config/config.py's
-- db_* settings). Applied by hand — this codebase has no migrations
-- framework yet.
--
-- train_captcha_model inserts a row here (is_completed = false) before it
-- starts training, and updates it to is_completed = true (completed_at set)
-- once training finishes — in a finally, so a crashed run still releases
-- the lock rather than blocking every future attempt forever. Before
-- starting, it checks for any existing is_completed = false row and skips
-- the run entirely if one is found, so the beat-scheduled trigger
-- (trigger_train_captcha_model, every 10 minutes) can't stack overlapping
-- training runs on top of one still in progress.
--
-- started_at/completed_at have no DB-side default — the application sets
-- them explicitly (see app/core/model_versions/training_schedule.py), not
-- Postgres.

CREATE TABLE IF NOT EXISTS training_schedule (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    is_completed BOOLEAN NOT NULL DEFAULT false
);
