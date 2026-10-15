import logging

import gerrit_rest
import pop3bot

logging.basicConfig(level=logging.DEBUG)


def _change(
    number: int, created: str, change_id: str, updated: str | None = None
) -> dict:
    """Build a minimal Gerrit change dict as returned by the REST API."""
    return {
        "_number": number,
        "created": created,
        "updated": updated if updated is not None else created,
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


def test_new_changes_since_keeps_changes_updated_after():
    last = "2024-01-01 00:00:00"
    g = RecordingGerrit(
        [
            # Created before the cutoff but UPDATED after (e.g. just un-WIP'd),
            # at patch set 3 — must be kept (this is the T267787 case).
            _change(3, "2023-12-01 00:00:00", "Iunwip", updated="2024-01-02 00:00:00"),
            # New change, PS1, updated after -> kept.
            _change(1, "2024-01-02 00:00:00", "Inew"),
            # Not updated since the cutoff -> dropped.
            _change(1, "2023-12-31 00:00:00", "Iold"),
        ]
    )

    result = g.new_changes_since(last)

    assert sorted(c["change_id"] for c in result) == ["Inew", "Iunwip"]
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


class _FakeGerrit:
    """Minimal stand-in exposing bot_has_acted with a controllable result."""

    def __init__(self, acted: bool = False):
        self._acted = acted

    def bot_has_acted(self, change_number, bot_account_id, bot_username):
        return self._acted


def test_process_rest_changesets_readonly_does_not_add(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        pop3bot, "add_reviewers", lambda cid, revs: calls.append((cid, revs))
    )

    rf = StubReviewerFactory(["alice"])
    changesets = [_change(1, "2024-06-01 00:00:00", "Ia")]

    results = pop3bot.process_rest_changesets(
        _FakeGerrit(), rf, changesets, authoritative=False
    )

    assert results == {"Ia": ["alice"]}
    assert calls == []  # read-only must not add reviewers


def test_process_rest_changesets_authoritative_adds(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        pop3bot, "add_reviewers", lambda cid, revs: calls.append((cid, revs))
    )

    rf = StubReviewerFactory(["bob"])
    changesets = [_change(1, "2024-06-01 00:00:00", "Ib")]

    results = pop3bot.process_rest_changesets(
        _FakeGerrit(acted=False), rf, changesets, authoritative=True
    )

    assert results == {"Ib": ["bob"]}
    assert calls == [("project~Ib", ["bob"])]


def test_process_rest_changesets_skips_when_bot_already_acted(monkeypatch):
    """Act-once guard (T267787): do not re-add if the bot already acted."""
    calls: list = []
    monkeypatch.setattr(
        pop3bot, "add_reviewers", lambda cid, revs: calls.append((cid, revs))
    )

    rf = StubReviewerFactory(["bob"])
    changesets = [_change(1, "2024-06-01 00:00:00", "Ib")]

    results = pop3bot.process_rest_changesets(
        _FakeGerrit(acted=True), rf, changesets, authoritative=True
    )

    # Reviewers are still computed/reported, but NOT added.
    assert results == {"Ib": ["bob"]}
    assert calls == []


def test_bot_has_acted_reads_reviewer_updates(monkeypatch):
    g = gerrit_rest.GerritREST("http://localhost")

    # Bot added siebrand earlier; even though no reviewers may remain, the
    # updated_by entry proves the bot acted.
    updates = [
        {
            "updated_by": {"_account_id": 578, "username": "reviewer-bot"},
            "reviewer": {"username": "siebrand"},
        },
    ]
    monkeypatch.setattr(g, "reviewer_updates", lambda n: updates)
    assert g.bot_has_acted(123, 578, "reviewer-bot") is True

    # Only a human added reviewers -> bot has not acted.
    updates2 = [
        {
            "updated_by": {"_account_id": 92, "username": "siebrand"},
            "reviewer": {"username": "cparle"},
        },
    ]
    monkeypatch.setattr(g, "reviewer_updates", lambda n: updates2)
    assert g.bot_has_acted(123, 578, "reviewer-bot") is False

    # Match by username when account id differs (rename safety).
    updates3 = [{"updated_by": {"username": "reviewer-bot"}, "reviewer": {}}]
    monkeypatch.setattr(g, "reviewer_updates", lambda n: updates3)
    assert g.bot_has_acted(123, 999, "reviewer-bot") is True
