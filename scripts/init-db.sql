-- Initialize the database with pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant necessary permissions to pdf_user
GRANT ALL PRIVILEGES ON DATABASE pdf_miner TO pdf_user;
GRANT ALL PRIVILEGES ON SCHEMA public TO pdf_user;

-- Ensure the password is set correctly
ALTER USER pdf_user PASSWORD 'pdf_password';

-- Note: Tables and indexes will be created by Alembic migrations
-- This script only sets up the database extension and basic configuration

-- Configure pgvector settings for better performance
-- Note: shared_preload_libraries requires server restart, skip for Docker
SET max_parallel_workers_per_gather = 2;

-- Display success message
SELECT 'Database initialization completed successfully' AS status;