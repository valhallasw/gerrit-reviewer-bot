import email.message
import email.parser
import logging
import os
import sys
import traceback
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import gerrit_rest
from add_reviewer import ReviewerFactory, add_reviewers

# monkey patch max line length for poplib
# as gmail sometimes sends > 2048 char lines
import poplib
poplib._MAXLINE = 1024 * 1024  # type: ignore[attr-defined]


def _excepthook(exc_type, exc_value, exc_tb):
    print(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'), file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook

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


LAST_NUMBER_FILE = Path('last_change_number.txt')
VALID_SOURCES = ('pop3', 'both', 'rest')


def read_last_number() -> int | None:
    try:
        return int(LAST_NUMBER_FILE.read_text().strip())
    except FileNotFoundError:
        return None
    except ValueError:
        return None


def write_last_number(number: int) -> None:
    LAST_NUMBER_FILE.write_text(str(number))


def compare_tracks(
    primary: dict[str, list[str]],
    secondary: dict[str, list[str]]
) -> None:
    primary_ids = set(primary)
    secondary_ids = set(secondary)

    for change_id in primary_ids - secondary_ids:
        logger.info("REST track: missing change %s", change_id)
    for change_id in secondary_ids - primary_ids:
        logger.info("REST track: extra change %s", change_id)
    for change_id in primary_ids & secondary_ids:
        p = sorted(primary[change_id])
        s = sorted(secondary[change_id])
        if p != s:
            logger.info("REST track: reviewer mismatch for %s: POP3=%r REST=%r", change_id, p, s)


def run_pop3_track(g: gerrit_rest.GerritREST, RF: ReviewerFactory, authoritative: bool) -> dict[str, list[str]]:
    mailbox = mkmailbox(0)
    nmails, octets = mailbox.stat()
    logger.info("%i e-mails to process (%i kB)", nmails, octets / 1024)

    results: dict[str, list[str]] = {}
    try:
        changesets = new_changeset_generator(g, gerritmail_generator(message_generator(mail_generator(mailbox))))
        for changeset in changesets:
            try:
                reviewers = list(RF.get_reviewers_for_changeset(changeset))
                if authoritative:
                    add_reviewers(changeset['id'], reviewers)
                results[changeset['change_id']] = reviewers
            except Exception:
                logger.exception("Exception processing changeset %r", changeset)
    finally:
        mailbox.quit()
    return results


def run_rest_track(g: gerrit_rest.GerritREST, RF: ReviewerFactory, last_number: int, authoritative: bool) -> tuple[dict[str, list[str]], int]:
    results: dict[str, list[str]] = {}
    max_number = last_number
    for changeset in g.new_changes_since(last_number):
        try:
            reviewers = list(RF.get_reviewers_for_changeset(changeset))
            if authoritative:
                add_reviewers(changeset['id'], reviewers)
            results[changeset['change_id']] = reviewers
            max_number = max(max_number, changeset['_number'])
        except Exception:
            logger.exception("Exception in REST track for changeset %r", changeset)
    return results, max_number


def seed_last_number(g: gerrit_rest.GerritREST) -> int:
    changes = g.changes(q='status:open', n=1, o=[])
    number = changes[0]['_number'] if changes else 0
    write_last_number(number)
    logger.info("Seeded %s with change number %i", LAST_NUMBER_FILE, number)
    return number


def get_last_number(g: gerrit_rest.GerritREST, seed_if_missing: bool) -> int | None:
    number = read_last_number()
    if number is None:
        if seed_if_missing:
            return seed_last_number(g)
        return None
    return number


def main():
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        stream=sys.stdout
    )

    import config
    source = getattr(config, 'changeset_source', 'pop3')
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid changeset_source {source!r}, must be one of {VALID_SOURCES}")
    logger.info("Changeset source: %s", source)

    g = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')
    RF = ReviewerFactory()

    if source == 'pop3':
        run_pop3_track(g, RF, authoritative=True)

    elif source == 'both':
        primary_results = run_pop3_track(g, RF, authoritative=True)
        last_number = get_last_number(g, seed_if_missing=True)
        if last_number is None:
            logger.warning("REST track skipped: could not determine last change number")
        else:
            try:
                secondary_results, max_number = run_rest_track(g, RF, last_number, authoritative=False)
                compare_tracks(primary_results, secondary_results)
                write_last_number(max_number)
            except Exception:
                logger.exception("REST track failed")

    elif source == 'rest':
        last_number = get_last_number(g, seed_if_missing=True)
        if last_number is None:
            logger.warning("REST track skipped: could not determine last change number")
        else:
            results, max_number = run_rest_track(g, RF, last_number, authoritative=True)
            write_last_number(max_number)


if __name__ == "__main__":
    main()
