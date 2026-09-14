#!/bin/bash
cd "$(dirname "$0")"
echo "Starting preview server..."
ruby -run -e httpd . -p 8000 &
SERVER_PID=$!
sleep 1
open "http://localhost:8000/mishko-epk.html"
echo ""
echo "Preview running at http://localhost:8000/mishko-epk.html"
echo "Leave this window open while you look at the site."
echo "Close this window (or press Ctrl+C) when you're done to stop the preview."
wait $SERVER_PID
