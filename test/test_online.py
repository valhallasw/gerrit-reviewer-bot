import add_reviewer
import logging
import pathlib
import gerrit_rest

logging.basicConfig(level=logging.DEBUG)

basepath = pathlib.Path(__file__).parent


def test_gerrit_and_reviewer_factory():
    gerrit = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')
    changeset = gerrit.get_changeset("491868")

    RF = add_reviewer.ReviewerFactory()
    reviewers = RF.get_reviewers_for_changeset(changeset)

    assert 'Merlijn van Deen' in reviewers
