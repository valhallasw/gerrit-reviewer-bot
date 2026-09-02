import email.message
import email.parser
import logging
import os
import sys
import traceback
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

import time

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

    for attempt in range(3):
        try:
            mailbox = poplib.POP3_SSL(config.pophost, '995', timeout=30)
            mailbox.set_debuglevel(debug)
            mailbox.user(username)
            mailbox.pass_(password)
            return mailbox
        except (poplib.error_proto, OSError) as e:
            if attempt == 2:
                raise
            logger.warning("POP3 connection attempt %d failed: %s; retrying in 5s", attempt + 1, e)
            time.sleep(5)


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


LAST_TIMESTAMP_FILE = Path('last_change_timestamp.txt')
VALID_SOURCES = ('pop3', 'both', 'rest')


def read_last_timestamp() -> str | None:
    try:
        return LAST_TIMESTAMP_FILE.read_text().strip()
    except FileNotFoundError:
        return None


def write_last_timestamp(timestamp: str) -> None:
    LAST_TIMESTAMP_FILE.write_text(timestamp)


def current_timestamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def compare_tracks(
    primary: dict[str, list[str]],
    secondary: dict[str, list[str]]
) -> None:
    primary_ids = set(primary)
    secondary_ids = set(secondary)

    for change_id in primary_ids - secondary_ids:
        logger.info("REST track: change only in POP3 track: %s (reviewers: %r)", change_id, sorted(primary[change_id]))
    for change_id in secondary_ids - primary_ids:
        logger.info("REST track: change only in REST track: %s (reviewers: %r)", change_id, sorted(secondary[change_id]))
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


def fetch_rest_changesets(g: gerrit_rest.GerritREST, last_timestamp: str) -> tuple[list[dict], str]:
    next_timestamp = current_timestamp()
    changesets = g.new_changes_since(last_timestamp)
    logger.info("%i changesets to process via REST (since %s)", len(changesets), last_timestamp)
    return changesets, next_timestamp


def process_rest_changesets(RF: ReviewerFactory, changesets: list[dict], authoritative: bool) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    for changeset in changesets:
        try:
            reviewers = list(RF.get_reviewers_for_changeset(changeset))
            if authoritative:
                add_reviewers(changeset['id'], reviewers)
            elif reviewers:
                logger.info("REST track (read-only): would add reviewers for %s: %r", changeset['change_id'], reviewers)
            results[changeset['change_id']] = reviewers
        except Exception:
            logger.exception("Exception in REST track for changeset %r", changeset)
    return results


def seed_last_timestamp() -> str:
    timestamp = current_timestamp()
    write_last_timestamp(timestamp)
    logger.info("Seeded %s with timestamp %s", LAST_TIMESTAMP_FILE, timestamp)
    return timestamp


def get_last_timestamp(seed_if_missing: bool) -> str | None:
    timestamp = read_last_timestamp()
    if timestamp is None:
        if seed_if_missing:
            return seed_last_timestamp()
        return None
    return timestamp


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

    if source == 'pop3':
        RF = ReviewerFactory(logger=logging.getLogger('add_reviewers.pop3'))
        run_pop3_track(g, RF, authoritative=True)

    elif source == 'both':
        RF_pop3 = ReviewerFactory(logger=logging.getLogger('add_reviewers.pop3'))
        RF_rest = ReviewerFactory(logger=logging.getLogger('add_reviewers.rest'))
        last_timestamp = get_last_timestamp(seed_if_missing=True)
        if last_timestamp is None:
            logger.warning("REST track skipped: could not determine last timestamp")
            run_pop3_track(g, RF_pop3, authoritative=True)
        else:
            try:
                rest_changesets, next_timestamp = fetch_rest_changesets(g, last_timestamp)
            except Exception:
                logger.exception("REST track fetch failed")
                run_pop3_track(g, RF_pop3, authoritative=True)
            else:
                primary_results = run_pop3_track(g, RF_pop3, authoritative=True)
                secondary_results = process_rest_changesets(RF_rest, rest_changesets, authoritative=False)
                compare_tracks(primary_results, secondary_results)
                write_last_timestamp(next_timestamp)

    elif source == 'rest':
        RF = ReviewerFactory(logger=logging.getLogger('add_reviewers.rest'))
        last_timestamp = get_last_timestamp(seed_if_missing=True)
        if last_timestamp is None:
            logger.warning("REST track skipped: could not determine last timestamp")
        else:
            changesets, next_timestamp = fetch_rest_changesets(g, last_timestamp)
            process_rest_changesets(RF, changesets, authoritative=True)
            write_last_timestamp(next_timestamp)


if __name__ == "__main__":
    main()
