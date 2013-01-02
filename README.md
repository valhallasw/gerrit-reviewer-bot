Gerrit reviewer bot for WMF's Gerrit.

This bot reads reviewers from http://www.mediawiki.org/wiki/Git/Reviewers and adds them to changes in Gerrit.


Usage
-----
First, copy reviewer-bot's id_rsa to the working directory. Then:
``` bash
./run_bot
```

Testing
-------
``` bash
cat stream-events-example | python add_reviewer.py
```

Expected output:
```
Removing owner Merlijn van Deen from reviewer list ['Merlijn van Deen', 'Sumanah']
gerrit set-reviewers --add Sumanah I87fa5cb799c0b9367daad8c2cbb2b8c47f45fcfc
<errors because you haven't added the right id_rsa>
```
(or whatever the current reviewers for test/mediawiki/extensions/examples are)


``` bash
python -c "import add_reviewer; add_reviewer.test_get_reviewers()"
```

Expected output:
```
test/mediawiki/extensions/examples 0 ['Merlijn van Deen']
test/mediawiki/extensions/examples 1 ['Merlijn van Deen']
test/mediawiki/extensions/examples 2 ['Merlijn van Deen']
test/mediawiki/extensions/examples 3 ['Merlijn van Deen']
test/mediawiki/extensions/examples 4 ['Merlijn van Deen']
```
(again: or what the current reviewers are)

L10n-bot commits are filtered:
``` bash
$ cat l10n-test | python add_reviewer.py
Skipping L10n patchset  41058
```
