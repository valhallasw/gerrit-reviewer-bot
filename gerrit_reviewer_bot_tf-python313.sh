#!/bin/bash
set -euo pipefail

echo
echo "$(date): Running as task $HOSTNAME"
cd "$( dirname "${BASH_SOURCE[0]}" )"

KNOWN_HOSTS_URL="https://config-master.wikimedia.org/known_hosts"
# Refresh known_hosts, but tolerate a failed fetch: fall back to the existing
# file so a transient outage does not break the run. Log a clear, timestamped
# message (including the URL) on failure instead of curl's terse output.
if ! curl -sSf "$KNOWN_HOSTS_URL" -o known_hosts.new; then
    echo "$(date -u '+%Y-%m-%d %H:%M:%SZ') WARNING: failed to refresh known_hosts from $KNOWN_HOSTS_URL; using existing file" >&2
    rm -f known_hosts.new
else
    mv known_hosts.new known_hosts
fi

export PYTHONIOENCODING=utf-8
timeout 1h "$HOME/venv-tf-python313/bin/python" pop3bot.py

echo Done.
