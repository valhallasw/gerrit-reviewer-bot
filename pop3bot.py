import sys
import poplib
import email.parser
import logging
import traceback
from email.message import Message
from typing import Iterable, Dict, Tuple

import gerrit_rest
from add_reviewer import ReviewerFactory, add_reviewers

# monkey patch max line length for poplib
# as gmail sometimes sends > 2048 char lines
poplib._MAXLINE = 1024 * 1024

logger = logging.getLogger('pop3bot')


def mkmailbox(debug=0):
    import config
    username = config.username
    password = config.password

    mailbox = poplib.POP3_SSL(config.pophost, '995')
    mailbox.set_debuglevel(debug)

    mailbox.user(username)
    mailbox.pass_(password)

    return mailbox


def mail_generator(mailbox) -> Iterable[str]:
    """ RETRieves the contents of mails, yields those
        and DELEtes them before the next mail is RETRieved """
    nmails, octets = mailbox.stat()
    for i in range(1, nmails + 1):
        # use TOP rather than REPR; gmail (sometimes?) interprets REPR'd
        # messages as read and does not report them again (sigh)
        yield b"\n".join(mailbox.top(i, 1000)[1])
        mailbox.dele(i)


def message_generator(emails: Iterable[bytes]) -> Iterable[Tuple[Message, str]]:
    p = email.parser.BytesParser()
    for mail in emails:
        mail = p.parsebytes(mail)
        # if mail is multipart-mime (probably not from gerrit)
        # mail.get_payload() is a list rather than a string
        # and mail.get_payload(decode=True) returns None

        m = mail
        while isinstance(m.get_payload(), list):
            m = m.get_payload()[0]

        yield mail, m.get_payload(decode=True).decode('utf-8', 'replace')


def gerritmail_generator(generator: Iterable[Tuple[Message, str]]) -> Iterable[Dict[str, str]]:
    for message, contents in generator:
        mi = dict(list(message.items()))
        subject = mi.get('Subject', 'Unknown')
        sender = mi.get('From', 'Unknown')

        gerrit_data = {}

        for (header, value) in message.items():
            if header.startswith("X-Gerrit"):
                gerrit_data[header] = value.rstrip()

        for line in contents.split("\n"):
            if line.startswith("Gerrit-") and ": " in line:
                k, v = line.split(": ", 1)
                gerrit_data[k] = v.rstrip()

        print(subject, sender, gerrit_data.get('X-Gerrit-Change-Id'))

        if gerrit_data:
            yield gerrit_data
        else:
            print("Skipping; Contents: ")
            print(contents)


def new_changeset_generator(g: gerrit_rest.GerritREST, mail_generator: Iterable[Dict[str, str]]) -> Iterable[Dict]:
    for mail in mail_generator:
        mt = mail.get('X-Gerrit-MessageType', '')
        ps = mail.get('Gerrit-PatchSet', '')
        commit = mail['X-Gerrit-Commit']

        if mt != 'newchange':
            print("skipping message (%s)" % mt)
            continue
        if ps != '1':
            print("skipping PS%s" % ps)
            continue
        print("(getting ", commit, ")")
        matchingchange = g.get_changeset(commit)
        if matchingchange:
            yield matchingchange
        else:
            print("Could not find matching change for %s" % commit)


def main():
    g = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')
    RF = ReviewerFactory()
    mailbox = mkmailbox(0)
    nmails, octets = mailbox.stat()

    print("%i e-mails to process (%i kB)" % (nmails, octets / 1024))

    try:
        emails = mail_generator(mailbox)
        messages = message_generator(emails)
        gerritmails = gerritmail_generator(messages)
        changesets = new_changeset_generator(g, gerritmails)

        for j, changeset in enumerate(changesets):
            try:
                reviewers = RF.get_reviewers_for_changeset(changeset)
                add_reviewers(changeset['id'], reviewers)
            except Exception:
                sys.stdout.write(repr(changeset) + "\n caused exception:")
                traceback.print_exc()
                sys.stderr.write(repr(changeset) + "\n caused exception:")
                raise
    finally:
        # flush succesfully processed emails
        mailbox.quit()


if __name__ == "__main__":
    main()
