#!/bin/bash
echo
echo `date`: Running as task $JOB_ID @ $HOSTNAME
echo `date`: Running as task $JOB_ID @ $HOSTNAME >& 2
cd "$( dirname "${BASH_SOURCE[0]}" )"

export PYTHONIOENCODING=utf-8
$HOME/venv-py35-stretch/bin/python pop3bot.py

echo Done.
