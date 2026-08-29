import json
from typing import Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class GerritREST:
    def __init__(self, url: str) -> None:
        """ Basic wrapper around the Gerrit REST API. Takes care of
            connections and JSON-decoding. Currently only GET requests
            are supported.

            Parameters:
              * URL - The base URL, e.g. https://gerrit.wikimedia.org/r
        """
        self._url = url.rstrip('/')
        self._session = requests.Session()
        self._session.mount('https://', HTTPAdapter(max_retries=Retry(total=5, backoff_factor=1)))
        self._session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Gerrit-Reviewer-Bot GerritREST python-requests/%s' % (requests.__version__, )
        })

    def _request(self, name: str, **kwargs: Any) -> Any:
        """ Make a request. Parameters:
            * name - The name of the REST endpoint. This will be appended to the base URL.
            * any parameters taken by the REST endpoint (via kwargs)
        """
        r = self._session.get(self._url + '/%s/' % name, params=kwargs)
        r.raise_for_status()
        return json.loads(r.text[5:])  # strips anti-XSS prefix

    def __getattr__(self, name):
        """ Provides access to any APIs not yet implemented """
        def wrapper(self, **kwargs):
            return self._request(name, **kwargs)
        wrapper.__name__ = name
        return wrapper

    def changes(self, q: str = "", n: int = 25, o: list[str] | None = None) -> list[dict]:
        """ Submits a request to the /changes/ REST API. Parameters:
            * q - the query string,
            * n - the maximum number of results to return - 25 by default,
            * o - the list of options to pass. CURRENT_REVISION and CURRENT_FILES by default.

            See https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html
            for more details. """

        if o is None:
            o = []
        return self._request('changes', q=q, n=n, o=o)

    def get_changeset(self, changeid: str, o: list[str] | None = None) -> dict | None:
        if o is None:
            o = ['CURRENT_REVISION', 'CURRENT_FILES', 'DETAILED_ACCOUNTS']
        matchingchanges = self.changes(changeid, n=1, o=o)
        if matchingchanges:
            return matchingchanges[0]
        else:
            return None
