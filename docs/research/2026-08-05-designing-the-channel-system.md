# Designing the channel system: what is settled, what is open, and the options

**Written 2026-08-05**, before anything is built. This is a proposal page, not a description of
anything that runs — nothing in it is a guarantee and nothing in `docs/` should cite it.

It sits on three things established the same day:

- [`the-adapter-contracts.md`](the-adapter-contracts.md) — the channel adapter contract as the
  previous build defined it, already distilled and treated here as **the contract of record**.
- [`2026-08-05-the-old-builds-channel-system.md`](2026-08-05-the-old-builds-channel-system.md) — what
  the previous build's two adapters and their seam actually did, with the incidents attached.
- [`2026-08-05-how-other-gateways-do-channels.md`](2026-08-05-how-other-gateways-do-channels.md) —
  OpenClaw, Hermes, Matterbridge, Matrix/mautrix, Zulip, Apprise, Home Assistant.

---

## The finding that reframes the question

**A channel adapter contract already exists and it is largely right.** The evidence is not an opinion
about it: **Slack was added to the previous build with zero change under `src/rundesk/`.** A seam that
absorbs a second platform without moving is a seam that works.

So this is not a design from nothing. It is an evaluation, and it has three gaps.

| | Settled by the existing contract | Gap |
|---|---|---|
| **Reusability** | adapter is a program, not a plugin; NDJSON over pipes; rundesk owns turn state, the adapter owns only appearance; fidelity degrades, correctness never does | no capability declaration, so the core cannot decide to stream or to buffer, and cannot split text in one place |
| **Unprompted outbound** | — | **every record on the wire is turn-shaped.** There is no way to say "post this, nobody asked" |
| **Identity** | — | there is no person. There is a per-channel opaque `user` and an allow-list of them |

Everything below is those three.

---

## 0 · The transport problem, which decides the order of the work

**Discord inbound is the one thing on this page that stdlib Python cannot reach, and it has to be
answered before anything else is planned.**

- Discord's gateway is **WebSocket only**, and the standard library has no WebSocket client.
- The documented alternative — an HTTP **Interactions** endpoint — needs **Ed25519 request signature
  verification, which CPython's standard library does not provide**, and a **publicly reachable
  URL**, which a gateway running on somebody's Mac does not have.

Everything else is reachable: outbound is nearly free everywhere; email is `imaplib`/`smtplib`;
Telegram is `getUpdates` long-polling; Slack has Events-over-HTTP. **Discord — the platform this is
being built for first — is the single hardest case in the set.**

Three ways out, and this is a decision rather than a detail:

**A · Write a WebSocket client on stdlib primitives, inside the adapter.** RFC 6455 framing over
`socket` + `ssl`, with `zlib` for Discord's compression and `hashlib`/`base64`/`secrets` for the
handshake — every piece is in the standard library, and the client is on the order of a few hundred
lines. Keeps the empty `requirements.txt`. Costs a hand-written protocol implementation that has to
survive reconnects, and **reconnection was never proved in the old build** — both of its own
requirement rows are still ❌.

**B · Let an adapter have dependencies, because an adapter is not rundesk.** The old build did this:
`discord.py` and `slack_sdk` from a virtualenv, found by counting parent directories — *and the count
was wrong for a whole release, with "nothing failing until somebody added a channel."* The product's
`requirements.txt` stays empty; the adapter's does not. This needs a real answer for how a shipped
adapter gets its library onto a machine.

**C · Ship Discord as an adapter that is not installed by default**, leaving the contract, the core
and a stdlib-reachable channel (email, or Slack over Events) as what the first release proves.

The seam is what makes any of these possible — a vendor library lives on the far side of it and never
enters the gateway. **That is no longer just an argument for adapter-as-program; on this platform it
is the only reason the stdlib-only rule and Discord can both hold.**

---

## 1 · Reusability — keep the seam, change three things

### Keep: the adapter is a program

Not a plugin, and the reasons compound. Rundesk never loads a stranger's code into the gateway
running every other agent. An adapter author is not obliged to write Python. And **the two vendor
libraries the old build needed — `discord.py`, `slack_sdk` — stay on the far side of the seam**,
which is the only way a stdlib-only product can talk to Discord at all. That is not a workaround; it
is the same decision the provider layer already made, and the channel seam should mirror it exactly.

The comparison confirms it from the other side. Every in-process design surveyed (OpenClaw, Hermes,
Errbot, Rasa) buys convenience and pays with the core's own stability, and OpenClaw's own security
page concedes the model: *"This guidance assumes one trusted operator boundary per gateway."*

### Change one: declare capability, and make "can it stream" computed rather than stated

The current contract deliberately has none — *"Show what you have and skip what you have not."* That
is right for **fidelity** and wrong for **fan-out**, and the old build shows the cost twice:

- Discord's limit is `1900` and Slack's is `3800`, each held in its own adapter. **Slack fixed a
  splitting bug — a completion line alone in its own message, carrying the mention — and Discord
  still has the original rule.** Two copies of one rule is how that happens.
- `--activity`/`--no-activity` exists to fix an earlier state where *"two defaults for one idea"* had
  core streaming activity while the adapter dropped every line, silently.

Take the shape from mautrix `RoomFeatures`, which is the best answer found anywhere, and take two
ideas from it rather than the whole thing:

**A support level is five-valued, not boolean** — `rejected` (I will refuse and error), `dropped`
(I will accept and silently discard), `unsupported`, `partial`, `full`. Matterbridge's entire failure
mode is that everything is implicitly *dropped* with no way to find out. A boolean cannot express the
difference between refusing loudly and dropping quietly, and that difference is what lets the core
decide whether to degrade or to fail.

**Quantitative caps sit beside the levels** — `max_text`, `edit_max_count`. Then the question this
whole system turns on is *computed*:

> **"Can this channel stream?" is not a flag. It is `edit >= partial and edit_max_count > n`.**

Email declares `edit: unsupported` and the same core path collapses to one send. Discord DM declares
`edit: full` and gets live editing. **The core owns the degradation; the adapter only owns the truth
about itself.** And splitting moves into core, once.

Asked the way the provider contract already asks: run with `--capabilities`, print one JSON object,
exit `0`. Absent fields mean the least capable answer, so `{}` is a valid and complete adapter.

**Pair it with Rasa's flattening default.** Only "send text" is mandatory; every richer thing has a
default that projects down to text. Declared gets the rich path, undeclared gets an automatic lossy
one, and **there is no `if channel == "email"` anywhere in the core** — which is the whole test of
whether this abstraction earned its place.

**Capability is `f(adapter, destination, identity_state)`, not `f(adapter)`.** mautrix's relay mode
drops reactions entirely for unlinked users, because the bot cannot attribute them. That couples this
section to §2 and is the reason the capability answer takes a place rather than being read once at
startup.

### Change one-and-a-half: a send result, not a boolean

Hermes returns `SendResult(success, message_id, error_kind, retry_after, continuation_message_ids)`.
Two things a boolean loses and both matter here: **`retry_after` makes rate-limiting contractual**
rather than something each adapter re-invents, and **`continuation_message_ids` admits that one reply
becomes N platform messages** — which is exactly what splitting produces. OpenClaw adds the two
outcomes a boolean also loses: `suppressed` ("no platform message, and that is not a failure") and
`partial_failed` ("some landed before a later one did not").

*The honest counter-argument:* this is machinery for a product with one adapter. The floor that earns
its place on day one is `max_text` plus the streaming pair — three fields. The five-valued vocabulary
should be there from the first line even so, because a boolean that later needs a third state is a
migration on every install.

### Change two: a record for outbound nobody asked for

Every stdin record in the contract is scoped to a `conversation` and a `run`. There is no way to
deliver something unprompted. The old build hit this and hacked around it: `owner-notice` was sent on
the wire but **was never added to the `TELLING` constant that documents what is sent**, which nothing
read and which rotted.

This is the load-bearing gap for *"every morning, email me the daily report"*, and for gateway
up/down notices, and for delegation reports. One new record kind — a delivery carrying a place, a
body and an id, acknowledged by the adapter with the platform's own message id.

The schedules table **already carries `channel` and `channel_place_id`**, added unwritten in step
`0002` for exactly this. Nothing about an agent's records has to move.

### Change three: a durable outbox

Today a send that fails is logged and the turn carries on. For a reply that is arguable. For the
daily report it is not: the adapter may be reconnecting, rate-limited, or inside its ten-second
restart. Recommend an `outbox` table in the agent's own records, drained by the gateway, acknowledged
by the adapter.

That also finally gives `external_id` a writer. The old build **had the column and its partial unique
index and no adapter ever passed one through the seam** — its own comment admits it. A correct
idempotency guard that nothing used, while Slack re-solved de-duplication in adapter memory that does
not survive a restart.

---

## 2 · Identity — the genuinely hard part, and nobody has shipped it well

Calibration first, because it decides how much machinery is justified:

- **OpenClaw** has a hand-edited config map, `identityLinks: { alice: ["telegram:123", "discord:987"] }`.
  It is a session-routing device, not a person record — it buys shared conversation continuity and
  cannot answer *"what is Tim's email address"*. It is populated by hand with no verification, and it
  is **separate from authorization**, so the same human is listed twice, in two places, in two
  formats. A third party had to ship an "identity-resolver skill" to fill the gap.
- **Home Assistant** *has* a person integration and has spent two years failing to wire it into
  `notify`. There is an `ATTR_RECIPIENTS` constant with no consumer.
- **Matrix/mautrix** is the only one that really has it — and pays with an appservice, a registration
  file, homeserver admin, and a class of silent failure.

> **We want Matrix's tables, not Matrix's machinery.**

### The options

**A · No person record.** Owner is `allow[0]`, per channel, as the old build did. Cheapest, and it
already produced two hacks that are still visible: the `allow[0]` convention, and `may_configure()`
meaning *"the allow list has exactly one entry and it is them"*. Fails every one of the owner's
stated cases.

**B · `people` + `handles`, per agent.** One human, many per-channel addresses; authorization moves
onto the person. This is mautrix's `UserLogin` shape — *one real human → many remote logins* — and it
is literally the requirement. Consistent with everything else here being per-agent, and it keeps the
stated invariant that an agent whose records cannot be read is *one* agent that cannot be read.

**C · B, but install-wide.** Tim is Tim across agents and is typed once. Buys convenience, costs the
per-agent isolation and puts a second writer on a file every agent needs.

**Recommended: B.** The concrete shape, with mautrix's ghost idea folded in as a nullable column
rather than a second table:

```sql
people          (id, name, display_name, is_owner)
people_handles  (id, person_id NULL, channel, remote_id, handle, email, verified_at,
                 UNIQUE (channel, remote_id))
```

- **`person_id IS NULL` is a ghost** — somebody who has spoken and is not linked to anyone. That is
  one nullable column instead of the whole puppet/user split.
- **`remote_id` is the provider-issued immutable id, and it is the ACL key.** Never the display name,
  never the handle — both of those are things a stranger can change to match somebody else's.
- **Capture `email` at link time.** It is the only plausible cross-channel join key, and it is the
  field that makes "email me the daily report" resolvable at all for a person first met on Discord.

### Two rules that are not optional

**Linking is proven, never inferred.** Matterbridge tried to infer ownership from display names and
produced `{NOPINGNICK}`. Two ways in, and both should exist:

- `rundesk people link` at a terminal — explicit, for an owner who has the ids.
- **a claim code** — `rundesk people claim` prints a short expiring code, you DM it to the bot from
  the new channel, and the handle is linked and marked verified. This is OpenClaw's `dmPolicy:
  pairing` turned into the linking mechanism, and it is the answer to *"make it easy"*: nobody has to
  look up a Slack member id.

**Every addressable destination is a registry row with a stable id.** Home Assistant's lesson,
verbatim: *an entity id is a primary key you can join on, log against and authorize; a URI is a value,
not a key.* So **not** Apprise-style `discord://channel_id` strings. Rows.

A third authorization state is worth one column, from mautrix: **`relay` — "I know who you are well
enough to carry your text, but not well enough to attribute it."** That is exactly what an unlinked
human in a public room is, and it is the state they are in before they claim.

### Addressing, three layers

| Form | Meaning | When |
|---|---|---|
| **here** | the conversation's own place | ~95% of everything, and it costs nothing |
| **a place** | a row: this room, this thread, this DM | "post the report in #ops" |
| **a person on a channel** | resolved through handles **at send time** | "email me the daily report" |

Send time, not set time — so a schedule saying *email Tim* survives Tim changing his address.

---

## 3 · Setup — one bot per agent, and the credential never enters `data/`

**One Discord application per agent is forced, not a preference.** One bot is one identity and one
presence. Two agents behind one bot receive the same messages and nobody can tell which one replied.
The nice version of the same constraint: every agent gets its own name and avatar.

### The correction that matters most

`brief.md` gives the `channels` table a `secrets (json)` column. **A credential may not live there.**
`core/secrets.py` exists to make one structural guarantee — values are kept outside `data/`, so a
backup *cannot* contain a credential, *"not by being careful"*. `state.db` is inside `data/`. Putting
a bot token in that column destroys the guarantee for every install. (The old build was no better: a
plain-text `token` file at `0600` under the agent's directory, not encrypted at all.)

**The record holds the *name* of the value; the value lives in the sealed store.** That is already
what the old build's record did (`secret = {"env": […], "files": […]}`) and what `--check` reports.

And the naming is already solved. `skills/needs.py` has profiles: *"a whole named set of values,
found from the suffixes standing on the names a thing declares"*. **A channel's credentials are a
profile of the adapter, named for the agent** — `DISCORD_BOT_TOKEN__ALAN`. No new mechanism, no new
naming rule, `rundesk env list` already hints them, and `rundesk channels doctor` can reuse the
`skills doctor` verdict shape wholesale.

### The flow

Take mautrix's `GetLoginFlows` — the best setup abstraction found — where **the core renders a
generic wizard from adapter-supplied data** rather than each adapter shipping README prose. Three step
types cover every real case: *user input* (token paste), *display-and-wait* (QR, approve-on-phone),
and *webview* (OAuth) — and webview is the one to punt on, because it needs a callback server this
product cannot have.

Concretely, `rundesk channels add alan discord`:

1. walks the adapter's declared steps, reading the token with `getpass` — never from `argv`;
2. runs `--check`, which signs in and **reports what it found**: the bot's name, the servers it can
   see, and the invite URL with the right permission bits already set;
3. **writes nothing until the check says `ok`** — the rule already in the contract, and the one that
   matters most: *an agent whose channel is misconfigured must find out while somebody is typing the
   command, not at three in the morning*;
4. expands `shapes` into one channel per kind of place.

**Keep `shapes`.** One `add` making several channels was settled by measurement: DMs and a public
room need different allow-lists, and when one message matched both it was answered twice by two
processes.

---

## 4 · The command surface

The draft in `brief.md` has four problems: `<agent>` sits before the noun where every shipped verb
puts it after (`rundesk schedules add <agent> <schedule>`); the slot after `add` means *type* where
every other verb means *name* — the old build hit this exactly and moved to name-first with `--kind`;
`--owner`/`--allow` conflate a person with a per-channel address; and `--token-stdin` presumes one
secret when Slack needs two.

```
rundesk channels                                     every agent's channels, and how each stands
rundesk channels list <agent>
rundesk channels add <agent> <channel> --kind <adapter> [--allow <person>]… [-- <adapter opts>]
rundesk channels show <agent> <channel>
rundesk channels configure <agent> <channel> [--allow <person>] [--deny <person>]
rundesk channels test <agent> <channel>              run --check again; prove the credential still works
rundesk channels remove <agent> <channel> --confirm
rundesk channels doctor [<agent>]                    what cannot be used and exactly why; exits non-zero

rundesk people list <agent>
rundesk people add <agent> <person> [--owner]
rundesk people link <agent> <person> <channel> <address>
rundesk people claim <agent> <person> <channel>      prints a code to DM from the new channel
rundesk people forget <agent> <person> --confirm
```

`--allow <person>` now names a person rather than a raw snowflake, which is the whole point of §2.

---

## 5 · Schema deltas against `brief.md`

1. **`conversations` needs `UNIQUE (source, source_id)`.** The old build's derived id —
   `sha256(channel\0space\0thread)[:16]` — is *precisely* what let two turns weeks apart in different
   processes land on one conversation without asking anything first. An autoincrement int PK needs
   that constraint to do the same work, and `brief.md` declares none. **This is a real defect in the
   brief, not a preference.**
2. **`channels.secrets` holds names, never values.** §3.
3. **`channels` lost `kind`** — the old build could not resolve an adapter without it. Either `key`
   carries it or it comes back.
4. **`channels` lost `describes`** (the `--check` one-liner a person reads to confirm they got the
   right room) **and `fills`** (what made a misspelt template refusable *when written* rather than
   silently blank on every turn afterwards).
5. **`conversation_messages` lost `external_id`** and its partial unique index. Bring both back *and
   give them a writer* via the outbox acknowledgement — see §1.
6. **New:** `people`, `people_handles`, `places`, `outbox`.

Dead columns not worth carrying: `conversation.thread` was always `""`, `parent_id` was never
written, `channel.enabled` was never non-1.

---

## 6 · Carry forward verbatim

Short list, each with a cost already paid:

- **Prose is held and handed over whole.** The single best decision in the old build. It makes
  "post half a sentence" structurally impossible and kills a class of edit-storm rate-limit bugs.
- **The outbound field allowlist is named, not filtered** — a new vendor key defaults to *not*
  crossing the seam.
- **The double-verified outbound attachment.** Core validates with `O_NOFOLLOW` and a `sha256`; the
  adapter re-opens with `O_NOFOLLOW` and refuses on a size or digest mismatch. That closes a real
  TOCTOU window and is worth copying line for line.
- **Authorization is one function, asked of the record, and a stranger gets silence** — replying to
  tell somebody they are a stranger confirms the agent is listening and spends the owner's tokens.
- **Nothing is written until `--check` says `ok`.**
- **Everything is bounded, and eviction cancels.** Dropping a conversation without cancelling its
  timers left a typing indicator renewing for the life of the process.

---

## 7 · The traps, each with somebody else's incident behind it

- **An empty recipient set must never mean everybody.** OpenClaw shipped `return true; // default-allow
  fallback` and sent *approval prompts* to every connected client. The old build had this right —
  an empty allow-list authorizes nobody, and `add` refuses to write one — and that rule should be a
  `CHECK`, not a convention.
- **Two registries drift, and the drift lies.** OpenClaw's `isKnownChannel()` answers yes while
  `getChannelPlugin()` returns undefined. This product already has the pattern for avoiding it:
  adapters are **found by looking**, never listed, exactly as skills are.
- **Discovery that fails silently reads as a missing feature.** Hermes shipped a wheel missing its
  entry points — "No adapter available for discord" with the adapter on disk. OpenClaw disabled 33
  plugins through one path-resolution regression. `channels doctor` has to be able to say *found,
  not runnable* and *connected, never received an event* — the second is what a missing Discord
  privileged intent looks like, and it fails silently.
- **One channel failing must not end the gateway** (Hermes #5196). Already the rule in
  `schedules.firing`; it applies here unchanged.
- **An untyped passthrough bag becomes the blocker.** Errbot's `extras`, Home Assistant's
  `data: dict` — whose own maintainers name it as what blocks their migration — and Matterbridge's
  `Extra`. **The existing contract has one: `RUNDESK_SETTINGS`, "passed through unread".** That is
  defensible for adapter-owned settings *because the adapter defines and normalises them in
  `--check`*, but it should not grow into the place core-level options go to avoid being designed.
- **Version the contract from day one.** Home Assistant's `notify` migration has run two years, needed
  a whole repairs subsystem, covers 9 of 67 integrations, regressed groups, and closed a breakage as
  "not planned".
- **Attachments assume a public file host** in both Matterbridge and mautrix. We have none, which is
  why the old build's approach — files are local paths, verified twice — is the right one and not a
  limitation to fix.
- Smaller, each real: never `fnmatch` an identity string; use `hmac.compare_digest` for a claim code;
  do not put directives like `MEDIA:` in a message body (Hermes needed two maskers to undo it).

---

## 8 · Open questions

- **How Discord inbound is reached** (§0, options A, B and C). This one gates the plan rather than
  sitting inside it.
- **People per agent or install-wide** (§2, options B and C).
- **How much capability vocabulary on day one** — three fields, or the levelled shape in full.
- **Whether the claim-code flow lands in the first release** or after `people link`.
- **Whether a schedule stores a resolved place or a symbolic person+channel.** Recommended
  symbolic — but it means the send path can fail on an unresolvable person, which needs a state.
