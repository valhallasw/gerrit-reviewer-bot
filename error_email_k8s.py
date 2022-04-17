import smtplib
from email.message import EmailMessage

errlog = open('gerrit-reviewer-bot.err').readlines()[-100:]

errorlines = [line for line in errlog if "Running as task" not in line]

if not any(errorlines):
    print("OK")
    exit(0)

errortext = "".join(errorlines)

message = f"""Hello valhallasw,

It seems gerrit-reviewer-bot has encountered some trouble. Please see
the error below:

-----------------------------------------------------------------------
{errortext}
-----------------------------------------------------------------------

The full error log has been attached for your convenience.

With kind regards,
valhallasw in the past
"""

msg = EmailMessage()
msg.set_content(message)
msg['Subject'] = "Gerrit Reviewer Bot broken"
msg['From'] = "tools.gerrit-reviewer-bot <tools.gerrit-reviewer-bot@tools.wmflabs.org>"
msg['To'] = "valhallasw@arctus.nl"
msg.add_attachment("".join(errlog), filename='error.log')

s = smtplib.SMTP('mail.tools.wmflabs.org')
s.send_message(msg)
s.quit()

print("Sent error email")
