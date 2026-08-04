"""Every operation the finished product will offer, registered from the outset.

The product is rebuilt one part at a time, which leaves a question the command has to answer well:
what does `rundesk agents list` do on the day agents have not been rebuilt? Three answers are wrong.
Saying nothing and exiting `0` tells a script the work happened. Failing as though it was attempted
tells a person their machine is broken. Answering argparse's usage error makes "not built yet" and
"you typed it wrongly" the same reply.

So every operation is **listed by the command from the outset**, accepts the arguments it will take
once built, names which part of itself is missing, points at something that does work, and exits
`NOT_AVAILABLE`. An entry leaves this table on the day its verb becomes real — which is the only
edit this file ever needs.

The surface below is the owner's, from `brief.md` at the repository root. It is copied into code once,
here, and read off the parser everywhere else.
"""

from typing import Dict, Tuple

#: verb -> (what it is for, {action -> what that action is for})
#:
#: An action is named here only where the verb has more than one, so a refusal can say which half is
#: missing. A verb whose actions are not yet settled carries an empty mapping and refuses by name.
PLANNED: Dict[str, Tuple[str, Dict[str, str]]] = {
    "agents": ("the named identities work is run for", {
        "list": "every agent on this install",
        "add": "make one, and say which brain answers for it",
        "configure": "change which brain answers for an agent",
        "remove": "take an agent away with everything that was its own",
    }),
    "messages": ("what an agent has been asked, and what it answered", {}),
    "schedules": ("work an agent starts because the time came", {
        "add": "state a time, and what to ask when it comes",
        "update": "change a schedule that is already stated",
        "run": "run one now, without waiting for its time",
        "show": "one schedule in full",
        "remove": "take a schedule away",
    }),
    "skills": ("the library of skills on this machine, and who is granted what", {
        "list": "every skill in the library",
        "catalogs": "the repositories skills were installed from",
        "install": "install a catalog of skills from a repository",
        "remove": "take a catalog away",
        "update": "bring a catalog up to what its repository publishes",
        "grant": "let one agent use one skill",
        "revoke": "take a grant back",
    }),
    "channels": ("the surfaces an agent is reached on", {
        "add": "put an agent on a channel",
        "update": "change who may reach an agent there",
        "show": "one channel in full",
        "remove": "take an agent off a channel",
    }),
    "backups": ("copies of everything the owner keeps", {
        "add": "make a copy now",
        "configure": "say whether copies are kept, and where",
    }),
    "env": ("the values every program rundesk starts is given", {
        "list": "which values exist, never what they are",
        "check": "whether one value is set and reachable",
        "set": "keep a value",
        "unset": "take a value away",
    }),
    "gateways": ("the long-lived process an agent works inside", {
        "start": "hand one to the machine to keep running",
        "stop": "end one, and everything it started",
        "restart": "cycle one without disturbing the rest",
        "logs": "what a gateway wrote about what happened",
    }),
}


def part_named(verb: str, given) -> str:
    """Which action of a verb was asked for, read off what was typed — or `""` when none was.

    A group is typed several ways: `skills list`, and `schedules <agent> add <name>`, where the
    action is not the first word. Rather than encode each group's shape before that group is
    designed, this looks for the first word that **is** one of the verb's declared actions. A word
    that names no action leaves the refusal naming the verb alone, which is honest: rundesk does not
    yet know what that word will mean.
    """
    actions = PLANNED.get(verb, ("", {}))[1]
    for word in given or []:
        if word in actions:
            return word
    return ""
