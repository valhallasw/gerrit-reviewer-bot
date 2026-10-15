import smtplib
import sys
from datetime import UTC, datetime
from email.message import EmailMessage

import config


def log(text: str) -> None:
    """Print a line prefixed with a UTC timestamp (matching pop3bot's format)."""
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"{ts} {text}")


try:
    errlog = open("gerrit-reviewer-bot.err").readlines()[-100:]
except FileNotFoundError:
    log("OK")
    sys.exit(0)

errorlines = errlog

if not any(errorlines):
    log("OK")
    sys.exit(0)

errortext = "".join(errorlines)

message = f"""It seems gerrit-reviewer-bot has encountered some trouble. Please see
the error below:

-----------------------------------------------------------------------
{errortext}
-----------------------------------------------------------------------

The full error log has been attached for your convenience.
"""

msg = EmailMessage()
msg.set_content(message)
msg["Subject"] = "Gerrit Reviewer Bot broken"
msg["From"] = config.error_mail_from
msg["To"] = config.error_mail_to
msg.add_attachment("".join(errlog), filename="error.log")

try:
    s = smtplib.SMTP(config.smtp_host)
    s.send_message(msg)
    s.quit()
    log("Sent error email")
except smtplib.SMTPException as e:
    log(f"Failed to send error email: {e}")
    sys.exit(1)
