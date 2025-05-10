#!/bin/bash

# Check if an alert number is provided
if [ -z "$1" ]; then
  echo "Usage: ./run_pipeline.sh <alert_number>"
  echo "Example: ./run_pipeline.sh 1"
  exit 1
fi

ALERT_NUMBER=$1
ALERT_FILE="/app/input_alerts/sample_alert${ALERT_NUMBER}.json"

echo "Starting pipeline with alert: ${ALERT_FILE}"
docker-compose -f docker-compose.secops.yml run --rm secops-orchestrator --alert-file ${ALERT_FILE}
