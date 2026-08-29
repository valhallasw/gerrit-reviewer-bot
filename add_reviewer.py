import subprocess
import re
import logging
from shlex import quote
from fnmatch import fnmatch
from typing import Generator, Iterable

import requests
import lxml.objectify


logger = logging.getLogger('add_reviewers')


def call_utf8(command: list[str], *args, **kwargs) -> int:
    return subprocess.call(command, *args, **kwargs)


class ReviewerFactory:
    nofilere = re.compile('')

    def __init__(self, page: str = "Git/Reviewers", template: str = "Gerrit-reviewer") -> None:
        self.page = page
        self.template = template

    @property
    def data(self):
        if hasattr(self, '_data'):
            return self._data
        url = "https://www.mediawiki.org/w/api.php?format=json&action=parse&page=Git/Reviewers&prop=parsetree"
        headers = {"User-Agent": "gerrit-reviewer-bot/1.0 (https://github.com/valhallasw/gerrit-reviewer-bot)"}
        return requests.get(url, headers=headers).json()

    @property
    def objecttree(self):
        return lxml.objectify.fromstring(self.data['parse']['parsetree']['*'])

    def _tryParseInt(self, value, default: int | None = None) -> int | None:
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _parse_template(self, sibling, changedfiles, addedfiles, name):
        reviewer = None
        modulo = 1
        filere = self.nofilere
        matchall = False

        for part in sibling.iter('part'):
            if part.name == "" and part.name.attrib['index'] == '1':
                reviewer = part.value.text
            elif part.name == "every":
                modulo = self._tryParseInt(part.value, 1)
                if modulo < 2:
                    modulo = 1
            elif part.name == "file_regexp":
                try:
                    regexp = part.value.text or part.value.ext.inner.text
                    filere = re.compile(regexp, flags=re.DOTALL | re.IGNORECASE)
                except re.error:
                    logging.error("Could not process file regexp %r -- ignoring." % regexp)
            elif part.name == "match_all_files" or part.value.text == "match_all_files":
                matchall = True
            elif part.name == "only_match_new_files" or part.value.text == "only_match_new_files":
                logger.info("%r:%r -> only checking new files" % (name, reviewer))
                changedfiles = addedfiles

        return reviewer, modulo, filere, matchall, changedfiles

    def _reviewer_generator(
        self, project: str, changedfiles: list[str], addedfiles: list[str] | None = None
    ) -> Generator[tuple[str, int], None, None]:
        if addedfiles is None:
            addedfiles = []
        tree = self.objecttree

        for section in tree.iter('h'):
            name = section.text.strip('= ')
            if not fnmatch(project, name):
                continue
            for sibling in section.itersiblings():
                if sibling.tag == "h":
                    break
                if sibling.tag == "template" and sibling.title == self.template:
                    reviewer, modulo, filere, matchall, changedfiles = self._parse_template(
                        sibling, changedfiles, addedfiles, name
                    )
                    if matchall:
                        result = all(filere.search(file) for file in changedfiles)
                    else:
                        result = any(filere.search(file) for file in changedfiles)
                    if result:
                        logger.debug('* MATCH in in section %r:' % name)
                        logger.debug(lxml.objectify.dump(sibling))
                        yield reviewer, modulo

    def _filter_reviewers(
        self, reviewers: Iterable[tuple[str, int]], owner_name: str, changeset_number: int
    ) -> Generator[str, None, None]:
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
            i += 1

    def get_reviewers_for_changeset(self, changeset: dict) -> list[str] | Iterable[str]:
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
        callcmd = [
            "ssh", "-o", "ConnectTimeout=10", "-o", "Batchmode=yes",
            "-o", "UserKnownHostsFile=known_hosts", "-i", "id_rsa",
            "-p", "29418", "reviewer-bot@gerrit.wikimedia.org", command
        ]
        retval = call_utf8(callcmd)
        if retval != 0:
            with open('debug.out', 'a') as fp:
                retval = call_utf8(
                    [callcmd[0]] + ["-v", "-v"] + callcmd[1:],
                    stdout=fp,
                    stderr=subprocess.STDOUT)
            raise Exception(command + ' was not executed successfully (code %i)' % retval)
