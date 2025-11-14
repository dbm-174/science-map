#!/bin/bash
uvicorn app.backend.api.main:app --reload --host 127.0.0.1 --port 8000
# Browser öffnen: http://127.0.0.1:8000/app/
