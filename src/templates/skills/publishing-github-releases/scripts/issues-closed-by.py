#!/usr/bin/env python3
"""Prove a pull request will actually close what it says it fixes — and sweep for the ones that didn't.

GitHub closes an issue on merge only when the PR body carries a *closing keyword*
(`Closes #12`, `Fixes #12`, `Resolves #12`). A bare `#12` renders as a link and reads to a
human exactly like a promise, but closes nothing. A pull request that mentions five issues
that way ships every fix and leaves all five open — which reads to an owner as work never done.

`closingIssuesReferences` is what GitHub will really act on, so that is what this asks.

    ./issues-closed-by.py --pr 128           # before merging: does it close what it mentions?
    ./issues-closed-by.py --stale            # sweep: open issues a merged PR already fixed
    ./issues-closed-by.py --pr 131 --repo owner/name

The repository defaults to the checkout the command runs in. From anywhere else, name it with
`--repo`.

    "$RUNDESK_SKILLS/publishing-github-releases/scripts/issues-closed-by.py" --stale

Exit status is 0 when nothing is wrong, 1 when a PR would leave an issue behind, and 2 when
GitHub could not be asked at all — never 0 for an unanswered question.
"""

import argparse
import json
import re
import subprocess
import sys

#: What GitHub itself accepts. Kept here so the message can name them all.
KEYWORDS = ("close", "closes", "closed", "fix", "fixes", "fixed", "resolve", "resolves",
            "resolved")
MENTION = re.compile(r"#(\d+)\b")
#: How a body says "I named this on purpose and am not closing it". Recognised, because a
#: check that goes on complaining after you have answered it is one people learn to ignore —
#: and the instruction to declare a reference is worthless if nothing reads the declaration.
DECLARED = re.compile(r"^.*(?:reference only|not closed by this|only a reference).*$",
                      re.IGNORECASE | re.MULTILINE)


def unanswerable(why: str):
    """Stop at 2 and say why.

    `sys.exit` takes the status or the message, never both, so the reason has to be printed
    first. Written out because `sys.exit(f"..." and 2)` reads like it does both and does not:
    `and` returns the 2 and the message is discarded, leaving a bare exit nobody can diagnose.
    """
    print(why, file=sys.stderr)
    sys.exit(2)


def gh(*argv):
    """One `gh` call, or a truthful failure — never an empty answer standing in for one."""
    done = subprocess.run(("gh",) + argv, capture_output=True, text=True)
    if done.returncode != 0:
        unanswerable(f"could not ask github: {done.stderr.strip()[:300]}")
    return json.loads(done.stdout) if done.stdout.strip() else None


def here() -> str:
    """The repository this checkout belongs to, or a refusal naming the way out.

    Asked of the working directory rather than baked in, because the whole point of this
    living beside a skill is that it is not one project's command. Outside a checkout there
    is no answer to guess at, so it says which flag supplies one.
    """
    done = subprocess.run(
        ("gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"),
        capture_output=True, text=True)
    if done.returncode != 0 or not done.stdout.strip():
        unanswerable("no repository here, and none named: pass --repo owner/name")
    return done.stdout.strip()


def mentioned(text: str) -> set:
    """Every issue number a body points at, however it points at it."""
    return {int(one) for one in MENTION.findall(text or "")}


def declared(body: str) -> set:
    """Issue numbers the body says out loud it is naming rather than closing."""
    return {int(one) for line in DECLARED.findall(body or "")
            for one in MENTION.findall(line)}


def an_issue(repo: str, number: int) -> bool:
    """Whether that number is an issue rather than a pull request.

    GitHub numbers both from one sequence and `gh issue view` happily answers about a PR, so
    a body that names a sibling pull request read as an issue somebody had failed to close.
    """
    done = subprocess.run(
        ("gh", "api", f"repos/{repo}/issues/{number}", "--jq", ".pull_request.url // \"\""),
        capture_output=True, text=True)
    if done.returncode != 0:
        return False          # cannot be read, so cannot be claimed to be a stale issue
    return not done.stdout.strip()


def check_one(repo: str, number: int) -> int:
    pr = gh("pr", "view", str(number), "-R", repo, "--json",
            "body,title,state,closingIssuesReferences")
    will_close = {one["number"] for one in pr["closingIssuesReferences"]}
    # The PR's own number is not an issue it fixes, and neither is a sibling PR it merely
    # names. Anything left is something a reader would fairly expect to be closed.
    claimed = mentioned(pr["body"]) | mentioned(pr["title"])
    claimed.discard(number)
    claimed -= declared(pr["body"])
    open_issues = set()
    for one in sorted(claimed - will_close):
        if not an_issue(repo, one):
            continue
        kind = gh("issue", "view", str(one), "-R", repo, "--json", "state,title")
        if kind and kind["state"] == "OPEN":
            open_issues.add((one, kind["title"]))

    print(f"PR #{number} ({pr['state']}): closes {sorted(will_close) or 'nothing'}")
    if not open_issues:
        print("  ok — every open issue it names will close on merge")
        return 0
    print(f"  MENTIONED BUT NOT CLOSING — {len(open_issues)} open issue(s):")
    for one, title in sorted(open_issues):
        print(f"    #{one}  {title[:70]}")
    print(f"  add a closing keyword ({KEYWORDS[1]}/{KEYWORDS[4]}/{KEYWORDS[7]} #<n>) to the "
          "PR body, or say in the body why it is only a reference")
    return 1


def sweep(repo: str, most: int) -> int:
    """Open issues that a merged pull request already claims to have fixed."""
    merged = gh("pr", "list", "-R", repo, "--state", "merged", "--limit", str(most),
                "--json", "number,title,body,closingIssuesReferences")
    stranded = {}
    for pr in merged:
        will_close = {one["number"] for one in pr["closingIssuesReferences"]}
        claimed = (mentioned(pr["body"]) | mentioned(pr["title"])) - will_close
        claimed.discard(pr["number"])
        for one in claimed:
            stranded.setdefault(one, []).append(pr["number"])

    left = []
    for one in sorted(stranded):
        if not an_issue(repo, one):
            continue
        kind = gh("issue", "view", str(one), "-R", repo, "--json", "state,title")
        if kind and kind["state"] == "OPEN":
            left.append((one, kind["title"], stranded[one]))

    print(f"{len(merged)} merged pull requests read")
    if not left:
        print("  ok — no open issue is named by a merged pull request")
        return 0
    print(f"  STALE — {len(left)} open issue(s) a merged pull request already names:")
    for one, title, prs in left:
        print(f"    #{one}  {title[:60]}  (named by {', '.join('#'+str(p) for p in prs)})")
    print("  close each with the evidence, or say on it why it is still open")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="owner/name (default: the repository this checkout is)")
    parser.add_argument("--pr", type=int, help="check one pull request before merging it")
    parser.add_argument("--stale", action="store_true",
                        help="sweep merged pull requests for issues left open")
    parser.add_argument("--most", type=int, default=40,
                        help="how many merged pull requests the sweep reads (default: 40)")
    args = parser.parse_args()
    if not args.pr and not args.stale:
        parser.error("say which: --pr <n> before merging, or --stale to sweep")
    repo = args.repo or here()
    worst = 0
    if args.pr:
        worst |= check_one(repo, args.pr)
    if args.stale:
        worst |= sweep(repo, args.most)
    return worst


if __name__ == "__main__":
    sys.exit(main())
