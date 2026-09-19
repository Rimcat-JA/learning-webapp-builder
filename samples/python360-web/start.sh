#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 server.py "$@"
elif command -v node >/dev/null 2>&1; then
  exec node server.mjs "$@"
fi
echo 'Python 3.8+ or Node.js 18+ is required. See README.md.' >&2
exit 1
