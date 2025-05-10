#!/bin/sh
echo "===== STARTING FIXED BACKEND WITH ENHANCED STARTUP ====="
echo "REDIS_URL: \"
echo "Attempting to ping Redis..."

# Wait for Redis to be fully available
RETRIES=30
while [ \ -gt 0 ]
do
    if redis-cli -u \ ping > /dev/null 2>&1; then
        echo "âœ… Redis connection successful!"
        break
    fi
    echo "Waiting for Redis connection... (\ attempts left)"
    RETRIES=\
    sleep 1
done

if [ \ -eq 0 ]; then
    echo "âš ï¸ Could not connect to primary Redis URL, trying fallback..."
    if [ ! -z "\" ]; then
        export REDIS_URL=\
        echo "Changed REDIS_URL to \"
    fi
fi

# Start the application with enhanced logging
echo "Starting FastAPI backend..."
python app_standalone.py