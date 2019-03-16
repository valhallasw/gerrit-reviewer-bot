import logging
from email.message import Message

logging.basicConfig(level=logging.DEBUG)

import pathlib
import pop3bot
import gerrit_rest

from typing import NamedTuple, Tuple, List, Dict

basepath = pathlib.Path(__file__).parent


class ProcessedEmail(NamedTuple):
    messages: List[Tuple[Message, str]]
    gerritmails: List[Dict[str, str]]
    changesets: List[Dict]


class MockGerrit(gerrit_rest.GerritREST):
    def __init__(self):
        super().__init__("http://localhost")

    def _request(self, name, **kwargs):
        raise Exception()

    def get_changeset(self, changeid, o=None):
        return {'commit': changeid}


def process_email(mbox: str) -> ProcessedEmail:
    emails = [open(basepath / "resources" / "gerrit_emails" / mbox).read()]
    messages = list(pop3bot.message_generator(emails))
    gerritmails = list(pop3bot.gerritmail_generator(messages))
    changesets = list(pop3bot.new_changeset_generator(MockGerrit(), gerritmails))

    return ProcessedEmail(messages, gerritmails, changesets)


def test_notgerrit():
    result = process_email("notgerrit.mbox")

    assert len(result.messages) == 1
    assert len(result.gerritmails) == 0
    assert len(result.changesets) == 0


def test_new_patchset():
    result = process_email("497076.mbox")
    assert result.changesets == [{'commit': '9e71f2c950587a0a7a75da49c6af89001803ff17'}]


def test_merged():
    result = process_email("497094-merged.mbox")
    assert len(result.messages) == 1
    assert len(result.gerritmails) == 1
    assert len(result.changesets) == 0
