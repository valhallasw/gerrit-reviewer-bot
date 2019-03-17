import logging
import pytest
import pathlib
import json
import add_reviewer

logging.basicConfig(level=logging.DEBUG)
basepath = pathlib.Path(__file__).parent


def test_get_reviewers():
    RF = add_reviewer.ReviewerFactory()
    RF._data = json.load((basepath / "resources" / "api_result.json").open())

    for gerrit_json, expected_reviewers in [
        ("379239.json", ['Merlijn van Deen', 'BryanDavis', 'Arturo Borrero Gonzalez']),
        ("398648.json", []),  # abandoned changeset
        ("402373.json", ['Dduvall', 'BryanDavis', 'mepps', 'XenoRyet', 'jgleeson', 'cstone']),  # popular usage
        ("491868.json", ['Merlijn van Deen', 'legoktm']),
        ("494815.json", []),  # already merged
        ("496929.json", []),  # l10n-bot should be ignored
        ("496844.json", ["Siebrand"]),  # regex filter
    ]:
        changeset = json.load((basepath / "resources" / "gerrit_changesets" / gerrit_json).open())
        reviewers = list(RF.get_reviewers_for_changeset(changeset))

        assert set(reviewers) == set(expected_reviewers)


@pytest.mark.skip("Used as development tool")
def test_create_gerrit_json():
    i = 497076

    import gerrit_rest
    g = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')
    changeset = g.get_changeset(i)

    with (basepath / "resources" / "gerrit_changesets" / ("%s.json" % i)).open("w") as f:
        json.dump(g.get_changeset(i), f)

    RF = add_reviewer.ReviewerFactory()
    RF._data = json.load(open(basepath / "resources" / "api_result.json"))

    print(list(RF.get_reviewers_for_changeset(changeset)))
