import json
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GerritREST:
    def __init__(self, url: str) -> None:
        """Basic wrapper around the Gerrit REST API. Takes care of
        connections and JSON-decoding. Currently only GET requests
        are supported.

        Parameters:
          * URL - The base URL, e.g. https://gerrit.wikimedia.org/r
        """
        self._url = url.rstrip("/")
        self._session = requests.Session()
        retry = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
        user_agent = (
            f"Gerrit-Reviewer-Bot GerritREST python-requests/{requests.__version__}"
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": user_agent,
            }
        )

    def _request(self, name: str, **kwargs: Any) -> Any:
        """Make a request. Parameters:
        * name - The name of the REST endpoint. This will be appended to the base URL.
        * any parameters taken by the REST endpoint (via kwargs)
        """
        r = self._session.get(self._url + f"/{name}/", params=kwargs)
        r.raise_for_status()
        return json.loads(r.text[5:])  # strips anti-XSS prefix

    def __getattr__(self, name):
        """Provides access to any APIs not yet implemented"""

        def wrapper(**kwargs):
            return self._request(name, **kwargs)

        wrapper.__name__ = name
        return wrapper

    def changes(
        self, q: str = "", n: int = 25, o: list[str] | None = None
    ) -> list[dict]:
        """Submits a request to the /changes/ REST API. Parameters:
        * q - the query string,
        * n - the maximum number of results to return - 25 by default,
        * o - the list of options to pass. CURRENT_REVISION and
          CURRENT_FILES by default.

        See https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html
        for more details."""  # noqa: E501

        if o is None:
            o = []
        return self._request("changes", q=q, n=n, o=o)

    def get_changeset(self, changeid: str, o: list[str] | None = None) -> dict | None:
        if o is None:
            o = ["CURRENT_REVISION", "CURRENT_FILES", "DETAILED_ACCOUNTS"]
        matchingchanges = self.changes(changeid, n=1, o=o)
        if matchingchanges:
            return matchingchanges[0]
        else:
            return None

    def reviewer_updates(self, change_number: int | str) -> list[dict]:
        """Return the change's reviewer_updates audit entries.

        Uses the /changes/<id>/detail endpoint, which populates
        reviewer_updates; the /changes/?q= query path returns it empty even
        with the REVIEWER_UPDATES option, so it cannot be used here.
        """
        detail = self._request(f"changes/{change_number}/detail")
        return detail.get("reviewer_updates", [])

    def bot_has_acted(
        self, change_number: int | str, bot_account_id: int, bot_username: str
    ) -> bool:
        """True if the bot ever added a reviewer to this change.

        Reads the change's reviewer_updates audit log (append-only), matching
        on the stable account id first and falling back to the username. This
        is the "act once per change" guard for T267787: because it keys on who
        *performed* the add (updated_by), it stays true even if every reviewer
        the bot added was later removed — so the bot never re-adds opted-out
        reviewers.
        """
        for update in self.reviewer_updates(change_number):
            by = update.get("updated_by") or {}
            if by.get("_account_id") == bot_account_id:
                return True
            if by.get("username") == bot_username:
                return True
        return False

    def new_changes_since(self, last_timestamp: str) -> list[dict]:
        """Return open, non-WIP changes updated since last_timestamp.

        Keyed on *update* time (not creation) so that a change which was
        created WIP and later marked ready for review is surfaced — see
        T267787. Callers must guard against re-processing a change the bot has
        already acted on (see pop3bot's act-once check), because an update-based
        query re-sees a change on every modification.
        """
        changes = self.changes(
            q=f'status:open -is:wip after:"{last_timestamp}"',
            n=100,
            o=["CURRENT_REVISION", "CURRENT_FILES", "DETAILED_ACCOUNTS"],
        )
        # 'after:' matches on last-update time, but filter explicitly too in
        # case the stored timestamp granularity differs from Gerrit's.
        return [c for c in changes if c["updated"] > last_timestamp]
