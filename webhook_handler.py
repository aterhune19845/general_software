#!/usr/bin/env python3
"""Simple Flask webhook handler.

Run:
    python3 -m pip install -r requirements.txt
    WEBHOOK_SECRET=dev-secret python3 webhook_handler.py

Try:
    curl -i -X POST http://localhost:8080/webhook \
      -H 'Content-Type: application/json' \
      -H 'X-Webhook-Secret: dev-secret' \
      -d '{"event_id":"evt_1","event_type":"user.created","timestamp":"2026-06-12T15:00:00Z","data":{"user_id":"u_123"}}'
"""

import os
import json
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request


app = Flask(__name__)

ALLOWED_EVENT_TYPES = {"user.created", "user.updated", "invoice.paid"}
PROCESSED_EVENT_IDS = set()
MAX_RETRIES = 3
EVENT_LOG_FILE = "webhook_events.jsonl"


def error(message, status):
    return jsonify({"ok": False, "error": message}), status


def validate_event(payload):
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object", 400

    required = ("event_id", "event_type", "timestamp", "data")
    missing = [field for field in required if field not in payload]
    if missing:
        return None, f"Missing required field(s): {', '.join(missing)}", 400

    event_id = payload["event_id"]
    event_type = payload["event_type"]
    timestamp = payload["timestamp"]
    data = payload["data"]

    if not isinstance(event_id, str) or not event_id.strip():
        return None, "event_id must be a non-empty string", 400
    if event_type not in ALLOWED_EVENT_TYPES:
        return None, "event_type is not supported", 422
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None, "timestamp must be an ISO-8601 string", 400
    if not isinstance(data, dict):
        return None, "data must be a JSON object", 400

    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None, "timestamp must be an ISO-8601 string", 400

    return {
        "event_id": event_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "data": data,
    }, None, None


def process_event(event):
    if event["data"].get("force_error"):
        raise RuntimeError("Temporary processing failure")

    log_entry = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "timestamp": event["timestamp"],
        "data": event["data"],
    }

    with open(EVENT_LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(log_entry) + "\n")

    app.logger.info("processed %s (%s)", event["event_type"], event["event_id"])


def process_with_retries(event):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            process_event(event)
            return True
        except Exception as exc:
            app.logger.warning("attempt %s failed: %s", attempt, exc)
            if attempt == MAX_RETRIES:
                return False
            time.sleep(0.25 * attempt)


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.post("/webhook")
def webhook():
    expected_secret = os.environ.get("WEBHOOK_SECRET", "dev-secret")
    if request.headers.get("X-Webhook-Secret") != expected_secret:
        return error("Missing or invalid webhook secret", 401)

    if not request.is_json:
        return error("Content-Type must be application/json", 400)

    event, message, status = validate_event(request.get_json(silent=True))
    if message:
        return error(message, status)

    if event["event_id"] in PROCESSED_EVENT_IDS:
        return jsonify({"ok": True, "status": "duplicate_ignored"})

    if not process_with_retries(event):
        return error("Processing failed; try again later", 503)

    PROCESSED_EVENT_IDS.add(event["event_id"])
    return jsonify({"ok": True, "status": "processed"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
