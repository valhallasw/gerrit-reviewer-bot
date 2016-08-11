import sys, json
from pipes import quote
import subprocess
import pywikibot
import lxml.objectify
import re
import traceback
import sys
import time
import logging
logger = logging.getLogger('add_reviewers')
from fnmatch import fnmatch

sys.path.append('python-gerrit')
g = None

site = pywikibot.getSite('mediawiki', 'mediawiki')

def call_utf8(command, *args, **kwargs):
    command = [part.encode('utf-8') for part in command]
    return subprocess.call(command, *args, **kwargs)

class ReviewerFactory(object):
    nofilere = re.compile('')

    def __init__(self, site=pywikibot.getSite('mediawiki', 'mediawiki'),
                       page="Git/Reviewers",
                       template="Gerrit-reviewer"):
        self.site = site
        self.page = page
        self.template = template

    @property
    def data(self):
        if hasattr(self, '_data'):
            return self._data
        return pywikibot.data.api.Request(action="parse", page=self.page, prop='parsetree', site=self.site).submit()

    @property
    def objecttree(self):
        return lxml.objectify.fromstring(self.data['parse']['parsetree']['*'])

    def _tryParseInt(self, value, default=None):
        try:
            return int(value)
        except Exception, e:
            return default

    def reviewer_generator(self, project, changedfiles, addedfiles=[]):
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
                            filere = re.compile(part.value.text or part.value.ext.inner.text, flags=re.DOTALL | re.IGNORECASE)
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


def get_reviewers(change, RF=ReviewerFactory()):
        num = int(change['number'])
        reviewers = []
        try:
            changedfiles = [p.path for p in g.change_details(num).last_patchset_details.patches]
        except Exception, e:
            print e
            changedfiles = []
        for i, (reviewer, modulo) in enumerate(RF.reviewer_generator(change['project'], changedfiles)):
            if ((num + i) % modulo == 0):
                reviewers.append(reviewer)
            else:
                logger.debug("NOT adding %r due to modulo match" % reviewer)
        return reviewers

def test_get_reviewers():
    RF = ReviewerFactory()
    RF._data = json.load(open("api_result"))
    name = 'test/mediawiki/extensions/examples'

    for i in [40978, 40976, 40975]:
        change = {'number': i, 'project': name}
        revs = get_reviewers(change, RF)
        for rev in revs:
            assert isinstance(rev, str)
        if i % 5 == 0:
            assert revs == ["Merlijn van Deen", "Sumanah"]
        else:
            assert revs == ["Sumanah"]

    RF = ReviewerFactory()
    for i in [40978, 40976, 40975, 34673]:
        change = {'number': i, 'project': name}
        revs = get_reviewers(change, RF)
        print name, i, revs

def add_reviewers(changeid, reviewers):
    reviewers = list(reviewers)
    if reviewers:
        params = []
        for reviewer in reviewers:
            params.append('--add')
            params.append(reviewer)
        params.append(changeid)
        command = "gerrit set-reviewers " + " ".join(quote(p) for p in params)
        print command
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
    from gerrit.rpc import Client; g=Client('https://gerrit.wikimedia.org/r/', 'gerrit_ui/rpc');
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            data = json.loads(line)
            if data['type'] != 'patchset-created':
                continue
            change = data['change']
            patchset = data['patchSet']
            if int(patchset['number']) != 1:
                continue

            owner = change['owner']['name'].lower()
            if owner == 'l10n-bot':
                print "Skipping L10n patchset ", change['number']
                continue

            reviewers = [r.lower() for r in get_reviewers(change)]
            if owner in reviewers:
                print "Removing owner %s from reviewer list %r" % (owner, reviewers)
                reviewers.remove(owner)

            if reviewers:
                params = []
                for reviewer in reviewers:
                    params.append('--add')
                    params.append(reviewer)
                params.append(change['id'])
                command = "gerrit set-reviewers " + " ".join(quote(p) for p in params)
                print command
                print call_utf8(["ssh", "-i", "id_rsa", "-p", "29418", "reviewer-bot@gerrit.wikimedia.org", command])
        except Exception, e:
            print "-"*80
            print "Exception %r caused by line:" % e
            print "-"*80
            print line,
            print "-"*80
            traceback.print_exc()
            print "-"*80
            time.sleep(3)
