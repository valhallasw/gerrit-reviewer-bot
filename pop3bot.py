import os
import sys
import poplib
import email.message
import email.parser
import logging
from collections.abc import Iterable

import gerrit_rest
from add_reviewer import ReviewerFactory, add_reviewers

# monkey patch max line length for poplib
# as gmail sometimes sends > 2048 char lines
poplib._MAXLINE = 1024 * 1024  # type: ignore[attr-defined]

logger = logging.getLogger('pop3bot')


def mkmailbox(debug=0):
    import config
    username = config.username
    password = config.password

    mailbox = poplib.POP3_SSL(config.pophost, '995', timeout=30)
    mailbox.set_debuglevel(debug)

    mailbox.user(username)
    mailbox.pass_(password)

    return mailbox


def mail_generator(mailbox) -> Iterable[bytes]:
    """ RETRieves the contents of mails, yields those
        and DELEtes them before the next mail is RETRieved """
    nmails, octets = mailbox.stat()
    for i in range(1, nmails + 1):
        # use TOP rather than REPR; gmail (sometimes?) interprets REPR'd
        # messages as read and does not report them again (sigh)
        yield b"\n".join(mailbox.top(i, 1000)[1])
        mailbox.dele(i)


def message_generator(emails: Iterable[bytes]) -> Iterable[tuple[email.message.Message, str]]:
    p = email.parser.BytesParser()
    for raw in emails:
        msg = p.parsebytes(raw)
        # if mail is multipart-mime (probably not from gerrit)
        # mail.get_payload() is a list rather than a string
        # and mail.get_payload(decode=True) returns None

        m = msg
        while isinstance(m.get_payload(), list):
            m = m.get_payload()[0]  # type: ignore[assignment,index]

        yield msg, m.get_payload(decode=True).decode('utf-8', 'replace')  # type: ignore[union-attr]


def gerritmail_generator(generator: Iterable[tuple[email.message.Message, str]]) -> Iterable[dict[str, str]]:
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

        logger.info("%s %s %s", subject, sender, gerrit_data.get('X-Gerrit-Change-Id'))

        if gerrit_data:
            yield gerrit_data
        else:
            logger.warning("Skipping; Contents: %s", contents)


def new_changeset_generator(g: gerrit_rest.GerritREST, mail_generator: Iterable[dict[str, str]]) -> Iterable[dict]:
    for mail in mail_generator:
        mt = mail.get('X-Gerrit-MessageType', '')
        ps = mail.get('Gerrit-PatchSet', '')
        commit = mail.get('X-Gerrit-Commit')
        if not commit:
            logger.warning("Skipping message with no X-Gerrit-Commit: %r", mail)
            continue

        if mt != 'newchange':
            logger.debug("skipping message (%s)", mt)
            continue
        if ps != '1':
            logger.debug("skipping PS%s", ps)
            continue
        logger.debug("getting %s", commit)
        matchingchange = g.get_changeset(commit)
        if not matchingchange:
            logger.warning("Could not find matching change for %s", commit)
        elif matchingchange.get('work_in_progress'):
            logger.debug("skipping WIP change %s", commit)
        else:
            yield matchingchange


def main():
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        stream=sys.stdout
    )
    g = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')
    RF = ReviewerFactory()
    mailbox = mkmailbox(0)
    nmails, octets = mailbox.stat()

    logger.info("%i e-mails to process (%i kB)", nmails, octets / 1024)

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
                logger.exception("Exception processing changeset %r", changeset)
    finally:
        # flush succesfully processed emails
        mailbox.quit()


if __name__ == "__main__":
    main()
