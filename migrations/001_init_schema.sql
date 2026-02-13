-- ═══════════════════════════════════════════════════════════════════════════════
-- Room Stager Database Schema
-- Version: 1.0.0
--
-- This migration is idempotent - safe to run multiple times on fresh deployments.
-- ═══════════════════════════════════════════════════════════════════════════════

-- Extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ═══════════════════════════════════════════════════════════════════════════════
-- MAIN JOB TRACKING TABLE
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS staging_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed
    mode VARCHAR(20) NOT NULL,  -- text-prompt, multi-reference, meilisearch

    -- Request parameters
    style VARCHAR(50) NOT NULL DEFAULT 'modern',
    room_type VARCHAR(50),
    color_preferences JSONB,
    budget_range JSONB,
    furniture_types JSONB,

    -- Progress tracking
    total_images INTEGER NOT NULL DEFAULT 1,
    completed_images INTEGER NOT NULL DEFAULT 0,
    current_stage VARCHAR(50),
    progress_percent INTEGER DEFAULT 0,

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    processing_time_ms INTEGER,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    correlation_id VARCHAR(50)
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- PER-IMAGE RESULTS TABLE
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS staging_job_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES staging_jobs(id) ON DELETE CASCADE,
    original_filename VARCHAR(255) NOT NULL,
    image_index INTEGER NOT NULL,

    -- Storage URLs (MinIO/S3)
    original_image_url TEXT,
    staged_image_url TEXT,
    staged_image_with_markers_url TEXT,

    -- Analysis & results
    room_analysis JSONB,
    product_hotspots JSONB,
    furniture_added TEXT[],

    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    processing_time_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- SELECTED PRODUCTS TABLE (MeiliSearch mode)
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS staging_selected_products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES staging_jobs(id) ON DELETE CASCADE,
    product_id VARCHAR(50) NOT NULL,
    ean VARCHAR(50),
    name VARCHAR(255) NOT NULL,
    furniture_type VARCHAR(50) NOT NULL,
    price DECIMAL(10, 2),
    image_url TEXT,
    images JSONB,  -- Array of all product image URLs
    selection_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- REAL-TIME PROGRESS EVENTS TABLE
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS staging_job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES staging_jobs(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,  -- started, analyzing, generating, validating, completed, failed, progress
    event_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════════════════════
-- INDEXES FOR PERFORMANCE
-- ═══════════════════════════════════════════════════════════════════════════════

-- Drop indexes if they exist (for idempotent re-runs)
DROP INDEX IF EXISTS idx_staging_jobs_status;
DROP INDEX IF EXISTS idx_staging_jobs_created_at;
DROP INDEX IF EXISTS idx_staging_jobs_session_id;
DROP INDEX IF EXISTS idx_staging_job_images_job_id;
DROP INDEX IF EXISTS idx_staging_job_images_status;
DROP INDEX IF EXISTS idx_staging_selected_products_job_id;
DROP INDEX IF EXISTS idx_staging_job_events_job_id;
DROP INDEX IF EXISTS idx_staging_job_events_created_at;

-- Create indexes
CREATE INDEX idx_staging_jobs_status ON staging_jobs(status);
CREATE INDEX idx_staging_jobs_created_at ON staging_jobs(created_at DESC);
CREATE INDEX idx_staging_jobs_session_id ON staging_jobs(session_id);
CREATE INDEX idx_staging_job_images_job_id ON staging_job_images(job_id);
CREATE INDEX idx_staging_job_images_status ON staging_job_images(status);
CREATE INDEX idx_staging_selected_products_job_id ON staging_selected_products(job_id);
CREATE INDEX idx_staging_job_events_job_id ON staging_job_events(job_id);
CREATE INDEX idx_staging_job_events_created_at ON staging_job_events(created_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════════
-- HELPER FUNCTIONS
-- ═══════════════════════════════════════════════════════════════════════════════

-- Function to update job progress
CREATE OR REPLACE FUNCTION update_job_progress()
RETURNS TRIGGER AS $$
BEGIN
    -- Update job's completed_images count
    UPDATE staging_jobs
    SET
        completed_images = (
            SELECT COUNT(*)
            FROM staging_job_images
            WHERE job_id = NEW.job_id AND status = 'completed'
        ),
        progress_percent = (
            SELECT CASE
                WHEN total_images > 0 THEN
                    (COUNT(*) FILTER (WHERE status = 'completed') * 100 / total_images)
                ELSE 0
            END
            FROM staging_job_images
            WHERE job_id = NEW.job_id
        )
    WHERE id = NEW.job_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists and recreate
DROP TRIGGER IF EXISTS trigger_update_job_progress ON staging_job_images;

CREATE TRIGGER trigger_update_job_progress
    AFTER UPDATE OF status ON staging_job_images
    FOR EACH ROW
    WHEN (NEW.status = 'completed')
    EXECUTE FUNCTION update_job_progress();

-- ═══════════════════════════════════════════════════════════════════════════════
-- SCHEMA VERSION TRACKING
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(20) PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Record this migration (upsert for idempotency)
INSERT INTO schema_migrations (version)
VALUES ('001_init_schema')
ON CONFLICT (version) DO NOTHING;
