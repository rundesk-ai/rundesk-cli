# The channel system the previous build actually shipped

Established 2026-08-05 by reading the code: `src_old/channels/discord` (2363 lines),
`src_old/channels/slack` (2483 lines), `src_old/rundesk/{channel,answering,gateway,agent,store,
turn,attachment,transcript,activity,process,secret,welcome}.py`, `src_old/migrations/001.py`,
`src_old/rundesk/commands/channels.py` and `src_old/rundesk/cli.py`; then against
`docs_old/{discord,slack,configuration}.md`, `docs_old/extending/channel-adapters/` and
`.knowledge_old/prd/channel-*.md`. All of those trees are gitignored, reference-only and
expected to be deleted.

[`the-adapter-contracts.md`](the-adapter-contracts.md) already reproduces what that build
**promised** an adapter author, distilled from `docs_old/extending/`. **This page is the other
half: what the code did.** Where the two differ — and they differ in six places worth knowing —
§8 says so, and the code is what happened.

Two shipped adapters, and they are not one thing written twice. Discord came first and Slack was
written against the published contract afterwards; every place they diverge is a place a platform
could not do what the other could, and those divergences are the most useful part of the record.

---

## 1. The boundary

**An adapter was an executable file, started as a subprocess, held open for the life of the
gateway, speaking newline-delimited JSON over pipes.** Nothing was loaded, nothing was imported,
nothing bound a port.

Resolution is `channel.program()` (`channel.py:274-293`) and is exactly the provider rule: a name
with no path separator is looked for in `src/channels/`, anything else is used as a path; it must
exist and be executable or `NotRunnable` (`channel.py:266-293`). `ADAPTERS` is read by looking
rather than listed, "so one added later is reachable the day it lands and no second copy of the
list can come to disagree with the directory" (`channel.py:40-43`).

The gateway runs one asyncio task per channel (`gateway.py:1111-1120`), each a loop that starts
the program, waits for it to end, and starts it again (`gateway.py:1122-1181`). The spawn:

```python
outcome = await self.start(
    [str(one.program)], as_name=held, env=await self._for_a_channel(one),
    silence=None, ceiling=None, takes_input=True,
    sink=answering.heard,
    on_error=lambda said, name=one.name: channel_note(self.log, name, said))
```
— `gateway.py:1150-1160`. **`silence=None, ceiling=None` is the whole difference from every other
program rundesk starts**: providers get a 1800-second silence window and a 48-hour ceiling
(`process.py:73,79`), and a channel gets neither, because "an idle channel says nothing for hours
by design, and a clock that ends one is a clock that ends the thing a held-open surface exists
for" (`gateway.py:1147-1149`). `takes_input=True` opens stdin as a pipe rather than `/dev/null`
(`process.py:564`), and `start_new_session=True` makes the adapter a process-group leader
(`process.py:579`) so shutdown can signal the whole group.

### The wire, in both directions

**Adapter → rundesk, on stdout, one JSON object per line, flushed.** Six kinds and no more —
`ARRIVING = ("ready", "arrived", "control", "configure", "query", "gone")` (`channel.py:48`).
What each must carry (`channel.py:54-61`):

```python
NEEDED = {
    "ready": (),
    "arrived": ("conversation", "user", "text"),
    "control": ("conversation", "user", "control"),
    "configure": ("conversation", "user", "provider", "ref"),
    "query": ("conversation", "user", "query", "ref"),
    "gone": (),
}
```

`channel.understood()` (`channel.py:366-412`) parses one line and **never raises and never
refuses loudly**: an unreadable line, a non-object, an unknown kind, a known kind missing a
required field, a `control` outside `CONTROLS`, a `query` outside `QUERIES` all come back `None`,
meaning "keep the raw line, act on nothing" (`channel.py:373-378`). The raw line is still written
into the run's account as an `unknown` record, which is what makes adapter drift readable rather
than a silent gap.

The shapes, as the adapters really emit them:

```python
say(type="arrived", conversation=str(conversation), user=str(message.author.id),
    text=text, ref=str(message.id), direct=direct, attachments=brought,
    where=_place(message, direct, in_thread), called=_who(message),
    prompt_replaces=LEGACY_INSTRUCTIONS[DMS if direct else ROOMS],
    parts=_parts(message, direct, in_thread),
    **({"reply_to": reply} if (reply := _reply_to(message)) else {}),
    **_prompt_context(message, direct, in_thread))
```
— `discord:859-865`. And `say(type="control", conversation=str(interaction.channel_id),
user=str(interaction.user.id), control=gesture)` (`discord:585-586`); `say(type="query", …,
query=query, ref=ref)` (`discord:613-614`); `say(type="configure", …, provider=provider,
ref=ref)` (`discord:638-639`); `say(type="ready")` (`discord:672`); `say(type="gone", why=…)`
(`discord:2274`, `slack:2402-2403`).

**rundesk → adapter, on stdin, one JSON object per line, sorted keys.** `channel.spoken()` is one
line: `json.dumps(it, sort_keys=True) + "\n"` encoded UTF-8 (`channel.py:356-363`), "so the same
thing said twice is the same bytes and what crossed the seam can be compared with what was
shown". The kinds (`channel.py:203-204`):

```python
TELLING = ("state", "think", "tool", "result", "usage", "said", "answer",
           "configure-result", "query-result")
```

`TELLING` is **not the whole of what is sent**, and that is a real trap: `answering.py` also
emits `owner-notice` (`:627`, `:686`), `role` (`:731-732`) and `delegation` (`:828-829`) records,
none of which appear in that tuple. `TELLING` is a docstring-grade constant that drifted; the
adapters key off `told()`'s own if-chain (`discord:916-1020`) and never read it.

Records the adapter receives, verbatim from the code that builds them:

```python
{"type": "state", "conversation": …, "run": …, "state": "taken"|"running"|"finished"|"stopped"|"failed",
 "ref": …?, "why": …?, "can": {…}?}                          # answering.py:1363-1375
{"type": "think"|"tool"|"result"|"usage", "conversation": …, "run": …, …}  # answering.py:1477-1512
{"type": "said",   "conversation": …, "run": …, "text": …}   # answering.py:1539-1540
{"type": "answer", "conversation": …, "run": …, "provider": …, "text": …, "attachments": […]}
                                                             # answering.py:1317-1318
{"type": "role",   "conversation": …, "role_run": …, "state": …, "role": …, "label": …, "elapsed": …}
{"type": "delegation", "conversation": …, "delegation": …, "state": …, "to": …, "label": …}
{"type": "owner-notice", "text": …, "user": …?}
{"type": "query-result",  "conversation": …, "query": …, "ref": …, "text": …}
{"type": "configure-result", "conversation": …, "ref": …, "text": …}
```

**The exact field allowlist for the three streamed provider records** is
`_Shown.AS_IT_HAPPENS` (`answering.py:1477-1482`):

```python
AS_IT_HAPPENS = {
    "think":  ("text",),
    "tool":   ("id", "name", "did"),
    "result": ("id", "ok", "summary"),
    "usage":  ("input", "output", "cached", "written", "session", "model"),
}
```
Named rather than filtered, "so the default for anything new is that it stays" here and does not
cross the seam (`answering.py:1469-1476`). One narrow exception: a `who` accompanies a `tool`
whose `did` is `delegate`, and nowhere else (`answering.py:1505-1508`). `summary` is clipped to
200 characters (`answering.py:1487`, `:1509-1510`).

### Writing back

`answering.Answering` holds **one outbound queue and one writer task** (`answering.py:169-171`,
`_tell` at `:1377-1385`, `_show` at `:1387-1409`), "because a mark saying a turn is finished must
not overtake the answer it is finishing — and a record shown out of order is worse than one not
shown at all, since a reader has no way to tell." `_tell` is never awaited by the thing that
decided the record, so "a turn must not be held up by how fast a chat platform accepts writes."
A send that throws is logged and the turn continues (`answering.py:1405-1407`). The actual write
is `gateway._write_to` → `program.send(record)`, raising `process.NotListening` if the adapter is
not running (`gateway.py:1248-1253`, `process.py:877-920`).

Both adapters read stdin through `asyncio.connect_read_pipe` into a `StreamReader`, line at a
time; a non-JSON line is skipped, a `told()` that throws is noted on stderr and the loop
continues, and EOF means rundesk has stopped speaking (`discord:2286-2308`, `slack:2406-2428`).

**stderr is the adapter's own channel to the gateway log.** `note(said, level="WARNING")` writes
`f"{level}\t{said}\n"` (`discord:314-317`, `slack:344-347`); the gateway strips the marker and
logs each line **as it is said, not when the program ends**, because "a channel is held open for
weeks, so waiting for it to end before showing what it complained about is never showing it"
(`gateway.py:1154-1160`).

**Neither adapter is stdlib-only.** Discord imports `discord.py` and Slack imports `slack_sdk`,
both found by inserting the install's own `.venv/lib/python3.*/site-packages` onto `sys.path`
counted from the file's own location (`discord:43-63`, `slack:54-71`). The stated reason:
"Python's standard library has no websocket client, and a gateway connection cannot be held open
without one" (`discord:22-23`). The path was once written as `parents[3]` and stayed that way
after the adapters moved directory — "it looked for the virtualenv one directory *above* the
install, found nothing, and told an owner to run the installer that had already put `discord.py`
exactly where it belonged. Nothing failed until somebody added a channel" (`discord:48-52`).

---

## 2. Inbound

### From a platform event to an `arrived`

Discord's `on_message` (`discord:803-865`), in order: drop bot authors; drop a guild that is not
`--server`; work out `in_thread`, `ours` (thread `owner_id == self.user.id`), `mentioned`; ask
`where_to_answer()`; ask `within()`; **then** check `RUNDESK_ALLOW`; only then strip our own
mention, download attachments, open a thread if needed, and emit.

`where_to_answer` is five cases and is the whole routing policy (`discord:433-448`):

```python
if direct:        return "here"          # nobody else is here, and nowhere to put a thread
if ours:          return "here"          # a thread this agent opened is its conversation
if not mentioned: return "ignore"        # silence in a shared channel until named
if in_thread:     return "here"          # threads do not nest, so a named message stays put
return "open-thread"                     # named in a channel: the turn happens in a thread
```

`within()` is the owner's confinement (`discord:451-481`): a direct message needs `dms`; a room
message is compared against `--channel` **by the thread's `parent_id`, never its own id** —
"asked of the thread's own id, the restriction matched nothing and was skipped for every thread
in the server" (`discord:816-819`). A channel that named only DMs takes only DMs, and the
docstring records that this flipped twice before settling, with the measurement: "with `--dm` and
`--channel` both given, `within` returned true for the same message on both" (`discord:458-473`).

**The ordering of that method is a security decision with a cost attached** (`discord:823-834`):

> Nothing expensive or visible before this. Whether somebody may be answered is rundesk's to
> decide and it still decides it — but a message from anybody at all used to open a real thread
> and pull down as much as three hundred megabytes first, so any member of a shared server could
> make this agent litter their channel and fill a disk without ever being allowed to say a word
> to it.

Slack's `on_message` (`slack:889-978`) does the same shape with four extra platform guards:
`app_mention` is subscribed to and **deliberately dropped**, because a channel mention arrives on
both it and `message.channels` and taking both runs every turn twice (`slack:894-899`);
`IGNORED_SUBTYPES` drops joins, edits, deletions and bot messages (`slack:324-329`, `:900`);
its own user id and `bot_id` are dropped (`slack:902-903`); and a `ts` already in `self.seen` is
dropped as a redelivery beyond the envelope (`slack:933-934`).

### Conversation identity

`conversation` is the platform's own string and rundesk never parses it (`channel.py:351-355` of
the contract; enforced by the store, below). Discord uses the channel or thread snowflake
(`discord:839-842`). Slack has no thread object, so it composes one:
`conversation_of(channel, thread) -> f"{channel}:{thread}"` or the bare channel
(`slack:621-628`), split back with `where_of()` (`slack:631-635`), and the separator `IN = ":"`
carries the note that "Rundesk never parses this" (`slack:331-335`).

On the rundesk side that string becomes `store.conversation_id(channel, space, thread)` — a
**sha256 of `"\x00".join((channel, space, thread))` truncated to 16 hex characters**
(`store.py:235-249`). Derived rather than minted, "so two turns arriving in one Discord room,
weeks apart and from different processes, land on one conversation without either having asked
anything first"; hashed rather than joined, "because a separator is only unambiguous until one of
the three contains it".

### What travelled with the message

| field | who fills it | note |
|---|---|---|
| `conversation` | adapter | opaque; the session key |
| `user` | adapter | platform id, e.g. a Discord snowflake |
| `text` | adapter | **required to be present as a string** even when empty |
| `ref` | adapter | the message id a reaction attaches to |
| `direct` | adapter | `true`/`false` selects the standard instruction layer |
| `attachments` | adapter | `[{"name": …, "at": <absolute local path>}]` |
| `where` | adapter | one human phrase: `"#ops on the 'Acme' server"` |
| `called` | adapter | display name, not the id |
| `parts` | adapter | `{"channel": "#ops", "server": "Acme"}`, keys declared in `fills` |
| `reply_to` | adapter | `{"id", "resolved", "author"?, "text"?}` |
| `channel_{name,id,parent_name,parent_id,thread_name,thread_id}` | adapter | the platform-neutral six (`channel.py:112-115`) |
| `prompt_override` / `prompt_append` / `prompt_replaces` | adapter | instruction-layer hooks (`channel.py:103-108`) |

Everything a stranger typed is flattened and clipped on the way in: `plainly()` does
`" ".join(said.split())[:80]` (`channel.py:415-424`, `SAID_MOST` at `:162`) — "a newline, which
is how somebody would try to end our sentence and start one of their own, is not a character it
gets to have." `parts` keys must match `[a-z][a-z0-9_]{0,23}` and at most 8 survive
(`channel.py:583-594`). A quoted parent is clipped to 255 characters plus `...(truncated)`
(`channel.py:451-476`, `:167-168`). Attachments: at most 10, and **anything that is not an
absolute path to an existing file on this machine is silently dropped** (`channel.py:427-448`).

The prompt the brain sees is assembled by `_asked()` (`answering.py:1628-1662`) and is only what
the person typed, plus two appended blocks:

```
<what they typed>

Attached to this message, on this machine:
- report.csv: /Users/…/channels/discord-dms/attachments/1180/report.csv

--

This message replies to conversation message 8839 from Winston.
Quoted message: Nightly report…
```

**Where it was said does not go in the prompt.** That is stated as a defect that was fixed:
"Folded in, it arrived as part of what the person typed, so a brain could not tell rundesk's words
from theirs — and answered by reporting its own situation back to them as though they had asked
about it" (`answering.py:1636-1639`). Place and identity travel as `RUNDESK_PREFACE` instead, built
by `channel.preface()` from core + channel + adapter + owner layers (`channel.py:502-522`), with
`{agent}`, `{channel_where}`, `{user}`, `{where.channel}` and the rest filled by
`prompt_variables()` (`channel.py:525-563`).

### Who is allowed, and where it lives

**One function, one place, and never the adapter's** — `channel.allowed(record, user)` is
`user in record["allow"]`, and a record with an empty list authorizes nobody
(`channel.py:789-804`). It is asked of `arrived` (`answering.py:211`), of `control`
(`answering.py:994`) and of `query` (`answering.py:1051`). A refused message is dropped in
**silence**: "Answering a stranger to tell them they are a stranger confirms the agent is
listening and spends the owner's tokens doing it" (`answering.py:212-215`).

The adapters *also* check `RUNDESK_ALLOW`, and the docstrings are explicit that this is
**not** authorization but a refusal to work for somebody who cannot be answered
(`discord:830-834`, `slack:920-928`). A slash command from a disallowed user gets an ephemeral
"This command is not available to you." (`discord:571-575`) — added because "somebody this channel
does not allow typed `/restart` in a shared room and was told the agent was restarting — a promise
nothing kept, and a confirmation to a stranger that the agent is listening" (`discord:566-570`).

Storage: `channel.allow` is a JSON array in the per-agent SQLite `channel` table, `NOT NULL`
(`migrations/001.py:37`), written sorted and de-duplicated, and `remember_channel` raises on an
empty list (`store.py:785-825`). `allow_channel` does read-decide-write **inside one hold**
(`store.py:827-864`) so two concurrent owners cannot lose a change, refuses a `--remove` naming
somebody not already allowed, and refuses going down to nobody. **The owner is the first entry**
— `RUNDESK_ALLOW` is comma-joined in list order (`channel.py:336-341`) and both adapters take
`self.chose.allow[0]` as the person a hello, a goodbye and every owner notice go to
(`discord:754-760`, `slack:808-814`).

A second, tighter predicate exists for one gesture: `may_configure()` requires the allow-list to
be **exactly one person, and that person** (`channel.py:807-815`), because "a provider is an
agent-wide default, so membership in a shared room's allow-list is not authority to change it for
every channel and schedule."

---

## 3. Outbound

### The prose rule, which is the load-bearing design decision

**The adapter is never handed a part-written reply.** `text` is deliberately absent from
`TELLING` (`channel.py:194-196`): a brain writing its reply a fragment at a time is collected by
`_Shown._spoke` into `held.spoken` (`answering.py:1518-1542`) and handed over once as `answer`
(`answering.py:1301-1318`). "A reply that rewrites itself in place is unreadable, and the adapter
is never given the chance to try."

Between the two extremes sits `said`. A brain that marks a fragment `whole: true` gets each
previous whole remark posted as its own `said` record the moment the *next* one arrives — "which
is what makes the last one the answer, and is only knowable once there is a next"
(`answering.py:1518-1524`). So a brain that never says `whole` produces exactly one message per
turn, and a chatty one produces a running transcript, from the same code.

Order is fixed and the adapters depend on it: `taken` (with `ref`, no `run`, no `can`) →
`running` (with both) → activity → `answer` → `finished` (`answering.py:1175`, `:1285`,
`:1222-1224`).

### Chunking, limits and code blocks

| | Discord | Slack |
|---|---|---|
| message limit used | `LIMIT = 1900` (`discord:110`) | `LIMIT = 3800` (`slack:115`) |
| platform's own | 2000 | 4000 recommended, 40000 hard |
| attach instead of split past | `LIMIT * ATTACH_AFTER` = 5700 (`discord:170,1385`) | 11400 (`slack:168,1593`) |
| split rule | last `\n` before the limit, else hard cut (`discord:385-397`) | same, **unless that newline is before `limit // 2`** (`slack:412-432`) |

Slack's extra clause is a measured fix: the completion line, a newline, then thousands of
characters with nothing to break on "found the newline at character twenty and posted the
completion line entirely on its own, which is a notification saying nothing followed by the answer
somebody was waiting for — and the name the first piece carries went on the empty one"
(`slack:419-425`). **Discord still has the original rule.**

Code blocks are handled by *not* touching them on Discord and by an explicit fence-aware
translator on Slack. `to_mrkdwn()` escapes `&`, `<`, `>` in that order across the whole text
including fences (`slack:443-469`), then per line converts `[t](u)` → `<u|t>`, `**x**` → `*x*`,
`*x*` → `_x_`, and `# H` → `*H*`, parking inline-code spans and parked-bold in `\x00n\x00`
sentinels so the bold rule cannot read its own output back as italic (`slack:472-539`). Two
reasons given, and the second is the serious one: an agent that writes `<!channel>` while
explaining Slack's own syntax "sends a broadcast notification to everybody in the room. Nothing in
the turn asked for that and nothing in the room can tell it was not meant" (`slack:459-462`).

### The running commentary

Three modes — `grows`, `posts`, `off` (`discord:130-137`). `grows` edits **one** message and is
the default; `posts` starts a new message per batch; `off` shows none of it. Pacing is
`GROW_SECONDS = 1.2` for editing and `POST_SECONDS = 2.5` for posting, "Discord rate-limits
posting harder than editing" (`discord:124-128`); Slack cites "roughly one message per second per
channel with short bursts allowed" for the same numbers (`slack:117-123`).

`_flush()` (`discord:1244-1281`) grows only **while the commentary is still the last thing in the
conversation** — anything else being posted, or anybody speaking, calls `_no_longer_last()`
(`discord:1283-1303`) which clears `posted`, `activity`, `activity_groups`, the role and
delegation check-in maps, and **increments `held.writes`** so a post already in flight cannot
resurrect the buried message when it returns (`discord:1268-1276`). Commentary is bounded at
`ACTIVITY_CHARS = 1500` by dropping whole oldest groups and prefixing `-# …` (`discord:2000-2013`).
Adjacent identical lines collapse to `line **(xN)**` (`discord:1959-1997`).

Lines are broad and never carry arguments or results: `-# 📖 read file`, `-# 💻 ran command`,
`-# ⚠ command failed` (`discord:236-258`, `:301-305`, `:2016-2054`). Showing the brain's own
`name` was a recorded defect: "This showed `name` first, so a commentary read `commandExecution`
and `imageGeneration` — one vendor's identifiers, in front of somebody who has never heard of that
vendor and never should" (`discord:2022-2027`).

### The answer message

`_answer()` (`discord:1341-1399`, `slack:1541-1605`): stop typing, stop growing, build a footer
of `provider · <usage> · <elapsed>`, put it **above** the answer "because a long answer pushes
anything after it off a phone screen", split, attach past the ceiling, and mention the asker on
the first piece only.

Two platform facts fell out of this. Discord's mention comes free from `mention_author` on the
reply reference — **except for a scheduled report, whose anchor is rundesk's own notice, so
mentioning the reply author would ping the bot** (`discord:1543-1562`); core therefore ships
`recipient` on the answer, but only where the channel has exactly one allowed user
(`answering.py:402-405`). Slack has no reply-mention at all, so the adapter has to remember who
spoke: `held.asked_by = who` on every arrival (`slack:951-956`), because "an `answer` record says
what was said and what it cost, and never who asked — Discord does not need it… Read off the
answer record instead, this silently named nobody in every room, for every turn." **Neither
platform mentions anybody in a direct message** (`discord:1550-1557`, `slack:1575-1582`).

Slack additionally does **not** thread the answer in a DM: "In a direct message the question is
the message directly above the answer, so threading under it hides the reply behind a click and
buys nothing… what reads there as 'this is the one you asked' reads here as 'the answer is
somewhere else'" (`slack:1583-1590`).

### Attachments out

Three checks, in three places.

1. **The brain declares one** by writing an absolute local Markdown link, parsed by
   `attachment.declared_in()` with balanced-bracket handling and a `rundesk-attach:` reserved
   prefix (`attachment.py:108-168`).
2. **Core approves it** — `attachment.approved()` resolves the path, requires it under
   `workspace/`, `logs/` or `home/`, and fingerprints it by walking every path component with
   `O_NOFOLLOW` directory descriptors, refusing anything that is not a regular file, returning
   `{"name", "at", "bytes", "sha256"}` plus a `(st_dev, st_ino)` identity used to de-duplicate
   (`attachment.py:32-105`, `answering.py:1320-1361`). "The brain runs as the owner and can read
   anything they can, so 'the brain asked for it' is not on its own a reason to put a file into a
   chat room" (`answering.py:1325-1327`).
3. **The adapter verifies again and snapshots the bytes** — `_outbound_attachment()` re-walks the
   path with `O_NOFOLLOW`, streams into a `TemporaryFile`, and refuses if size or sha256 differ:
   `"could not attach {at}: file changed after validation"` (`discord:1587-1647`,
   `slack:1745-…`). That double check is what closes the window in which "a concurrent turn
   replaces an approved file or its parent between the check and the send."

Attachments in are downloaded by the adapter into
`$RUNDESK_CHANNEL_HOME/attachments/<message id>/`, renamed by `_plain_name()` (alnum, `-_.`,
last 120 chars) and de-collided by `_somewhere_new()` (`discord:352-378`, `:867-899`). The
de-collision is a recorded bug: "`report v2.csv` and `report-v2.csv` are both `report-v2.csv` —
so the second was written over the first, and the agent was handed two names that were one file.
It opened the right name and read the other one's contents" (`discord:362-368`). Slack needs the
bot token on the download because `url_private_download` "is not a public URL; without an
`Authorization` header it answers with the sign-in page, which downloads perfectly and is not the
file" (`slack:1158-1160`, `:1192-1203`).

---

## 4. Presence and affordances

**Rundesk decides the state; the adapter decides only how it looks.** Five states
(`channel.py:217-222`), rendered as reactions.

### Discord

| affordance | code |
|---|---|
| 👀 on `taken`, replaced by ✅ / ✋ / ⚠️ on the terminal state — one mark at a time | `discord:183-184`, `_react` at `:1121-1142`, `_state` at `:1064-1091` |
| a `⚠ <why>` subtext message posted before the ⚠️ mark | `discord:1088-1089` |
| typing indicator, renewed every 8 s inside Discord's ~10 s lapse | `discord:121`, `_typing` at `:1093-1119` |
| typing stopped when a `said` remark arrives, not only at the end | `_stop_typing` at `:1329-1339`, called at `:986` and `:1362` |
| online presence set on connect, cleared by closing the socket | `:659-665`, `:772-799` |
| `/stop` `/new` `/restart` slash commands, ack'd ephemerally inside 3 s | `:210-216`, `:562-587` |
| `/status /version /agents /skills /schedules /roles /delegations /help`, deferred ephemeral | `:221-230`, `:589-615` |
| `/provider <name>`, single-user channels only | `:617-640` |
| thread opened on being named; degrades to the channel if Discord refuses | `_open` at `:901-912` |
| answer quotes the asking message, only if in the same room | `_post` at `:1505-1522` |
| running commentary as one growing message | `:1244-1281` |
| role / delegation lines as their own messages, check-ins edited in place | `:1144-1212` |
| owner DM on gateway up, gateway down, update installed, skill granted, new user greeting | `:659-699`, `:740-770`, `:772-799`, `:927-939` |
| long answer attached as `answer.md` | `:1385-1389`, `:1533-1535` |

Two of these carry the whole scar of a bug. **`_react` prefers `it["ref"]` over `held.anchor`**
because "every message was made the anchor here, so a second one sent while a turn was still
running took the ✅ that belonged to the message that asked for it" (`discord:843-846`). And the
reply reference is built with `fail_if_not_exists=False`, because Discord refuses a whole message
quoting one it cannot resolve: "The asker deleting their question is enough, and a turn here runs
for minutes" (`discord:1536-1542`). The anchor guard itself once read `channel_id` off a
`discord.Message`, an attribute that does not exist — `getattr` returned `""`, the guard was true
of every message, and **every anchor there had ever been was dropped** (`discord:1510-1513`).

### Slack — the same seam, three affordances short

- **No typing indicator, at all.** `assistant.threads.setStatus` exists "but requires the
  Agents/AI Apps feature and forces a thread-only UI on every conversation — so a turn says it is
  working through the 👀 mark and the running commentary, and there is no indicator to renew"
  (`slack:22-26`). `_state`'s `running` branch is therefore literally `return` (`slack:1333-1334`).
- **No presence call.** `users.setPresence` is a user-token method; the manifest's
  `always_online: false` makes the green dot follow the socket, "which is this program's own
  lifetime and the one thing worth meaning" (`slack:26-28`).
- **No replace on a reaction**, so superseding is add-then-remove in that order, "so a turn is
  never momentarily unmarked" (`slack:1346-1365`). And `MARKS` holds reaction *names*
  (`white_check_mark`, `raised_hand`, `warning`) where Discord's holds glyphs (`slack:194-195`).
- **One slash command, not eleven.** "A slash command name is unique across a Slack workspace and
  the last app to register one wins it, so an agent that claimed `/stop` would take it from every
  other app and two Rundesk agents in one workspace could not both be reached." The name is the
  owner's `--command` and the gesture is its first word (`slack:210-215`, `on_command` at
  `:980-1041`). A word it does not know gets a usage message and reports nothing to rundesk —
  "turning a typed word into an argument is how a read-only surface becomes a command runner"
  (`slack:1038-1041`).
- **No subtext register.** `SUB = ""` — "Discord writes `-# ` and gets a quieter, smaller line;
  the nearest thing here is italics, and italicising a line that already carries an emoji reads as
  emphasis rather than as quiet. So the prefix is nothing at all and the mark carries the line"
  (`slack:263-268`).
- Private answers go through the slash command's `response_url` rather than a posted message:
  "that URL works for half an hour, needs no channel membership, and is what Slack gives a slash
  command precisely so an app can answer one privately" (`slack:1052-1058`, `:186-188`).
- A thread is "ours" by asking `conversations_replies` whether this app has spoken in it, cached
  per thread; the same call also yields the root message for `reply_to`, "asked separately, a busy
  thread cost two calls for every message in it" (`slack:1070-1099`).

### Once per gateway, not once per adapter

An agent reachable by DM and in rooms runs **two** adapter processes, so both would greet the
owner. Both adapters settle it on the filesystem: `_claim(what)` does
`os.open(marker, O_CREAT|O_EXCL|O_WRONLY, 0o600)` on
`$RUNDESK_HOME/.said-{online|offline}-{RUNDESK_GATEWAY}` and returns `False` on `FileExistsError`
(`discord:701-738`, `slack:760-793`). "Creating a file that must not already exist is one
operation the machine decides, so exactly one of them wins it." A machine that will not let it be
written answers `True` — "being told once too often is a smaller failure than never being told a
gateway came up at all." The marker is keyed on the gateway *lifetime*, so a reconnect stays quiet
and a real restart greets again. Goodbye is claimed separately, so an adapter that came up second
can still say it if it gets there first.

`ready` goes out on **every** connection; the greeting only on the first (`discord:666-672`,
`slack:729-745`), because "an owner told 'the gateway is up' after a blip is told about something
that did not happen, and there is no going-down message to pair it with."

---

## 5. Config and secrets

### The command surface

```
rundesk channels <agent>
rundesk channels <agent> add <channel> --kind <kind> --allow <user> [--allow …]
                                       [--token-stdin] [--activity | --no-activity]
                                       -- <adapter options…>
rundesk channels <agent> allow <channel> [--add <user>] [--remove <user>]
rundesk channels <agent> instructions <channel> [<text>]
rundesk channels <agent> show <channel>
rundesk channels <agent> remove <channel>
```
— `cli.py:868-941`. `--allow` is `required=True` with no default and no way to say "anybody":
"An agent that answers whoever speaks to it, on a machine where it runs tools, is a
misconfiguration and never a mode" (`cli.py:878-884`). Everything after `--` is carried to the
adapter unparsed (`cli.py:900-905`, `commands/channels.py:184`).

The verb is name-first (`add <channel> --kind <kind>`), and the guide records the earlier draft
that was `channels add <kind>` — "which made the slot after `add` mean the *type* on one verb and
the *name* on another."

### Adding a channel: check, then take a credential, then check again

`_add_channel` (`commands/channels.py:153-297`), in the order that is the requirement:

1. Refuse an empty `--allow` (`:161-170`).
2. Resolve the program (`:171-175`).
3. `mkdir` a working home under the *typed* name (`:179-180`).
4. Run `<program> --check <options…>` with a 60-second silence window and a 300-second ceiling
   (`channel.checked()` at `channel.py:747-778`, constants at `:257`, `:263`). The check's
   environment is **the owner's own shell plus the built one** — the one exception to the built
   environment, because an adapter being checked has not yet said which variable it reads
   (`channel.py:326-330`).
5. If it failed **and named a `secret`**, prompt once per named credential with `getpass` (or read
   one line each from stdin under `--token-stdin`), write each with `secret.write_private()`, and
   **check again** — "the credential being present is not the channel being reachable, and only
   the adapter can say which" (`:192-201`, `_took_a_secret` at `:93-139`).
6. Still not `ok` → print the adapter's own `why` and write nothing (`:202-207`).
7. Expand `shapes` into one channel per shape, name each `<typed>-<suffix>`, **validate every name
   and collision before writing any of them** (`:208-230`), then for each: make its own home,
   copy the credentials across, `remember_no_one_welcomed()`, `remember_channel()` (`:232-270`).

`--check` answers are read rather than trusted: `channel.answered()` coerces every field
(`channel.py:680-702`) and `channel.shaped()` drops a shape whose `suffix` is not
`[a-z0-9][a-z0-9-]{0,23}` or is a duplicate — "Two shapes of one name are one channel written
twice, and the second would silently replace the first — including who it said was allowed"
(`channel.py:705-744`, `SHAPES_MOST = 8` at `:152`).

Both shipped adapters report two shapes from one `add` (`wanted()` at `discord:2219-2228`,
`slack:2189-2199`): nothing said means both DMs and rooms; `--dm` alone leaves rooms out;
`--server`/`--channel` (Slack: `--workspace`/`--channel`) leave DMs out. So
`rundesk channels ava add discord --kind discord --allow 123…` writes `discord-dms` **and**
`discord-rooms`, each with its own allow-list and instructions.

### Where a token lived, and what "encrypted" meant

**Nothing was encrypted.** A channel credential is a plain file in the channel's private home,
mode `0600`, created with the mode rather than chmod'd afterwards, written beside and renamed into
place (`secret.write_private` at `secret.py:460-472`; the reason at
`commands/channels.py:131-137`: "a `write_text` narrowed by a `chmod` afterwards leaves a window in
which anybody on the machine can read it").

```
<data>/agents/<agent>/channels/<channel>/token        # channel.SECRET_FILE, channel.py:184
<data>/agents/<agent>/channels/<channel>/app-token    # slack:95
```

The record keeps only the **names**: `channel.secret` is `{"env": [...], "files": [...]}`
(`channel.named()` at `channel.py:621-639`, `kept_in()` at `:642-666`). `SECRET_FILE` moved from
`commands/channels.py` into `channel.py` for a stated reason worth carrying: "It was private to
`commands/channels.py`, so the name existed three times and agreed by luck: rundesk wrote `token`,
the Discord adapter declared `TOKEN_FILE = "token"`, and a stranger's adapter — given only the
contract, which states no name at all — hedged with two guesses. One of them is enough to make an
owner's channel silently deaf" (`channel.py:178-184`).

At runtime the adapter reads **the variable first, then the file**:

```python
said = os.environ.get(chose.token_from)
if said:
    return said.strip()
beside = Path(os.environ.get("RUNDESK_CHANNEL_HOME") or ".") / TOKEN_FILE
```
— `discord:335-349`, `slack:365-379`. Both places, because "a person adding your channel is at a
terminal with a variable exported, and the machine keeping an agent up has no terminal and no
shell profile, which is the state a channel spends its whole life in" (`discord:70-77`).

**The install-wide store is deliberately not allowed to satisfy a channel.** `Reachable`
carries `channel_secrets` — the names this adapter reads its own credential from — and
`gateway._for_a_channel` passes them as `exclude` to the secret resolver
(`agent.py:1222-1230`, `gateway.py:1242-1246`): "two agents may hold two different bots — one
install-wide value would make them the same bot, silently, with each record still naming a file
nobody read." Install-wide values are otherwise merged into the adapter's environment **at each
adapter start**, so replacing one takes effect on the next adapter restart rather than the next
machine restart (`gateway.py:1235-1240`).

### The environment an adapter actually receives

The contract names five variables. The code sets nine plus install-wide values:

| | from |
|---|---|
| `RUNDESK_CHANNEL`, `RUNDESK_AGENT`, `RUNDESK_AGENT_NAME`, `RUNDESK_CHANNEL_HOME`, `RUNDESK_ALLOW`, `RUNDESK_SETTINGS` | `channel.py:332-348` |
| `RUNDESK_HOME`, `RUNDESK_SCRIPTS`, `RUNDESK_SKILL_LIBRARY`, `PATH`, `HOME`, `TERM=dumb`, `LANG` | `process.py:1138-1154` |
| `RUNDESK_GATEWAY`, `RUNDESK_MAINTENANCE`, `RUNDESK_VERSION`, `RUNDESK_RELEASE_URL` | `gateway.py:1219-1234` |
| the one-or-more variables named in `secret` | `channel.py:349-352` |
| everything the install keeps, minus `channel_secrets` | `gateway.py:1246` |

`RUNDESK_SETTINGS` is always set, `{}` and all, sorted: "an adapter that believed it and reached
for the key rather than asking politely for it crashed the first time it was held open with
nothing configured — which is exactly the case the guide's own smallest example produces"
(`channel.py:342-348`). Both adapters use `RUNDESK_HOME` and `RUNDESK_GATEWAY` for `_claim`, and
`RUNDESK_MAINTENANCE` / `RUNDESK_VERSION` / `RUNDESK_RELEASE_URL` for the post-update greeting —
**none of which the published contract mentions**.

---

## 6. Lifecycle and failure

**Reconnection is the adapter's, restart is the gateway's, and they are deliberately different
grain.** `_hold_one` restarts an adapter that exited after `CHANNEL_AGAIN_SECONDS = 10.0`, "long
enough not to hammer a platform that is refusing us, short enough that an owner does not notice"
(`gateway.py:93-95`, `:1177-1181`). The docstring is clear about which is which: "An adapter
reconnects to its own platform far better than this can, because it knows what its platform's
backoff wants. This is what catches the case where it did not come back at all"
(`gateway.py:1125-1128`).

`gone` is **said and never acted on** — the connection state is noted in the log and a turn already
running is not interrupted (`answering.py:196-200`). `ready` sets `connected` and triggers
`_recover()` (`answering.py:191-195`).

### Crash recovery of in-flight turns

This is the part with the most machinery. On `ready`, once per `Answering` instance
(`answering.py:1115-1147`):

1. `store.recoverable(channel)` selects runs where `source = 'channel'`, this channel, that carry
   a `RECOVERABLE` marker record and no `RECOVERY_CLAIMED` one, oldest first
   (`store.py:1538-1556`).
2. `claim_recovery(run_id, at)` writes the claim under the store's single writer lock, returning
   `False` if already claimed (`store.py:1558-…`).
3. A turn is started with the fixed prompt `CONTINUE` (`answering.py:60-63`):

   > "Continue the interrupted work from where the previous gateway stopped. Do not repeat actions
   > already completed. Finish the original request."

   **It never replays the person's original prompt**, "because doing so can repeat tool effects
   that already happened before the restart."
4. It runs with `resume_required=True`, so a conversation with no saved provider session raises
   `CannotResume` rather than silently starting fresh (`answering.py:1200`, `turn.py:352-355`).
5. If that conversation already has a turn running, the recovery is refused and a `failed` state is
   sent naming why (`answering.py:1129-1139`).

### Steering, queueing and stopping

A second message during a running turn (`answering.py:961-985`): it is appended to
`held.waiting`, bounded at `WAITING = 4` — "somebody typing while an agent works is answering the
conversation, not queueing a batch of work, and an unbounded queue is a way to hand one person the
whole gateway" (`answering.py:38-42`). If the brain declared `steer: true` it is offered to the
running turn now; the offer is retained until the consumer confirms it was sent, because "the
running task can outlive the provider-input consumer during answer cleanup; putting words on that
dead consumer and forgetting them lost the message" (`answering.py:970-973`, `_offer` at
`:1287-1299`, `_saying` at `:1605-1625`).

`stop` cancels the turn **and drops the backlog** (`answering.py:1006-1028`):

> A turn ending promotes whatever queued behind it, and a cancelled turn ends like any other — so
> a stop drained the backlog instead of ending it and the agent carried on a second later with the
> next message, leaving no way to actually stop short of one stop per queued message, each racing
> the turn it had just started.

`forget` ends no turn but sets `held.forgotten`, and the session is forgotten *again* in the
turn's `finally` — "a turn already running will write down where it got to when it ends, and that
lands after this — so forgetting mid-turn was undone a few seconds later by the turn it
deliberately did not interrupt" (`answering.py:1029-1042`, `:1247-1251`). `restart` is the one
gesture aimed at the agent rather than the conversation, and is announced before it happens
"because the thing that would report it afterwards is the thing going away"
(`answering.py:997-1005`).

### Shutdown

`Answering.stop()` sets `_stopping` **before** cancelling anything and re-reads the running set up
to `_UNWINDING = 3` times, "because a turn ending schedules whatever was waiting behind it, from a
`finally` that runs during the cancelling — so a snapshot taken first and awaited afterwards missed
exactly the turn that shutdown created, and left a brain running for a channel already reported
gone" (`answering.py:1413-1441`). Then it drains the outbound queue, because "what was decided
before the end is still worth showing."

On the adapter side, `SIGTERM`/`SIGINT` are handled rather than fatal — "the default for these two
signals is to die immediately, so the goodbye, the presence going away and every last write were
simply never reached" (`discord:2255-2264`). The goodbye budget is `GOODBYE_SECONDS = 3.0` total
with `TELLING_SECONDS = 1.0` for the owner message, and the split is a bug fix:

> This had the whole goodbye budget to itself, so an owner who could not be reached — a fetch and a
> send, with the library's own rate-limit waits behind them — spent all of it and the close below
> was never reached at all. Discord then reaps it on its own schedule, and the bot goes on showing
> as online long after the gateway behind it has gone.
> — `discord:772-776`, `:152-159`

The gateway signals the whole process group and waits `GRACE_SECONDS = 5.0` before `SIGKILL`
(`process.py:68`, `:1013`).

### How failures showed up

- **Delivery failures never end the turn.** `_show` catches everything and writes
  `channel '<name>': could not show <type>: <why>` (`answering.py:1401-1407`).
- **The adapter's stderr goes to the agent's log as it happens**, prefixed with the channel name
  (`gateway.py:1154-1160`). Discord's `_read` originally wrapped `told()` in
  `suppress(Exception)`: "a report that never arrived left no trace at all, unlike a room that
  could not be found" (`discord:2302-2308`).
- **Success is logged too.** `_tell_the_owner` notes on success as well as failure, because "'It
  reported nothing' was read as 'it worked' for three restarts running, and the two are only the
  same thing when success has a line of its own" (`discord:767-770`).
- **A conversation id the platform cannot parse is a log line, not an exception.** `_where_to_write`
  guards `int()`: unguarded, "a report was lost and the log said nothing at all"
  (`discord:1425-1434`).
- **Slack redelivery.** Socket Mode replays what it was not acknowledged for, so the envelope is
  acknowledged *first*, on Slack's own thread, before anything else runs — "a turn run twice is a
  turn charged twice" (`slack:853-867`) — and `self.handled` de-duplicates envelope ids
  (`slack:869-878`) with `self.seen` as a second guard on `ts` (`slack:933-934`).
- **Everything the adapter holds is bounded** because the process runs for weeks: `SEEN_KEPT`,
  `LIVE_KEPT`, `THREADS_KEPT`, `NAMES_KEPT`, all 200 (`discord:174,179`, `slack:172-183`).
  `_make_room` drops idle conversations first and **cancels their typing and pacing tasks on the
  way out** — dropping the entry without cancelling left "the indicator going on renewing in that
  conversation for the rest of this process's life, which is weeks" (`discord:1305-1327`).
  `answering.py` bounds its own side at `CONVERSATIONS = 200`, dropping only idle ones, "where a
  conversation *got to* is in the agent's own record and is found again by name, so forgetting one
  here costs nothing at all" (`answering.py:50-56`, `:947-959`).

I did not find any explicit rate-limit backoff in either adapter. Both lean on the vendor library's
own handling and on the pacing constants; the old requirement rows for pacing are marked unproven
(`.knowledge_old/prd/channel-discord.md:39`, `channel-slack.md:66`).

---

## 7. Extensibility

**A published, versioned contract page, a conformance suite that takes the adapter as an argument,
and a stated promise that the page wins.** That is more than most projects offer and it was
genuinely load-bearing: Slack was added with no change under `src/rundesk/`.

The promise, quoted verbatim from `docs_old/extending/channel-adapters/references/the-contract.md`
(:690-697):

> **If your adapter follows this page and the suite still fails it, this page is wrong** — it is
> the contract, and the code is what has to move.

And the fidelity guarantee (`the-contract.md:441-445`):

> **Show what you have and skip what you have not.** There is no capability declaration to fill in.
> A surface with no reactions simply never marks anything; one with no typing indicator never
> types; one that cannot edit posts again instead. A turn completes anyway. Correctness never
> degrades — only fidelity — and the poorest surface there is, one that can only post text, is a
> first-class channel rather than a broken one.

And the forward-compatibility one (`:488-491`):

> **A record we do not recognise is kept, not refused.** Emit something new and it lands in the
> run's account verbatim. It will not be shown and it will not break anything — so you can be
> ahead of us without waiting for us.

The suite is invoked as `python3 tests/test_channel.py --adapter /path/to/your-adapter`
(`the-contract.md:673-688`), with a stated skip rather than a failure when the adapter's own
`--check` refuses. `.knowledge_old/CODEMAP.md:380` records 77 cases and "one adapter in
`strangers/` that this code never saw being written". The four hard limits imposed on a third
party: the closed `did` vocabulary, the closed `query` list, the closed `control` list, and
"do not implement your own allowlist; carry who spoke and let rundesk refuse."

**Three things undercut it in practice.**

- The documented `python3 tests/test_channel.py --adapter src/channels/discord` fails on a machine
  without the install's `.venv`, on the adapter's own honest `{"ok": false, "why": "discord.py is
  not installed…"}` refusal (`.knowledge_old/MEMORY.md:400-407`). The invitation extended to a
  stranger can fail for a reason the page does not name.
- The contract's closed `query` list is four words and the code's is eight (§8).
- Running an adapter by hand to diagnose it, while a gateway is already serving that channel, makes
  one of the two silently stop receiving with no error on either side
  (`docs_old/extending/channel-adapters/README.md:122-126`).

---

## 8. Where the code and the old docs disagree

Six of these matter to anyone re-implementing from the contract page rather than from the code.

1. **`text` is mandatory on the wire even when empty.** `NEEDED["arrived"]` includes `"text"`
   and `understood()` requires `isinstance(it.get("text"), str)` (`channel.py:56`, `:388-389`);
   only the *emptiness* is excused, and only when attachments are present (`:404-405`). The
   contract's own table lists `text` under "may have" (`the-contract.md:126`). **An adapter that
   omits the key for a photo-only message has its message silently dropped.**
2. **The `query` vocabulary is eight words, not four.** Code:
   `(status, version, agents, skills, schedules, roles, delegations, help)` (`channel.py:240-248`),
   and both adapters offer all eight (`discord:221-230`, `slack:232-241`). The contract says
   "The closed list is `status`, `version`, `agents`, and `help`" (`the-contract.md:150-151`).
   A third party following the page would never offer four of them.
3. **`secret.env` may be a list, and the contract only ever shows a string.**
   `channel.named()` accepts either (`channel.py:628-639`), `kept_in()` derives a file per
   credential (`:642-677`), and Slack needs two (`slack:2237-2242`). The contract is singular
   throughout ("The one variable you named in `secret` is set too").
4. **The environment is nine variables plus install secrets, not five** (§5). Both shipped
   adapters read `RUNDESK_HOME` and `RUNDESK_GATEWAY`, which appear nowhere in the contract.
5. **The user-visible gesture is `new`; the wire word is `forget`.** `CONTROL_COMMANDS` maps
   `("new", …, "forget", …)` (`discord:212-213`, `slack:223-224`).
6. **`--activity` / `--no-activity` is a real, documented-nowhere flag** (`cli.py:897-899`), and
   the adapters carry dead code for its third value. `--activity` on the adapter only accepts
   `grows|posts` (`discord:327-328`), and `settled()` skips a stored `off` and defaults to `grows`
   (`discord:2335-2349`), so `chose.activity` is never `OFF` at runtime and the
   `if self.chose.activity == OFF: return` in `_doing` (`discord:1225-1226`) is unreachable. That
   too is a bug fix left in place: for a while there were "two defaults for one idea, and the one
   further from the owner won: an owner who never said anything got a channel rundesk was
   streaming activity to and an adapter dropping every line of it, so nothing ever appeared and
   nothing said why" (`discord:2339-2346`).

One I could not settle: the old `docs_old/slack.md:172` shows
`rundesk channels ava allow slack-dms U01ABCDEF2G U03HIJKLM4N` — a positional replacement list the
parser does not accept (`cli.py:915-926`). The generated `old/CLI.md:33` agrees with the parser, so
the Slack page is very probably stale, but I did not run anything to prove it.

---

## 9. The old schema against `brief.md`

The old build's per-agent `state.db` (`migrations/001.py`) versus what `brief.md` proposes.

### `channel` → `channels`

```sql
CREATE TABLE channel (
    name TEXT PRIMARY KEY, kind TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
    provider TEXT, model TEXT, instructions TEXT,
    allow TEXT NOT NULL, secret TEXT, settings TEXT NOT NULL DEFAULT '{}',
    describes TEXT, fills TEXT NOT NULL DEFAULT '[]', activity INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
) STRICT;
```
— `migrations/001.py:28-44`.

| old | `brief.md` `channels` | note |
|---|---|---|
| `name` (PK) | `key` (PK) | same role |
| `kind` | — | **gone.** The old build could not resolve an adapter without it; `brief.md` may be folding kind into `key` |
| `allow` (JSON array, first entry is the owner) | `owner_id` + `allowed` (JSON) | **the owner is promoted out of the list.** That removes the `allow[0]` convention and `may_configure`'s "exactly one allowed user" hack (`channel.py:807-815`) |
| `secret` (JSON `{env:[…], files:[…]}`) | `secrets` (JSON) | same shape presumably |
| `settings` | `settings` | same |
| `provider`/`model`/`instructions` | same three | old ones were per-channel fallbacks; only `instructions` was ever settable (`store.py:866-872`) |
| `enabled` | — | **gone.** Nothing in the old code ever wrote `0`; `channels(enabled_only=True)` existed and was unused by the gateway, which reads all of them (`agent.py:1244`) |
| `describes` | — | **gone.** This was `--check`'s one-line answer, shown by `channels show`/`list` (`commands/channels.py:492`, `:517`) |
| `fills` | — | **gone.** This is what made `{where.channel}` refusable *when written* rather than silently blank at every turn (`channel.py:597-618`) |
| `activity` | — | **gone.** The per-channel "show the turn while it runs" switch (`answering.py:1514-1516`) |
| `created_at` | `created_at` | same |

### `conversation` → `conversations`

```sql
CREATE TABLE conversation (
    id TEXT PRIMARY KEY, channel TEXT NOT NULL, kind TEXT NOT NULL,
    space TEXT NOT NULL, thread TEXT NOT NULL DEFAULT '',
    parent_id TEXT REFERENCES conversation(id),
    opened_at TEXT NOT NULL, last_at TEXT NOT NULL,
    UNIQUE (channel, space, thread)
) STRICT;
CREATE INDEX conversation_in_space ON conversation(channel, space, last_at);
```
— `migrations/001.py:91-106`.

`brief.md` proposes `id (int PK)`, `source`, `source_id`, `channel`, `created_at`, `last_at`.

- **The id changes from a derived hash to an autoincrement integer.** The old id was
  `sha256(channel\0space\0thread)[:16]` precisely so that "two turns arriving in one Discord room,
  weeks apart and from different processes, land on one conversation without either having asked
  anything first" (`store.py:235-249`). An integer PK needs the `UNIQUE (source, source_id)`
  lookup to do the same work; `brief.md` declares no such constraint.
- **`space`/`thread` collapse into `source_id`.** In practice the old build never used `thread`:
  `turn.carry` calls `kept.opened(conversation_id(on, conversation), on, kind, conversation, …)`
  with no `thread` argument, so it is always `""` (`turn.py:347-348`, `store.py:1212`). Slack
  encoded its thread into the `space` string instead (`slack:621-628`). **`thread` and `parent_id`
  were dead columns**, and `parent_id` says so in its own comment ("No adapter reports one yet, so
  nothing sets it").
- **`source` moves from `run` to `conversation`.** In the old schema `source` was on the run
  (`'channel' | 'terminal' | 'schedule'`, `migrations/001.py:131`, `turn.py:377`) while the
  conversation carried `kind` (the adapter kind). `brief.md`'s enum
  `'channel'|'schedule'|'terminal'|'agent'|'role'` is broader and lives one level up. That is a
  real improvement for the case the old build handled with a pseudo-surface — a scheduled turn's
  conversation "is on a pseudo-surface that joins no channel", which is why
  `announces_into`/`announces_as` exist as a pair to translate between rundesk's id and the
  platform's word (`store.py:252-296`).

### `message` → `conversation_messages`

```sql
CREATE TABLE message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    run_id TEXT REFERENCES run(id),
    external_id TEXT, at TEXT NOT NULL,
    author TEXT NOT NULL, who TEXT, text TEXT NOT NULL
) STRICT;
CREATE UNIQUE INDEX message_once ON message(conversation_id, external_id)
    WHERE external_id IS NOT NULL;
```
— `migrations/001.py:158-176`.

- `author` ∈ `agent | user | rundesk` in both; `who` is `brief.md`'s `author_id`; `text` is `body`.
- **`external_id` and its partial unique index are gone from `brief.md`.** That index was the
  idempotency guard — "what makes work arriving twice from one surface recorded once… enforced by
  `message_once` rather than by anything remembering to check" — and its own comment admits **no
  adapter ever passed one through the seam** (`migrations/001.py:162-165`). It was a correct
  mechanism that nothing used. Slack instead re-implemented de-duplication in adapter memory
  (`slack:869-878`, `:933-934`), which does not survive a restart.
- FTS5 is external-content in both, with three sync triggers, asked for rather than assumed
  because "FTS5 is a compile-time option rather than a guarantee" (`migrations/001.py:190-200`).

### One structural change worth naming

The old build had **no migrations table** — `PRAGMA user_version`, stamped inside the same
transaction as the step. `brief.md` proposes a `migrations (key, completed_at)` table. That is a
deliberate reversal; the reasons for either are in
[`2026-07-26-sqlite-store-and-migrations.md`](2026-07-26-sqlite-store-and-migrations.md) and are
not this page's to argue.

---

## 10. Verdict

### What was right, and is cheap to keep

- **The adapter as a program, not a plugin.** It bought a second platform with zero core change,
  and it means a third party's bug cannot reach the gateway running every other agent. Nothing
  in the two adapters imports rundesk; nothing in rundesk imports them.
- **Authorization in exactly one function, asked of the record.** `channel.allowed()` is nine
  lines and is the whole of it. A stranger's adapter is safe "because of where this decision
  lives rather than because of how carefully it was written" (`channel.py:793-796`). Silence
  rather than refusal for a stranger is the right default and cost nothing to implement.
- **Rundesk owns the turn's state; the adapter owns only its appearance.** Five states, decided
  once, in a fixed order, with `taken` first and alone. Every alternative ends with two surfaces
  disagreeing about one run.
- **Prose is held and handed over whole.** This is the single best decision in the whole system.
  It makes "post half a sentence" structurally impossible rather than merely discouraged, it
  removes a whole class of edit-storm rate-limit problems, and `said`/`whole` gives a chatty brain
  a live feel without ever exposing a fragment.
- **A field allowlist on the way out.** `_Shown.AS_IT_HAPPENS` means a vendor adding a key next
  year does not post a command's full output into somebody's room. The default for anything new
  is that it stays here.
- **`--check` before anything is written, and the credential taken between two checks.** "An
  agent whose channel is misconfigured must find out while somebody is typing the command, not at
  three in the morning."
- **`shapes`: one `add`, several channels, one allow-list each.** The reasoning is airtight — "the
  people who may speak to an agent in a public room are not the people who may speak to it in
  private" — and the measurement behind it is recorded: with `--dm` and `--channel` both given,
  one message matched both channels and was answered twice by two processes
  (`discord:465-469`).
- **Everything bounded, because the process runs for weeks.** Every map in both adapters is
  capped, and `_make_room` cancels what it drops.
- **`_claim` on the filesystem** for once-per-gateway messages. Two processes, one `O_EXCL`, no
  coordination protocol.
- **The double-verified outbound attachment.** Approve with a fingerprint, then re-open with
  `O_NOFOLLOW` and compare size and digest before sending the snapshot. That is the correct shape
  for a TOCTOU boundary and is worth copying verbatim.

### What was structurally wrong or painful

- **Two vendor libraries, in a stdlib-only product.** `discord.py` and `slack_sdk` are pinned in
  `requirements.txt`, installed into the install's own virtualenv, and found by a
  `sys.path.insert` counted from the adapter file's location. That path was wrong for a whole
  release and "nothing failed until somebody added a channel" (`discord:48-52`). The install-time
  coupling also breaks the documented conformance invitation for a stranger.
- **`answering.py` is 1669 lines and knows about far too much.** It is the only module that knows
  `channel`, `turn` and `agent` all exist — which is defensible — but it also carries role runs,
  delegations, schedule notices, post-update continuations, restart handshakes, welcome turns and
  gateway queries. Six of its nine public methods are `told_*` callbacks for subsystems that have
  nothing to do with a channel.
- **Two live representations of a conversation that must not drift.** `answering.Exchange` and the
  adapter's `Live` both track the same turn, in two processes, and the bugs are exactly where you
  would predict: the anchor stealing the ✅, the commentary growing into a buried message, the
  typing indicator surviving its conversation's eviction, `held.writes` existing only to
  invalidate a write in flight.
- **The adapter reconstructs state the seam already has.** Slack keeps `held.asked_by` because the
  `answer` record does not say who asked (`slack:951-956`); Discord keeps `self.started[schedule]`
  because the pairing of a start notice and a report is left to the adapter. Both are things
  rundesk knew and did not send.
- **Nothing correlated in the adapter survives its turn.** `_state`'s terminal branch does
  `self.live.pop(conversation)` (`discord:1091`), and `told()` re-creates a fresh `Live` for the
  next record (`discord:953`). Role and delegation records explicitly outlive turns, so their
  check-in edit-in-place resets every time a turn ends in that room.
- **Allow-list changes need a restart.** The adapter is handed `RUNDESK_ALLOW` at start-up, so
  `channels allow --add` prints "in effect when the channel next starts" (`commands/channels.py:
  392-399`). Core still enforces correctly, but a newly allowed person is invisible to the adapter
  and their greeting waits for the same moment.
- **Instruction changes need a *new conversation*, not a restart.** Measured against a real brain:
  "the same instruction was obeyed at the start of a thread and ignored on every resume after"
  (`commands/channels.py:438-444`). The command says so; nothing enforces it.
- **`kind`, `describes`, `fills`, `activity` and `enabled` were five columns for what is really
  "what the check said" plus "one switch", and `thread`, `parent_id` and `external_id` were three
  columns nothing ever wrote.** The last is the worst kind: a correct idempotency mechanism that no
  adapter used, so both platforms re-solved de-duplication in process memory instead.
- **The contract page and the code drifted in six places** (§8), and the page is the thing a third
  party reads. The stated remedy — "if your adapter follows this page and the suite fails, the page
  is what moves" — is only true if somebody notices the divergence, and nothing noticed these.
- **`TELLING` is a lie by omission.** Three record kinds are sent that it does not list. It is read
  by nothing, which is exactly why it rotted.
- **Reconnection was never proved.** Both `R-CAD-6` (channels held open by the gateway) and
  `R-CAD-7` (a channel that drops its connection returns without a turn noticing) are marked ❌ in
  the old requirement list — "a turn surviving a drop is proved, **the adapter coming back on its
  own is not**" (`.knowledge_old/prd/channel-adapter.md:29-30`). Everything in §6 above about
  reconnection is code that was written and reasoned about, not behaviour that was measured.
