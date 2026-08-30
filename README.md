Gerrit reviewer bot for WMF's Gerrit.

This bot reads reviewers from https://www.mediawiki.org/wiki/Git/Reviewers and
adds them to changes in Gerrit.

Changes are read from SSH ('add_reviewers.py'), POP3 ('pop3bot.py'), or the Gerrit REST API ('pop3bot.py' with `changeset_source = 'rest'`).

Development
-----------
``` bash
git clone https://github.com/valhallasw/gerrit-reviewer-bot
cd gerrit-reviewer-bot
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Then, to test:
``` bash
.venv/bin/pytest
```

The main algorithm for determining reviewers is the ReviewerFactory in
add_reviewer.py. gerrit_rest.py contains basic functionality for accessing
the Gerrit REST API. pop3bot.py reads Gerrit mails from a POP3 mailbox,
retrieves the corresponding changes using the REST API, determines reviewers
using the ReviewerFactory and finally adds reviewers via SSH.

Changes in the ReviewerFactory can best be tested using pytest. If
more information is required from Gerrit, try to do this using options to the
/changes/ REST API.

Configuration
-------------
Runtime configuration is split between environment variables and `config.py`.

Copy `config.py.example` to `config.py` and fill in the values. This file is
not committed to the repository as it contains credentials.

| Setting             | Description                                      |
|---------------------|--------------------------------------------------|
| `username`          | POP3 mailbox username                            |
| `password`          | POP3 mailbox password                            |
| `pophost`           | POP3 server hostname                             |
| `smtp_host`         | SMTP server for error emails                     |
| `error_mail_from`   | Sender address for error emails                  |
| `error_mail_to`     | Recipient(s) for error emails (comma-separated)  |
| `changeset_source`  | Changeset source: `pop3` (default), `both`, or `rest`. `both` runs the REST API track in read-only mode alongside POP3 for comparison. `rest` uses the REST API as the authoritative source. When switching to `both` or `rest`, `last_change_number.txt` is seeded automatically on the first run. |

The following environment variables are also supported:

| Variable    | Default | Description                                      |
|-------------|---------|--------------------------------------------------|
| `LOG_LEVEL` | `INFO`  | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

To change the log level in production, add or update the `env:` block for the
relevant job in `k8s-jobs.yaml`:

``` yaml
- name: gerrit-reviewer-bot
  ...
  env:
    - name: LOG_LEVEL
      value: INFO
```

Then reload the job spec:

``` bash
toolforge jobs load k8s-jobs.yaml
```

The next pod that spawns will pick up the new value.

Usage/deployment
----------------
The bot runs on [Wikimedia Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge)
as the `gerrit-reviewer-bot` tool, scheduled via `k8s-jobs.yaml`.

To get access, request membership at https://toolsadmin.wikimedia.org/tools/id/gerrit-reviewer-bot.

To deploy changes:
``` bash
ssh <your-wikitech-username>@login.toolforge.org
become gerrit-reviewer-bot
cd ~/src/gerrit-reviewer-bot
git pull
toolforge jobs load k8s-jobs.yaml
```

To set up the venv for manual runs on the bastion (only needed once, or after Python upgrades):
``` bash
python3.13 -m venv --without-pip ~/venv-tf-python313
curl -sSf https://bootstrap.pypa.io/get-pip.py | ~/venv-tf-python313/bin/python
~/venv-tf-python313/bin/pip install -r requirements.txt
```

To do a manual test run:
``` bash
bash ~/src/gerrit-reviewer-bot/gerrit_reviewer_bot_tf-python313.sh
```

To override the log level for a manual run:
``` bash
LOG_LEVEL=INFO bash ~/src/gerrit-reviewer-bot/gerrit_reviewer_bot_tf-python313.sh
```
