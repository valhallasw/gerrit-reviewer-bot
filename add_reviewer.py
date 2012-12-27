import sys, json
from pipes import quote
import subprocess
import pywikibot

site = pywikibot.getSite('mediawiki', 'mediawiki')

def get_reviewer_page_text(change):
    return pywikibot.Page(site, 'Git/reviewers/' + change['project']).get().encode('utf-8')

def get_reviewers_from_text(change, text):
    number = int(change['number'])
    reviewers = []
    for i, line in enumerate(text.split('\n')):
        try:
            line = line.strip()
            if not line:
                continue
            if line.startswith('<') or line.startswith('#'):
                continue
            elif line.startswith('%'):
                modulo, reviewer = line.split(' ', 1)
                if (number + i) % int(modulo[1:]) == 0:
                        reviewers.append(reviewer)
            else:
                reviewers.append(line)
        except Exception, e:
            print e
            pass

    return reviewers

def test_get_reviewers_from_text():
    change = {'number': '0'}
    text = """<pre>
# Comment line
User always
%2 User sometimes but not now
%2 User sometimes right now
"""
    result = get_reviewers_from_text(change, text)
    assert result == ["User always", "User sometimes right now"], result

def get_reviewers(change):
    try:
        text = get_reviewer_page_text(change)
        return get_reviewers_from_text(change, text)
    except Exception, e:
        print e
        return []

if __name__ == "__main__":
    while True:
        line = sys.stdin.readline()
        data = json.loads(line)
        if data['type'] != 'patchset-created':
            continue
        change = data['change']
        patchset = data['patchSet']
        if int(patchset['number']) != 1:
            continue

        reviewers = get_reviewers(change)

        if reviewers:
            params = []
            for reviewer in reviewers:
                params.append('--add')
                params.append(reviewer)
            params.append(change['id'])
            command = "gerrit set-reviewers " + " ".join(quote(p) for p in params)
            print command
            print subprocess.call(["ssh", "-i", "id_rsa", "-p", "29418", "reviewer-bot@gerrit.wikimedia.org", command])
