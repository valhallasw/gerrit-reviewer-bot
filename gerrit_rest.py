import json, requests

requests.adapters.DEFAULT_RETRIES = 5

class GerritREST(object):
    def __init__(self, url):
        """ Basic wrapper around the Gerrit REST API. Takes care of
            connections and JSON-decoding. Currently only GET requests
            are supported.

            Parameters:
              * URL - The base URL, e.g. https://gerrit.wikimedia.org/r
        """
        self._url = url.rstrip('/')
        self._session = requests.Session()
        self._session.headers.update({'Accept': 'application/json',
                                      'User-Agent':\
'Gerrit-Reviewer-Bot GerritREST python-requests/%s' % (requests.__version__)})

    def _request(self, name, **kwargs):
        """ Make a request. Parameters:
            * name - The name of the REST endpoint. This will be appended to the base URL.
            * any parameters taken by the REST endpoint (via kwargs)
        """
        r = self._session.get(self._url + '/%s/' % name, params=kwargs)
        realjson = r.text[5:] # strips anti-XSS prefix
        return json.loads(realjson)

    def __getattr__(self, name):
        """ Provides access to any APIs not yet implemented """
        def wrapper(self, **kwargs):
            return self._request(name, **kwargs)
        wrapper.__name__ = name
        return wrapper

    def changes(self, q="", n=25, o=[]):
        """ Submits a request to the /changes/ REST API. Parameters:
            * q - the query string,
            * n - the maximum number of results to return - 25 by default,
            * o - the list of options to pass. CURRENT_REVISION and CURRENT_FILES by default.

            See https://gerrit-review.googlesource.com/Documentation/rest-api-changes.html
            for more details. """

        return self._request('changes', q=q, n=n, o=o)

    # def accounts, def groups, def projects, etc.
