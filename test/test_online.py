import add_reviewer
import gerrit_rest


def test_gerrit_and_reviewer_factory():
    gerrit = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')
    changeset = gerrit.get_changeset("1332184")

    RF = add_reviewer.ReviewerFactory()
    reviewers = list(RF.get_reviewers_for_changeset(changeset))

    assert 'valhallasw' in reviewers
