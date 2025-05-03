-- Initialization script for the d365_poc_db database
-- REQ-DYN-DB-004, REQ-DYN-DB-005, REQ-DYN-DB-007

-- Create tables first, starting with those that don't have foreign key dependencies

-- Mock Accounts Table
CREATE TABLE IF NOT EXISTS mock_accounts (
    account_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    website VARCHAR(255) UNIQUE, -- Added UNIQUE constraint for lookup
    status VARCHAR(50)
);
\echo 'Table mock_accounts created (if not exists).'

-- Mock Contacts Table
CREATE TABLE IF NOT EXISTS mock_contacts (
    contact_id SERIAL PRIMARY KEY,
    account_id VARCHAR(64) REFERENCES mock_accounts(account_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(100)
);
\echo 'Table mock_contacts created (if not exists).'

-- Mock Opportunities Table
CREATE TABLE IF NOT EXISTS mock_opportunities (
    opportunity_id SERIAL PRIMARY KEY,
    account_id VARCHAR(64) REFERENCES mock_accounts(account_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    stage VARCHAR(50),
    revenue NUMERIC(15, 2) -- Use NUMERIC for currency
);
\echo 'Table mock_opportunities created (if not exists).'

-- Mock Cases Table
CREATE TABLE IF NOT EXISTS mock_cases (
    case_id SERIAL PRIMARY KEY,
    account_id VARCHAR(64) REFERENCES mock_accounts(account_id) ON DELETE CASCADE,
    subject TEXT,
    priority VARCHAR(50),
    status VARCHAR(50)
);
\echo 'Table mock_cases created (if not exists).'

-- Mock External Signals Table
CREATE TABLE IF NOT EXISTS mock_external_signals (
    signal_id SERIAL PRIMARY KEY,
    website VARCHAR(255) UNIQUE NOT NULL, -- Lookup key
    news TEXT[], -- Array of text
    intent_signals TEXT[], -- Array of text
    technologies TEXT[] -- Array of text
);
\echo 'Table mock_external_signals created (if not exists).'

-- Mock Tasks Table (REQ-DYN-DB-006)
CREATE TABLE IF NOT EXISTS mock_tasks (
    task_id SERIAL PRIMARY KEY,
    account_id VARCHAR(64) REFERENCES mock_accounts(account_id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    priority VARCHAR(50), -- e.g., High, Medium, Low
    status VARCHAR(50) DEFAULT 'Open', -- e.g., Open, In Progress, Completed
    related_record_id VARCHAR(100) NULL, -- e.g., OPP-123, CASE-456
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
\echo 'Table mock_tasks created (if not exists).'

-- Grant permissions first, before truncating
GRANT SELECT ON ALL TABLES IN SCHEMA public TO d365_user;
GRANT INSERT, UPDATE ON mock_tasks TO d365_user;
GRANT USAGE, SELECT ON SEQUENCE mock_tasks_task_id_seq TO d365_user;
\echo 'Granted permissions to d365_user.'

-- Populate Mock Data (Clear existing data first to ensure idempotency if script runs again)
-- Include mock_tasks in tables to be truncated
BEGIN;
  -- Check if the tables exist before trying to truncate them
  DO $$
  BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'mock_contacts')
       AND EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'mock_opportunities')
       AND EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'mock_cases')
       AND EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'mock_external_signals')
       AND EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'mock_tasks')
       AND EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'mock_accounts')
    THEN
      -- All tables exist, so we can truncate them
      EXECUTE 'TRUNCATE mock_contacts, mock_opportunities, mock_cases, mock_external_signals, mock_tasks, mock_accounts RESTART IDENTITY CASCADE';
      RAISE NOTICE 'All tables truncated.';
    ELSE
      RAISE NOTICE 'Not all tables exist yet, skipping truncate.';
    END IF;
  END
  $$;
COMMIT;
\echo 'Database prepared for data population.'

-- Insert Accounts
INSERT INTO mock_accounts (account_id, name, industry, website, status) VALUES
('ACC-GUID-001', 'Acme Corp', 'Manufacturing', 'acme.com', 'Active Customer'),
('ACC-GUID-002', 'Beta Solutions', 'Technology', 'beta.io', 'Prospect'),
('ACC-GUID-003', 'Delta Logistics', 'Transportation', 'delta-log.com', 'Active Customer'),
('ACC-GUID-004', 'Gamma Medical', 'Healthcare', 'gammamed.org', 'Past Customer'),
('ACC-GUID-005', 'Epsilon Retail', 'Retail', 'epsilon.shop', 'Prospect'),
('ACC-GUID-SVA', 'Quantum Dynamics', 'Technology', 'quantum-dynamics.tech', 'Strategic Account');
\echo 'Inserted data into mock_accounts.'

-- Insert Contacts
INSERT INTO mock_contacts (account_id, name, role) VALUES
('ACC-GUID-001', 'Jane Doe', 'VP Engineering'),
('ACC-GUID-001', 'Robert Smith', 'Procurement Manager'),
('ACC-GUID-002', 'John Smith', 'CTO'),
('ACC-GUID-003', 'Maria Garcia', 'Operations Director'),
('ACC-GUID-004', 'David Lee', 'IT Manager (Former)'),
('ACC-GUID-005', 'Chen Wang', 'E-commerce Lead'),
('ACC-GUID-SVA', 'Sarah Chen', 'CTO'),
('ACC-GUID-SVA', 'Michael Rodriguez', 'VP of Engineering'),
('ACC-GUID-SVA', 'Emma Watson', 'Procurement Director');
\echo 'Inserted data into mock_contacts.'

-- Insert Opportunities
INSERT INTO mock_opportunities (account_id, name, stage, revenue) VALUES
('ACC-GUID-001', 'Widget Pro Upgrade Q3', 'Proposal', 50000.00),
('ACC-GUID-001', 'Support Contract Renewal', 'Won', 15000.00),
('ACC-GUID-002', 'Initial Platform Deal', 'Qualification', 75000.00),
('ACC-GUID-003', 'Fleet Management Integration', 'Negotiation', 120000.00),
('ACC-GUID-005', 'POS System PoC', 'Discovery', 25000.00),
('ACC-GUID-SVA', 'Enterprise AI Platform Implementation', 'Negotiation', 850000.00),
('ACC-GUID-SVA', 'Cloud Infrastructure Migration', 'Proposal', 325000.00);
\echo 'Inserted data into mock_opportunities.'

-- Insert Cases
INSERT INTO mock_cases (account_id, subject, priority, status) VALUES
('ACC-GUID-001', 'Widget Pro connectivity issue', 'High', 'In Progress'),
('ACC-GUID-003', 'API rate limit question', 'Medium', 'Resolved'),
('ACC-GUID-003', 'Invoice clarification needed INV-12345', 'Low', 'Waiting for Customer'),
('ACC-GUID-SVA', 'Critical security vulnerability in current deployment', 'High', 'In Progress'),
('ACC-GUID-SVA', 'API integration failing after latest update', 'High', 'Open');
\echo 'Inserted data into mock_cases.'

-- Insert External Signals
INSERT INTO mock_external_signals (website, news, intent_signals, technologies) VALUES
('acme.com', ARRAY['Acme Corp announces record profits for Q2.', 'Acme Corp facing supply chain delays for Widget Pro.'], ARRAY['Increased research activity around ''cloud migration''.', 'Downloaded whitepaper on ''AI in Manufacturing''.'], ARRAY['Salesforce', 'AWS', 'SAP']),
('beta.io', ARRAY['Beta Solutions secures new round of funding.', 'Beta Solutions hiring data scientists.'], ARRAY['Multiple visits to pricing page.', 'Attended webinar on ''API Security Best Practices''.'], ARRAY['Azure', 'HubSpot', 'Snowflake']),
('delta-log.com', ARRAY['Delta Logistics partners with major shipping firm.'], ARRAY['Researching route optimization software.'], ARRAY['Oracle Netsuite', 'AWS']),
('gammamed.org', ARRAY['Gamma Medical publishes research on new diagnostic tool.'], ARRAY['Searching for HIPAA compliant cloud storage.'], ARRAY['Epic', 'Azure', 'Salesforce Health Cloud']),
('epsilon.shop', ARRAY['Epsilon Retail launches new loyalty program.'], ARRAY['Evaluating e-commerce platform migrations.', 'Looking for marketing automation tools.'], ARRAY['Shopify', 'Klaviyo', 'GCP']),
('quantum-dynamics.tech', ARRAY['Quantum Dynamics secures $75M in Series C funding for expansion', 'CRITICAL ALERT: Quantum Dynamics experiencing major security breach affecting critical systems', 'Competitor actively poaching Quantum Dynamics enterprise clients'], ARRAY['Emergency research into security vulnerability patches', 'CEO reviewing security documentation repeatedly', 'URGENT proposal request submitted with 24-hour deadline'], ARRAY['Kubernetes', 'AWS', 'TensorFlow', 'React', 'PostgreSQL']);
\echo 'Inserted data into mock_external_signals.'

\echo 'Database initialization script finished.'
