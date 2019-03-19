import sys
import logging
from gerrit_rest import GerritREST
from add_reviewer import ReviewerFactory

logging.basicConfig(level=logging.DEBUG)

if len(sys.argv) < 2:
    print("Usage: %s <change-id>" % (sys.argv[0]))
    exit(1)

g = GerritREST('https://gerrit.wikimedia.org/r')
changeset = g.get_changeset(sys.argv[1])
if not changeset:
    print("%r not found..." % (sys.argv[1]))

rf = ReviewerFactory()
reviewers = rf.get_reviewers_for_changeset(changeset)

print("Suggested reviewers: ", list(reviewers))
