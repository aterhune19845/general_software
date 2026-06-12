Simple Flask webhook handler.

Run:
    python3 -m pip install -r requirements.txt
    WEBHOOK_SECRET=dev-secret python3 webhook_handler.py

Try:
    curl -i -X POST http://localhost:8080/webhook \
      -H 'Content-Type: application/json' \
      -H 'X-Webhook-Secret: dev-secret' \
      -d '{"event_id":"evt_1","event_type":"user.created","timestamp":"2026-06-12T15:00:00Z","data":{"user_id":"u_123"}}'
