#!/bin/bash
set -euo pipefail

echo
echo `date`: Running as task $HOSTNAME
echo `date`: Running as task $HOSTNAME >& 2
cd "$( dirname "${BASH_SOURCE[0]}" )"

export PYTHONIOENCODING=utf-8
timeout 1h $HOME/venv-tf-python39/bin/python pop3bot.py

echo Done.
