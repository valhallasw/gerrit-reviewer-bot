import logging

import add_reviewer
import gerrit_rest
import pop3bot

logging.basicConfig(level=logging.DEBUG)


def _change(number: int, created: str, change_id: str) -> dict:
    """Build a minimal Gerrit change dict as returned by the REST API."""
    return {
        "_number": number,
        "created": created,
        "change_id": change_id,
        "id": f"project~{change_id}",
        "revisions": {"rev": {"_number": number}},
    }


class RecordingGerrit(gerrit_rest.GerritREST):
    """GerritREST whose .changes() returns a canned list and records the query."""

    def __init__(self, changes_result: list[dict]):
        super().__init__("http://localhost")
        self._changes_result = changes_result
        self.last_query: dict | None = None

    def changes(self, q: str = "", n: int = 25, o=None) -> list[dict]:
        self.last_query = {"q": q, "n": n, "o": o}
        return self._changes_result


def test_new_changes_since_keeps_only_first_patchset_created_after():
    last = "2024-01-01 00:00:00"
    g = RecordingGerrit(
        [
            _change(1, "2024-01-02 00:00:00", "Ikeep"),  # PS1, newer -> kept
            _change(2, "2024-01-02 00:00:00", "Inotps1"),  # PS2 -> dropped
            _change(1, "2023-12-31 00:00:00", "Iold"),  # too old -> dropped
        ]
    )

    result = g.new_changes_since(last)

    assert [c["change_id"] for c in result] == ["Ikeep"]
    # The query is scoped to open, non-WIP changes after the timestamp.
    assert g.last_query is not None
    assert "status:open" in g.last_query["q"]
    assert "-is:wip" in g.last_query["q"]
    assert last in g.last_query["q"]


def test_new_changes_since_empty():
    g = RecordingGerrit([])
    assert g.new_changes_since("2024-01-01 00:00:00") == []


def test_fetch_rest_changesets_returns_changes_and_timestamp():
    g = RecordingGerrit([_change(1, "2024-06-01 00:00:00", "Ia")])
    changesets, next_timestamp = pop3bot.fetch_rest_changesets(g, "2024-01-01 00:00:00")

    assert [c["change_id"] for c in changesets] == ["Ia"]
    # next_timestamp is a fresh "YYYY-MM-DD HH:MM:SS" stamp to persist.
    assert len(next_timestamp) == len("2024-01-01 00:00:00")


class StubReviewerFactory:
    """Returns a fixed reviewer list regardless of input."""

    def __init__(self, reviewers: list[str]):
        self._reviewers = reviewers

    def get_reviewers_for_changeset(self, changeset: dict):
        return list(self._reviewers)


def test_process_rest_changesets_readonly_does_not_add(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        add_reviewer,
        "add_reviewers",
        lambda cid, revs: calls.append((cid, revs)),
    )
    monkeypatch.setattr(
        pop3bot,
        "add_reviewers",
        lambda cid, revs: calls.append((cid, revs)),
    )

    rf = StubReviewerFactory(["alice"])
    changesets = [_change(1, "2024-06-01 00:00:00", "Ia")]

    results = pop3bot.process_rest_changesets(rf, changesets, authoritative=False)

    assert results == {"Ia": ["alice"]}
    assert calls == []  # read-only must not add reviewers


def test_process_rest_changesets_authoritative_adds(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        pop3bot,
        "add_reviewers",
        lambda cid, revs: calls.append((cid, revs)),
    )

    rf = StubReviewerFactory(["bob"])
    changesets = [_change(1, "2024-06-01 00:00:00", "Ib")]

    results = pop3bot.process_rest_changesets(rf, changesets, authoritative=True)

    assert results == {"Ib": ["bob"]}
    assert calls == [("project~Ib", ["bob"])]
