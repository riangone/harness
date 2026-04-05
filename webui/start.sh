#!/bin/bash
cd /home/ubuntu/ws/harness/webui
source venv/bin/activate 2>/dev/null || true
uvicorn app.main:app --host 0.0.0.0 --port 10000 --reload
