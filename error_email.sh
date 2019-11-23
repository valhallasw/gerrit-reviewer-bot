#!/bin/sh
cd /data/project/gerrit-reviewer-bot
(tail gerrit_reviewer_bot.err -n 100 | grep -v "Running as task") && (tail gerrit_reviewer_bot.err -n 100 | mail -s "Gerrit Reviewer Bot broken" valhallasw@arctus.nl)
