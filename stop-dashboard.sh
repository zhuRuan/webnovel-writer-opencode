#!/bin/bash
lsof -i :8765 -t 2>/dev/null | xargs kill 2>/dev/null && echo "Dashboard stopped" || echo "No dashboard running"
