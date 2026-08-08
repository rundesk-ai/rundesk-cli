"""What a command may exit with, and why each code means what it does.

A person reads the words. A script reads the number — and a script that reads the wrong number
carries on as though the work happened. So there are three answers and no others:

`OK` (0)      it was done.
`FAILED` (1)  it was attempted and did not work.
`USAGE` (2)   argparse's, reserved: the command line itself was wrong.

Every operation this command offers is built. There is no code for "registered but not written",
because there is nothing registered that is not written: a verb rundesk cannot perform is a verb
rundesk does not have.
"""

#: It was done.
OK = 0

#: It was attempted and did not work.
FAILED = 1

#: argparse's own, reserved: the command line itself was wrong. Never returned by hand.
USAGE = 2
