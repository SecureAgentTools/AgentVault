#!/bin/sh
# Dashboard backend startup script

# Initialize sample data
echo "Running sample data initialization..."
python -m initialize_data

# Start the application
echo "Starting dashboard backend..."
exec python app_standalone.py
