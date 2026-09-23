#!/bin/sh
# The browser check (check_page.py) in Microsoft's Playwright image: Chromium and its libraries included.
# The repo is mounted read-only and installed into the container; screenshots land in ./browser-check/.
set -eu
cd "$(dirname "$0")/../.."
VERSION=1.63.0
mkdir -p browser-check
exec docker run --rm -v "$PWD":/src:ro -v "$PWD/browser-check":/out "mcr.microsoft.com/playwright/python:v$VERSION-noble" sh -c "
  cp -r /src /tmp/palace && cd /tmp/palace &&
  pip install -q --break-system-packages --root-user-action=ignore playwright==$VERSION . 2>&1 | grep -v -i notice || true
  python tests/browser/check_page.py"
