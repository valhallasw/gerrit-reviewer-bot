import logging
logging.basicConfig(level=logging.DEBUG)
import pop3bot
import sys

if len(sys.argv) < 2:
    print "Usage: %s <change-id>" % (sys.argv[0])
    exit(1)

changeset = pop3bot.get_changeset(sys.argv[1])
if not changeset:
    print "%r not found..." % (sys.argv[1])

reviewers = pop3bot.get_reviewers_for_changeset(changeset)

print "Suggested reviewers: ", list(reviewers)
