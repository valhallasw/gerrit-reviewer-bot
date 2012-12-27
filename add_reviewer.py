import sys, json
from pipes import quote
import subprocess

while True:
    line = sys.stdin.readline()
    print line
    data = json.loads(line)
    if data['type'] != 'patchset-created':
        continue
    change = data['change']
    patchset = data['patchSet']
    if int(patchset['number']) != 1:
        continue

    if change['project'] == 'test/mediawiki/extensions/examples':
        reviewers = ['Merlijn van Deen', 'Sumanah']
    else:
        reviewers = []

    if reviewers:
        params = []
        for reviewer in reviewers:
            params.append('--add')
            params.append(reviewer)
        params.append(change['id'])
        command = "gerrit set-reviewers " + " ".join(quote(p) for p in params)
        print command
        print subprocess.call(["ssh", "-i", "id_rsa", "-p", "29418", "reviewer-bot@gerrit.wikimedia.org", command])
