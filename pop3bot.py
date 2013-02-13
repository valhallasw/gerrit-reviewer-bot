import poplib
import email.parser
import config

def mkmailbox(debug=0):
    username = config.username
    password = config.password

    mailbox = poplib.POP3_SSL('pop.googlemail.com', '995') 
    mailbox.set_debuglevel(debug)

    mailbox.user(username)
    mailbox.pass_(password)

    return mailbox

def mail_generator(mailbox):
    """ RETRieves the contents of mails, yields those
        and DELEtes them before the next mail is RETRieved """
    nmails, octets = mailbox.stat()
    for i in range(1,nmails+1):
        yield "\n".join(mailbox.retr(i)[1])
        mailbox.dele(i)

def message_generator(mailbox):
    p = email.parser.Parser()
    for mail in mail_generator(mailbox):
        mail = p.parsestr(mail)
        yield mail, mail.get_payload(decode=True)

def gerritmail_generator(mailbox):
    for message, contents in message_generator(mailbox):
        gerrit_data = dict((k,v) for (k,v) in message.items() if k.startswith('X-Gerrit'))
        gerrit_data.update(dict(line.split(": ", 1) for line in contents.split('\n') if (line.startswith("Gerrit-") and ": " in line)))

        if gerrit_data:
            yield gerrit_data

import gerrit_rest
g = gerrit_rest.GerritREST('https://gerrit.wikimedia.org/r')

def new_changeset_generator(mailbox, o=['CURRENT_REVISION', 'CURRENT_FILES']):
    for mail in gerritmail_generator(mailbox):
        if mail.get('X-Gerrit-MessageType', '') != 'newchange':
            continue
        if mail.get('Gerrit-PatchSet', '') != '1':
            continue
        matchingchanges = g.changes(q=mail['X-Gerrit-Change-Id'], n=1, o=o)
        if matchingchanges:
            yield matchingchanges[0]

mailbox = mkmailbox(0)
nmails, octets = mailbox.stat()

print "%i e-mails to process (%i kB)" % (nmails, octets/1024)

from add_reviewer import ReviewerFactory, add_reviewers

RF = ReviewerFactory()

def filter_reviewers(reviewers, owner_name, changeset_number):
    if owner_name.lower() == u'l10n-bot':
        return

    i = 0
    for (reviewer, modulo) in reviewers:
        if reviewer.lower() == owner_name.lower():
            continue

        if ((changeset_number + i) % modulo == 0):
            yield reviewer

for j,changeset in enumerate(new_changeset_generator(mailbox)):
    owner = changeset['owner']['name']
    changedfiles = changeset['revisions'].values()[0]['files'].keys()
    project = changeset['project']
    number = changeset['_number']

    print ""
    print "Processing changeset ", changeset['change_id'], changeset['subject']
    print "  " + "\n  ".join(changedfiles)

    reviewers = filter_reviewers(RF.reviewer_generator(project, changedfiles), owner, number)

    add_reviewers(changeset['change_id'], reviewers)

mailbox.quit()