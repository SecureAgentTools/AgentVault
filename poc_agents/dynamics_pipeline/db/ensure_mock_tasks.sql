-- Standalone script to ensure the mock_tasks table exists
-- This can be run at any time to add the table without affecting existing data

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

-- Grant necessary permissions
GRANT SELECT, INSERT, UPDATE ON mock_tasks TO d365_user;
GRANT USAGE, SELECT ON SEQUENCE mock_tasks_task_id_seq TO d365_user;

SELECT 'Mock tasks table check complete.' as status;
