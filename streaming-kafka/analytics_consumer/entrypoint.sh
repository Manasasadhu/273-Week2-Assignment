#!/bin/sh
set -euo pipefail

if [ "${TOPIC_WAIT_SKIP:-}" = "1" ]; then
  echo "Skipping Kafka topic wait per TOPIC_WAIT_SKIP=1"
else
  python -u wait_for_topics.py
fi

exec python -u main.py
