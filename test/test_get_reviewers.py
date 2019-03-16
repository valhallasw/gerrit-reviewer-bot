import logging

import pytest

logging.basicConfig(level=logging.DEBUG)

import pathlib
import json
import add_reviewer


basepath = pathlib.Path(__file__).parent


def test_get_reviewers():
    RF = add_reviewer.ReviewerFactory()
    RF._data = json.load(open(basepath / "resources" / "api_result.json"))

    for gerrit_json, expected_reviewers in [
        ("379239.json", ['Merlijn van Deen', 'BryanDavis', 'Arturo Borrero Gonzalez']),
        ("398648.json", []),  # abandoned changeset
        ("402373.json", ['Dduvall', 'BryanDavis', 'mepps', 'XenoRyet', 'jgleeson', 'cstone']),  # popular usage
        ("491868.json", ['Merlijn van Deen', 'legoktm']),
        ("494815.json", []),  # already merged
        ("496929.json", []),  # l10n-bot should be ignored
        ("496844.json", ["Siebrand"]),  # regex filter
    ]:
        changeset = json.load(open(basepath / "resources" / "gerrit_changesets" / gerrit_json))
        reviewers = list(RF.get_reviewers_for_changeset(changeset))

        assert set(reviewers) == set(expected_reviewers)


@pytest.mark.skip("Used as development tool")
def test_create_gerrit_json():
    i = 497076

    import gerrit_rest
    g = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')
    changeset = g.get_changeset(i)

    with open(basepath / "resources" / "gerrit_changesets" / f"{i}.json", "w") as f:
        json.dump(g.get_changeset(i), f)

    RF = add_reviewer.ReviewerFactory()
    RF._data = json.load(open(basepath / "resources" / "api_result.json"))

    print(list(RF.get_reviewers_for_changeset(changeset)))
    # RF = ReviewerFactory()
    # for i in [40978, 40976, 40975, 34673]:
    #     reviewers = RF.get_reviewers_for_changeset(g.get_changeset(i))
    #     print(name, i, reviewers)

# TODO: l10n-test: 41058