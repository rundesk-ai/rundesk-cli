"""What a command may exit with, and why each code means what it does.

A person reads the words. A script reads the number — and a script that reads the wrong number
carries on as though the work happened. So there are four answers and no others:

`OK` (0)              it was done.
`FAILED` (1)          it was attempted and did not work.
`USAGE` (2)           argparse's, reserved: the command was typed wrongly.
`NOT_AVAILABLE` (69)  this operation is real, registered, and not built yet.

The last one is the one worth explaining, because it costs a constant to keep and it would be easy to
reach for one of the others. It cannot be `0`: the caller would read "done" for work that never
started. It cannot be `1`: that is a command that tried, and this one did not. And it must not be
argparse's `2`, because then a verb rundesk has not built yet and a verb rundesk has never heard of
answer identically — so a script cannot tell "coming in a later release" from "you have a typo". 69
is `EX_UNAVAILABLE` from the BSD conventions, which is exactly this.
"""

#: It was done.
OK = 0

#: It was attempted and did not work.
FAILED = 1

#: argparse's own, reserved: the command line itself was wrong. Never returned by hand.
USAGE = 2

#: Registered, planned, and not built yet — told apart from a typo on purpose.
NOT_AVAILABLE = 69
