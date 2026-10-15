import logging
import sys
import types
from email.message import Message
from pathlib import Path

import pop3bot

logging.basicConfig(level=logging.DEBUG)


def _make_config(monkeypatch):
    """Install a fake `config` module so the helper's `import config` works."""
    cfg = types.ModuleType("config")
    cfg.smtp_host = "localhost"
    cfg.error_mail_from = "from@example.org"
    cfg.error_mail_to = "to@example.org"
    monkeypatch.setitem(sys.modules, "config", cfg)
    return cfg


class _RecordingSMTP:
    """Stand-in for smtplib.SMTP that records sent messages."""

    sent: list = []

    def __init__(self, host):
        self.host = host

    def send_message(self, msg):
        _RecordingSMTP.sent.append(msg)

    def quit(self):
        pass


def _comment_message() -> Message:
    msg = Message()
    msg["Subject"] = "Change marked ready for review"
    msg["X-Gerrit-MessageType"] = "comment"
    return msg


def _install(monkeypatch, tmp_path: Path):
    _make_config(monkeypatch)
    _RecordingSMTP.sent = []
    import smtplib

    monkeypatch.setattr(smtplib, "SMTP", _RecordingSMTP)
    monkeypatch.setattr(
        pop3bot, "UNWIP_SAMPLE_FILE", tmp_path / "unwip_sample_sent.txt"
    )


def test_forwards_once_and_writes_control_file(monkeypatch, tmp_path):
    _install(monkeypatch, tmp_path)

    pop3bot._forward_unwip_sample(
        _comment_message(), "Patch Set 2: Set Ready For Review"
    )

    assert len(_RecordingSMTP.sent) == 1
    sent = _RecordingSMTP.sent[0]
    assert "T267787" in sent["Subject"]
    assert "Set Ready For Review" in sent.get_content()
    assert (tmp_path / "unwip_sample_sent.txt").exists()


def test_does_not_forward_when_control_file_exists(monkeypatch, tmp_path):
    _install(monkeypatch, tmp_path)
    (tmp_path / "unwip_sample_sent.txt").write_text("already sent")

    pop3bot._forward_unwip_sample(_comment_message(), "body")

    assert _RecordingSMTP.sent == []


def test_control_file_not_written_when_send_fails(monkeypatch, tmp_path):
    _install(monkeypatch, tmp_path)
    import smtplib

    class _FailingSMTP(_RecordingSMTP):
        def send_message(self, msg):
            raise smtplib.SMTPException("boom")

    monkeypatch.setattr(smtplib, "SMTP", _FailingSMTP)

    pop3bot._forward_unwip_sample(_comment_message(), "body")

    # Send failed, so the control file must NOT exist -> retried next run.
    assert not (tmp_path / "unwip_sample_sent.txt").exists()


def test_capture_is_triggered_via_generator(monkeypatch, tmp_path):
    """A comment-type mail flowing through gerritmail_generator triggers capture."""
    _install(monkeypatch, tmp_path)

    msg = _comment_message()
    emails = [(msg, "Patch Set 2: Set Ready For Review")]

    # gerritmail_generator still yields the comment mail (capture-only, no
    # change to the yield behavior), and the forward happens as a side effect.
    list(pop3bot.gerritmail_generator(emails))

    assert len(_RecordingSMTP.sent) == 1
    assert (tmp_path / "unwip_sample_sent.txt").exists()
