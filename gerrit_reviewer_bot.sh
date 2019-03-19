#!/bin/bash
echo
echo `date`: Running as task $JOB_ID @ $HOSTNAME
echo `date`: Running as task $JOB_ID @ $HOSTNAME >& 2
cd $HOME/src/gerrit-reviewer-bot
export PYTHONIOENCODING=utf-8
$HOME/venv/bin/python pop3bot.py
echo Done.
