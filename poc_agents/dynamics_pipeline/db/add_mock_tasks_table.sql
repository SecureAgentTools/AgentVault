-- Script to add the missing mock_tasks table to the existing database

-- Create the mock_tasks table if it doesn't exist
CREATE TABLE IF NOT EXISTS mock_tasks (
    task_id SERIAL PRIMARY KEY,
    account_id VARCHAR(64) REFERENCES mock_accounts(account_id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    priority VARCHAR(50), -- e.g., High, Medium, Low
    status VARCHAR(50) DEFAULT 'Open', -- e.g., Open, In Progress, Completed
    related_record_id VARCHAR(100) NULL, -- e.g., OPP-123, CASE-456
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Grant privileges to d365_user
GRANT SELECT, INSERT ON mock_tasks TO d365_user;

-- Grant usage on the sequence
GRANT USAGE, SELECT ON SEQUENCE mock_tasks_task_id_seq TO d365_user;

\echo 'Table mock_tasks created (if not exists) and permissions granted.'
