Gerrit reviewer bot for WMF's Gerrit.

This bot reads reviewers from https://www.mediawiki.org/wiki/Git/Reviewers and adds them to changes in Gerrit.

Changes are read from SSH ('add_reviewers.py') or POP3 ('pop3bot.py').

__fdsa_
Development
-----------
``` bash
virtualenv --system-site-packages reviewer-bot && cd reviewer-bot
source bin/activate
git clone http://github.com/valhallasw/gerrit-reviewer-bot src
cd src
pip install -r requirements
git clone https://gerrit.wikimedia.org/r/pywikibot/core pywikibot
cd pywikibot && git checkout 2.0
```

Then, to test:
``` bash
$ python test.py Ic1250e94c2cbbd3cdc7f1f593be0e204bf735877
Processing changeset  Ic1250e94c2cbbd3cdc7f1f593be0e204bf735877 Moved to TWN, test whether the deployment really works... by Merlijn van Deen
  test.i18n.txt
Suggested reviewers:  ['siebrand', 'Sumanah']
```

The main algorithm for determining reviewers is the ReviewerFactory in
add_reviewer.py. gerrit_rest.py contains basic functionality for accessing
the Gerrit REST API. pop3bot.py reads Gerrit mails from a POP3 mailbox,
retrieves the corresponding changes using the REST API, determines reviewers
using the ReviewerFactory and finally adds reviewers via SSH.

Changes in the ReviewerFactory can best be tested using test.py, as above. If
more information is required from Gerrit, try to do this using options to the 
/changes/ REST API.

Usage/deployment
----------------
First, copy reviewer-bot's id_rsa and config.py to the working directory. Then:
``` bash
source bin/activate
python pop3bot.py
```

Config.py is a simple file containing
``` python
username = 'gmailusername@gmail.com'
password = 'whateveryourpasswordis'
```
(the gmail pop server is hard-coded at the moment)

This will start a single run. Wrap it in a loop with a sleep or use cron to use it constantly.


