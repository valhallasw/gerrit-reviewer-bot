import logging
import sys

from add_reviewer import ReviewerFactory
from gerrit_rest import GerritREST

logging.basicConfig(level=logging.DEBUG)

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <change-id>")
    exit(1)

g = GerritREST("https://gerrit.wikimedia.org/r")
changeset = g.get_changeset(sys.argv[1])
if not changeset:
    print(f"{sys.argv[1]!r} not found...")
    exit(1)

rf = ReviewerFactory()
reviewers = rf.get_reviewers_for_changeset(changeset)

print("Suggested reviewers: ", list(reviewers))
