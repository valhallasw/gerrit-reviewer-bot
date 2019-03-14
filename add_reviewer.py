import json
import subprocess
import re
import logging
from pipes import quote
from fnmatch import fnmatch
logger = logging.getLogger('add_reviewers')

import requests
import lxml.objectify

import gerrit_rest
g = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')

def call_utf8(command, *args, **kwargs):
    command = [part.encode('utf-8') for part in command]
    return subprocess.call(command, *args, **kwargs)

class ReviewerFactory(object):
    nofilere = re.compile('')

    def __init__(self, page="Git/Reviewers", template="Gerrit-reviewer"):
        self.page = page
        self.template = template

    @property
    def data(self):
        if hasattr(self, '_data'):
            return self._data
        return requests.get("https://www.mediawiki.org/w/api.php?format=json&action=parse&page=Git/Reviewers&prop=parsetree").json()

    @property
    def objecttree(self):
        return lxml.objectify.fromstring(self.data['parse']['parsetree']['*'])

    def _tryParseInt(self, value, default=None):
        try:
            return int(value)
        except Exception as e:
            return default

    def _reviewer_generator(self, project, changedfiles, addedfiles=[]):
        tree = self.objecttree

        for section in tree.iter('h'):
            name = section.text.strip('= ')
            if not fnmatch(project, name):
                continue
            for sibling in section.itersiblings():
                if sibling.tag == "h":
                    break
                if sibling.tag == "template" and sibling.title == self.template:
                    reviewer = None; modulo = 1; filere=self.nofilere; matchall=False
                    for part in sibling.iter('part'):
                        if part.name == "" and part.name.attrib['index'] == '1':
                            reviewer = part.value.text
                        elif part.name == "every":
                            modulo = self._tryParseInt(part.value, 1)
                            if modulo < 2:
                                modulo = 1
                        elif part.name == "file_regexp":
                            try:
                                filere = re.compile(part.value.text or part.value.ext.inner.text, flags=re.DOTALL | re.IGNORECASE)
                            except re.error as e:
                                logging.error("Could not process file regexp %r -- ignoring." % (part.value.text or part.value.ext.inner.text))
                        elif part.name == "match_all_files" or part.value.text == "match_all_files":
                            matchall = True
                        elif part.name == "only_match_new_files" or part.value.text == "only_match_new_files":
                            logger.info("%r:%r -> only checking new files" % (name, reviewer))
                            changedfiles = addedfiles
                    if matchall:
                        result = all(filere.search(file) for file in changedfiles)
                    else:
                        result = any(filere.search(file) for file in changedfiles)
                    if result:
                        logger.debug('* MATCH in in section %r:' % name)
                        logger.debug(lxml.objectify.dump(sibling))
                        yield reviewer, modulo

    def _filter_reviewers(self, reviewers, owner_name, changeset_number):
        if owner_name.lower() == 'l10n-bot':
            logger.debug('Skipping l10n-bot')
            return

        i = 0
        for (reviewer, modulo) in reviewers:
            if reviewer.lower() == owner_name.lower():
                logger.debug('Skipping owner %r' % reviewer)
                continue

            if ((changeset_number + i) % modulo == 0):
                yield reviewer
            else:
                logger.debug('Skipping %r due to modulo')

    def get_reviewers_for_changeset(self, changeset):
        owner = changeset['owner']['name']

        try:
            changes = list(changeset['revisions'].values())[0]['files']
            changedfiles = [k for (k, v) in list(changes.items())]
            addedfiles = [k for (k, v) in list(changes.items()) if 'status' in v and v['status'] == 'A']
        except Exception as e:
            print(e, repr(changeset))
            changedfiles = addedfiles = []

        project = changeset['project']
        number = changeset['_number']

        print("")
        print("Processing changeset ", changeset['change_id'], changeset['subject'], 'by', owner)
        for f in changedfiles:
            if f in addedfiles:
                print("A", end=' ')
            else:
                print("u", end=' ')
            print(f)

        if changeset['status'] in ['ABANDONED', 'MERGED']:
            print("Changeset was ", changeset['status'], "; not adding reviewers")
            return []

        reviewers = self._filter_reviewers(self._reviewer_generator(project, changedfiles, addedfiles), owner, number)

        return reviewers

def test_get_reviewers():
    RF = ReviewerFactory()
    RF._data = json.load(open("api_result"))
    name = 'test/mediawiki/extensions/examples'

    for i in [40978, 40976, 40975]:
        revs = RF.get_reviewers_for_changeset(g.get_changeset(i))

        for rev in revs:
            assert isinstance(rev, str)
        if i % 5 == 0:
            print(revs)
            assert revs == ["Merlijn van Deen", "Sumanah"]
        else:
            print(revs)
            assert revs == ["Sumanah"]

    RF = ReviewerFactory()
    for i in [40978, 40976, 40975, 34673]:
        change = {'number': i, 'project': name}
        revs = get_reviewers(change, RF)
        print(name, i, revs)

def add_reviewers(changeid, reviewers):
    reviewers = list(reviewers)
    if reviewers:
        params = []
        for reviewer in reviewers:
            params.append('--add')
            params.append(reviewer)
        params.append(changeid)
        command = "gerrit set-reviewers " + " ".join(quote(p) for p in params)
        print(command)
        callcmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "Batchmode=yes", "-i", "id_rsa", "-p", "29418", "reviewer-bot@gerrit.wikimedia.org", command]
        retval = call_utf8(callcmd)
        if retval != 0:
            with open('debug.out', 'a') as fp:
                retval = call_utf8(
                    [callcmd[0]] + ["-v", "-v"] + callcmd[1:],
                    stdout = fp,
                    stderr = subprocess.STDOUT)
            raise Exception(command + ' was not executed successfully (code %i)' % retval)

if __name__ == "__main__":
    test_get_reviewers()