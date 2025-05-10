#!/bin/bash
set -e

# Wait for the database to be ready
echo "Waiting for database to be ready..."
until PGPASSWORD=Password1337? psql -h db -U postgres -d postgres -c '\q'; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

echo "Database is ready."

# Run migrations
echo "Running database migrations..."
cd /app
export PYTHONPATH=/app/src
alembic upgrade head

echo "Database initialization complete."