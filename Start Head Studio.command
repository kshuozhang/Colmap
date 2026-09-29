#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print "Head Studio needs setup. See README.md."
  read "?Press Return to close."
  exit 1
fi
print "Open http://127.0.0.1:8765 in your browser. Keep this window open while processing."
if /usr/bin/curl -fsS http://127.0.0.1:8765/api/info >/dev/null 2>&1; then
  open http://127.0.0.1:8765
  exit 0
fi
.venv/bin/python app.py &
studio_pid=$!
trap 'kill -INT "$studio_pid" 2>/dev/null' INT TERM HUP EXIT
for attempt in {1..40}; do
  if /usr/bin/curl -fsS http://127.0.0.1:8765/api/info >/dev/null 2>&1; then
    open http://127.0.0.1:8765
    break
  fi
  sleep 0.25
done
wait "$studio_pid"
