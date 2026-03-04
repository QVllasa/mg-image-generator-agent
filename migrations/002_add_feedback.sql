-- ═══════════════════════════════════════════════════════════════════════════════
-- Feedback Table for User Ratings
-- Version: 1.1.0
--
-- Stores user feedback (positive/negative) for generated staging images.
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS job_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES staging_jobs(id) ON DELETE CASCADE,
    feedback VARCHAR(20) NOT NULL CHECK (feedback IN ('positive', 'negative')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(job_id)
);

-- Indexes
DROP INDEX IF EXISTS idx_job_feedback_job_id;
DROP INDEX IF EXISTS idx_job_feedback_created_at;

CREATE INDEX idx_job_feedback_job_id ON job_feedback(job_id);
CREATE INDEX idx_job_feedback_created_at ON job_feedback(created_at DESC);

-- Record migration
INSERT INTO schema_migrations (version)
VALUES ('002_add_feedback')
ON CONFLICT (version) DO NOTHING;
