-- Initialization script for the etl_poc_db database
-- REQ-ETL-DB-004, REQ-ETL-DB-005

-- Create the table to store pipeline artifacts as JSONB
CREATE TABLE IF NOT EXISTS pipeline_artifacts (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,          -- To group artifacts by pipeline run
    step_name VARCHAR(100) NOT NULL,      -- The orchestrator node/agent step that created it
    artifact_type VARCHAR(100) NOT NULL,  -- e.g., 'raw_data', 'transformed_data', 'validation_report'
    artifact_data JSONB NOT NULL,         -- The actual artifact content stored as JSON
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP -- Timestamp of creation
);

-- Optional: Add an index for faster lookup by run_id and type
CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_run_id_type ON pipeline_artifacts (run_id, artifact_type);

-- Grant privileges to the application user (replace 'etl_user' if using a different one)
-- The default POSTGRES_USER in docker-compose will own the DB,
-- so explicit grants might only be needed if using separate users later.
-- GRANT ALL PRIVILEGES ON TABLE pipeline_artifacts TO etl_user;
-- GRANT USAGE, SELECT ON SEQUENCE pipeline_artifacts_id_seq TO etl_user;

-- Log completion
\echo 'Database initialization script completed.'
\echo 'Table pipeline_artifacts created (if not exists).'
