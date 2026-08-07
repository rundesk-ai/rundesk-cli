"""Running an agent's brain, and writing down what it did.

A provider is a **program rundesk runs**, never code it loads. rundesk hands it a turn through the
environment and its input, reads whole records off its output, and ends it when the turn is over —
so rundesk never puts a stranger's code inside the gateway that runs every other agent, an adapter
can be written in anything, and a brain nobody here has heard of is reached by exactly the seam a
shipped one is.

**No module in this package may name a vendor.** Every fact about a particular brain — its flags,
its stream shape, its session files, its permission model, its usage arithmetic — lives in one
executable file under `src/providers/` and appears nowhere else. `tests/test_providers_protocol.py`
checks that mechanically, because a rule of this kind stops being true quietly.

| Module | Answers |
|---|---|
| `protocol` | what an adapter may say, and what a turn's records add up to |
| `adapters` | the program behind a provider: finding it, asking what it can do, starting one |
| `environment` | everything an adapter is told about one turn, and the whole of it |
| `streaming` | one adapter that is running: the records off it, the words to it, and ending it |
| `instructions` | what a brain reads before it reads a word of the task |
| `team` | which specialists a turn may delegate to, with current skill names |
| `kept` | what an agent's records hold about its turns, and finding what was said |
| `turns` | one turn: the claim, what it resolved, what it ran, and how it settled |
| `answering` | what answers a message, and what starts a scheduled turn |

May depend on `skills`, `channels`, `schedules`, `agents`, `core` and `utils`. It reaches `channels` because a turn's answer
becomes a message, is cut to a platform's limit and has its files vetted — all of which already have
one home. The traffic goes one way only: **`channels` may not reach here**, so every channel case is
still drivable by a test with no brain anywhere near it.
"""
