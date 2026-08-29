import smtplib
from email.message import EmailMessage
import config

try:
    errlog = open('gerrit-reviewer-bot.err').readlines()[-100:]
except FileNotFoundError:
    print("OK")
    exit(0)

errorlines = [line for line in errlog if "Running as task" not in line]

if not any(errorlines):
    print("OK")
    exit(0)

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
msg['Subject'] = "Gerrit Reviewer Bot broken"
msg['From'] = config.error_mail_from
msg['To'] = config.error_mail_to
msg.add_attachment("".join(errlog), filename='error.log')

s = smtplib.SMTP(config.smtp_host)
s.send_message(msg)
s.quit()

print("Sent error email")
