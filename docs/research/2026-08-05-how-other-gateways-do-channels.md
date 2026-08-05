# Research: how other gateways do channels

**Last updated:** 2026-08-05
**Question it answers:** How do comparable open-source systems structure a pluggable channel adapter —
the plugin boundary, capability negotiation, cross-channel identity, authorization, outbound addressing
and setup UX — and which of their answers survive a stdlib-only Python gateway with SQLite per agent.

**How this was established.** Everything below was read on **2026-08-05** from the URL given, either the
project's own documentation, its source files on `raw.githubusercontent.com`, or its issue tracker. Where a
claim comes from a third party (a blog, a docs mirror) rather than the project itself, it is labelled. Where
a documentation page and the actual source disagree — and in one case they do, materially — both are given
and the source is believed. Claims marked **(inferred)** were not verified against source; claims marked
**(gap)** are things looked for and not found, recorded as gaps rather than guessed at.

These projects move weekly. Every version number and every "currently" in this page is true of 2026-08-05
and of nothing else.

## The short version

Three distinct architectures showed up, and they are not variations on one idea:

1. **Fat in-process interface with declared capabilities** — OpenClaw. One TypeScript object per channel
   with ~24 optional adapter slots, a `capabilities` record the core reads before it attempts anything,
   and graceful degradation written into the core rather than into each channel.
2. **Thin in-process interface with no capability model** — Hermes, Errbot, Rasa. A base class with a
   handful of abstract methods. What a channel cannot do is a no-op or an exception, discovered at call
   time.
3. **Address-as-plugin-selector, send-only** — Apprise. There is no channel object the caller holds; there
   is a URI, and the scheme picks the plugin. No inbound, no identity, no session.

Everything else in this page is detail hanging off that split, plus a fourth thing that only Matrix really
has: an identity model where the *bridge* owns a persistent record of who a person is on each side.

---

## OpenClaw

A self-hosted personal-AI gateway in TypeScript, reached from ~31 chat channels. The closest analogue to
rundesk that exists, and the most developed answer to every question on this list.

### 1. Plugin boundary

An **imported ES module in the same process**, published as an npm package, discovered from a manifest
without executing code.

Declaration is split in two. `package.json` carries an `openclaw` field whose `extensions` array names the
entry files, plus catalog metadata for the channel
([sdk-setup](https://docs.openclaw.ai/plugins/sdk-setup)):

```json
"channel": {
  "id": "my-channel",
  "label": "My Channel"
}
```

Alongside it, **every plugin requires an `openclaw.plugin.json` manifest in the package root**, holding
`id`, `channels` or `providers`, and a `configSchema` given as JSON Schema. The point of the split is
stated plainly: the manifest lets OpenClaw "validate settings and discover plugins **before loading runtime
code**" ([sdk-setup](https://docs.openclaw.ai/plugins/sdk-setup)). User config goes under
`plugins.entries.<id>.config`, is validated against that schema, and arrives at the plugin as
`api.pluginConfig`.

The runtime object is a `ChannelPlugin`. It is deliberately **not** one fat interface — it is one required
slot and roughly twenty-odd optional adapter slots, each named for one narrow capability. A third-party
deep dive that reproduced the type
([avasdream.com, 2026-01-28](https://avasdream.com/blog/openclaw-channels-messaging-deep-dive)) gives the
head of it as:

> `id: ChannelId` `meta: ChannelMeta` `capabilities: ChannelCapabilities` `config: ChannelConfigAdapter`
> [plus 20+ optional adapter slots]

and the rule as: "Only `config` is required. Everything else is optional — channels implement what they
support and skip the rest."

The official SDK guide ([sdk-channel-plugins](https://docs.openclaw.ai/plugins/sdk-channel-plugins))
agrees in substance and names the slots. The required core:

```ts
id: string
config: {
  listAccountIds(cfg): string[]
  resolveAccount(cfg, accountId?)
  inspectAccount?(cfg, accountId?)   // read-only
}
```

with a stated rule worth stealing on its own — "**Account resolution/inspection belongs on `config`, not
`setup`**"; `setup` covers onboarding *writes* only. The optional slots include `security.dm`, `pairing`,
`message`, `outbound`, `threading`, `messaging`, `approvalCapability`, `conversationBindings`,
`heartbeat` (typing indicators), `actions` and `setup`. Representative shapes:

```ts
security?: { dm?: { channelKey: string; resolvePolicy(account): string;
                    resolveAllowFrom(account): string[]; defaultPolicy: string } }
pairing?:  { text?: { idLabel: string; message: string; notify(params): Promise<void> } }
threading?:{ topLevelReplyToMode: "reply" | "thread" | "custom" }
heartbeat?:{ sendTyping(target): Promise<void>; clearTyping?(target): Promise<void> }
```

**The single most transferable idea here is the granularity.** A channel does not implement a large
interface with stubs; it omits the slot, and the absence *is* the declaration. Typing indicators are not a
boolean on a big object, they are the presence or absence of `heartbeat`.

### 2. Capability negotiation

Declared, not discovered, and at three separate levels of resolution. This is the most thought-through
part of the whole design and the part most directly relevant to our "Discord streams, email gets one
message" requirement.

**Level one — coarse channel capabilities.** A `ChannelCapabilities` record, reported by the deep dive
above as:

> `chatTypes: Array<'direct' | 'group' | 'channel' | 'thread'>` `polls?` `reactions?` `edit?` `unsend?`
> `reply?` `effects?` `threads?` `media?` `nativeCommands?` `blockStreaming?` — all boolean

with the consumer named: "The agent layer reads these capabilities to decide what's possible — it won't
try to send a poll on Signal or edit a message on WhatsApp." *(Read from the blog, which quotes the type;
the SDK type file itself was not reachable — treat the exact field list as third-party-verified, the
existence and purpose as documented.)*

**Level two — live/streaming capabilities.** Separate from the above, `message.live.capabilities` is an
enumerated set ([sdk-channel-plugins](https://docs.openclaw.ai/plugins/sdk-channel-plugins),
[sdk-channel-outbound](https://docs.openclaw.ai/plugins/sdk-channel-outbound)):

| value | meaning |
|---|---|
| `draftPreview` | can post a partial message that will later be replaced |
| `previewFinalization` | can turn a draft into the final message in place |
| `progressUpdates` | can emit intermediate activity |
| `nativeStreaming` | the transport itself streams |
| `quietFinalization` | can finalize without re-notifying |

and a matching `message.live.finalizer.capabilities` set: `finalEdit`, `normalFallback`, `discardPending`,
`previewReceipt`, `retainOnAmbiguousFailure`. The instruction to plugin authors is explicit — "Declare live
and finalizer capabilities precisely — core uses these to decide what a channel can do" — and, on the
outbound page, "**Only declare capabilities the native transport actually preserves.**"

This is exactly our Discord-versus-email split, and note how it is factored: it is not one `streaming:
bool`. Discord DM declares `draftPreview` + `previewFinalization` + `finalEdit` and gets live editing;
email declares none of them and the same core code path collapses to a single send. **The core owns the
degradation, the channel only owns the truth about itself.**

**Level three — presentation capabilities.** A structured payload of typed blocks (`text`, `context`,
`divider`, `buttons`, `select`, `chart`, `table`) is sent once and rendered per channel, gated by
([message-presentation](https://docs.openclaw.ai/plugins/message-presentation)):

```ts
type ChannelPresentationCapabilities = {
  supported?: boolean; buttons?: boolean; selects?: boolean; context?: boolean;
  divider?: boolean; charts?: boolean; tables?: boolean;
  limits?: {
    actions?: { maxActions, maxLabelLength, supportsStyles, supportsDisabled... }
    selects?: { maxOptions, maxLabelLength... }
    text?:    { maxLength, encoding, markdownDialect... }
  }
}
```

The fallback rules are specified centrally rather than left to each channel: command actions render as
``label: `command` ``, callback actions become label-only so opaque values stay private, URL actions show
label and URL, charts and tables "become deterministic text", and an unsupported select lists its options
as text. The governing sentence is worth copying verbatim into our own design:

> "Unsupported native controls should degrade rather than fail the whole send."

The `limits` sub-object is the quiet win — `text.maxLength`, `markdownDialect` and `maxActions` are
declared so, in the docs' words, they "describe the generic envelope core can adapt before calling the
renderer". Message splitting and Markdown-dialect translation happen once in core, not once per channel.

**Outcome typing.** `sendDurableMessageBatch(...)` returns one of four explicit outcomes rather than a
boolean ([sdk-channel-outbound](https://docs.openclaw.ai/plugins/sdk-channel-outbound)): `sent`,
`suppressed` ("no platform message should be treated as missing"), `partial_failed` ("at least one platform
message was accepted before a later payload or side effect failed"), and `failed`. `suppressed` and
`partial_failed` are the two states a boolean loses, and both matter for retry logic.

### 3. Identity

**Manual, config-file, opt-in linking of per-channel ids to a canonical name. There is no contact record
and no verification.**

The primitive is `session.identityLinks`, which "maps canonical ids to provider-prefixed peers for
cross-channel session sharing". The shape is a plain map from canonical name to a list of prefixed ids:

```json5
identityLinks: { alice: ["telegram:123456789", "discord:987654321012345678"] },
```

The mechanism is a substitution in the session key. The three DM session-scoping modes are:

| mode | isolates by |
|---|---|
| `per-peer` | sender id, across channels |
| `per-channel-peer` | channel + sender — "recommended for multi-user inboxes" |
| `per-account-channel-peer` | account + channel + sender — "recommended for multi-account inboxes" |

and: "When `session.identityLinks` matches a provider-prefixed peer id (such as `telegram:123`), the
canonical key substitutes for the `<peerId>` segment, enabling the same individual to maintain a unified DM
session across multiple communication platforms"
([docs.claw.so engine mirror of `concepts/session`](https://docs.claw.so/engine/concepts/session/)). The
upstream page carries the one-line tip — "If the same person contacts you from multiple channels, use
`session.identityLinks` to map their identities to one canonical peer id so they share a session" — and the
consequence, "Without identity binding, OpenClaw treats them as separate identities"
([concepts/session](https://docs.openclaw.ai/concepts/session)).

*(Provenance: the upstream `docs.openclaw.ai/concepts/session` page, fetched 2026-08-05, contains the tip
but **not** the config example; `docs/gateway/configuration-reference.md` could not be retrieved directly
— the Fossies mirror returned 401 and two other mirrors 403. The example, the mode table and the
substitution sentence above were read from the `docs.claw.so` mirror, which is a third-party copy of the
same docs tree. Substance is consistent across all sources seen; the exact field name and shape are
therefore high-confidence, but were not read from the OpenClaw repository itself.)*

Three things follow, and all three are the interesting part:

- Identity is **a session-routing device, not a person record**. It buys shared conversation continuity.
  It does not give you a `people` table you can ask "what is Tim's email address".
- It is **populated by hand, in a config file**. No pairing flow writes into it, no auto-linking, no
  verification. You must already know Tim's Discord snowflake and his Telegram numeric id.
- It is **separate from authorization**, which is per-channel `allowFrom` lists (below). The same human
  is therefore listed twice, in two unrelated places, in two different formats.

That gap is visible in the wild: a community "identity-resolver skill" exists specifically to map
"channel-specific identities to a single, 'canonical' user ID", written up as solving the problem that
"the agent cannot inherently know that 'Telegram User A' and 'Discord User B' are actually the same
person" ([dev.to, posted 17 March](https://dev.to/aloycwl/mastering-user-identity-in-openclaw-a-guide-to-the-identity-resolver-skill-4lg6)).
It stores its mapping outside the gateway and uses `fcntl` file locking; the article does not say where
([gap](https://dev.to/aloycwl/mastering-user-identity-in-openclaw-a-guide-to-the-identity-resolver-skill-4lg6)).
That a third party had to build this as a *skill* is the strongest evidence that first-class identity is
missing.

### 4. Authorization

Per-channel, enforced on inbound before the agent runs, with a declared trust model that is worth quoting
because it decides how much machinery is justified
([gateway/security](https://docs.openclaw.ai/gateway/security)):

> "This guidance assumes one trusted operator boundary per gateway (single-user, personal-assistant
> model)."

and, for multiple untrusted users, the answer is separate gateway instances, not finer permissions. There
is no owner-versus-user *role* in the sense of a users table; there is a set of allowlists.

`dmPolicy` per channel, four values ([config-channels](https://docs.openclaw.ai/gateway/config-channels)):

| value | behaviour |
|---|---|
| `pairing` (default) | unknown senders get an expiring code; bot ignores them until approved |
| `allowlist` | unknown senders blocked, no handshake |
| `open` | anyone may DM — requires an explicit `"*"` opt-in |
| `disabled` | inbound DMs ignored entirely |

`allowFrom` is a list of channel-native identifiers, and **its format differs per channel** — Discord user
ids, Slack `user:U123`, Telegram raw ids, phone numbers for WhatsApp and Signal. The Discord page shows the
prefixed form `"discord:123456789012345678"`, plus `"*"` and a named-group form
`"accessGroup:operators"` ([channels/discord](https://docs.openclaw.ai/channels/discord)). Groups get their
own layer: `groupPolicy` (`allowlist` default / `open` / `disabled`), a per-group `groupAllowFrom`, and
`requireMention: true`. One rule stated because it was presumably learned the hard way: "Replying to a bot
message does **not** bypass `groupAllowFrom`."

A deliberate separation that is easy to miss and expensive to omit — **trigger authorization is not context
visibility**. Who may invoke the agent (`dmPolicy`, allowlists, mention gates) is a different question from
what supplemental context reaches the model, which has its own setting `contextVisibility` with values
`"all"` (default), `"allowlist"`, and `"allowlist_quote"` ("keeps one explicit quoted reply"). The security
page is candid that requester-scoped tool controls "**do not sanitize other content** in that prompt (quoted
text, history, attachments)" and that all of this is "defense in depth, not hostile isolation".

Pairing is concrete and small: unknown sender gets a code, codes **expire after 1 hour**, pending requests
are **capped at 3 per channel**, approvals are written to
`~/.openclaw/credentials/<channel>-allowFrom.json`, driven by `openclaw pairing list <channel>` and
`openclaw pairing approve <channel> <code>`. Note that approval writes to a *file per channel*, again
per-channel rather than per-person.

### 5. Outbound addressing

The best-developed answer of any system here, and the one to copy. A single command with a **channel-scoped
target string**, and a channel prefix that makes the target self-describing
([cli/message](https://docs.openclaw.ai/cli/message)):

```
openclaw message send --channel <channel> --target <target> [--message ...] [--presentation ...] [--delivery ...]
```

`--channel` is required only when more than one channel is configured; with exactly one, it is the default.
And critically: "**Channel-prefixed targets (for example `discord:channel:123`) resolve the owning plugin
without an explicit `--channel`**" — the address carries its own routing.

Target grammar is per channel, and it is a *grammar*, not an opaque id:

| Channel | Target forms |
|---|---|
| Discord | `channel:<id>`, `user:<id>`, `<@id>` mention, bare numeric id |
| Slack | `channel:<id>`, `user:<id>` |
| Telegram | chat id, `@username`, forum topic `<chatId>:topic:<topicId>` |
| Matrix | `@user:server`, `!room:server`, `#alias:server` |
| Signal | `+E.164`, `group:<id>`, `uuid:<id>`, `username:<name>` |
| WhatsApp | E.164, group JID `...@g.us`, newsletter JID |
| Microsoft Teams | `conversation:<id>` (`19:...@thread.tacv2`), `user:<aad-object-id>` |
| Google Chat | `spaces/<spaceId>`, `users/<userId>` |
| Mattermost | `channel:<id>`, `user:<id>`, `@username`, bare id |
| iMessage | handle, `chat_id:<id>`, `chat_guid:<guid>`, `chat_identifier:<id>` |

The `<kind>:<id>` shape recurring across channels (`channel:` / `user:` / `group:` / `conversation:`) is
the useful invariant: it disambiguates a room id from a person id without the core knowing the channel.

Beyond `send`, the same CLI carries `poll`, `react` (add/remove/list), `read`, `edit`, `delete`,
`pin`/`unpin`/`pins`, `member info`, `permissions`, and a `--targets <space-separated list>` broadcast.
`--delivery <json>` carries generic preferences such as `{"pin": true}`. Note what is *not* here: there is
no "send to Tim, you pick the channel". Every send names a channel or a channel-prefixed target. **Even the
most developed system on this list does not do requirement (e) — resolving "email me the daily report" to a
person and then to an address — and neither does anything else surveyed.** *(gap, and it is the most
important gap in this page.)*

### 6. Setup UX

`openclaw onboard` is a guided terminal flow ([start/wizard](https://docs.openclaw.ai/start/wizard)):
accept a security notice; detect models and API keys from environment and local installs; **test the first
candidate with a real completion** and fall through on failure; persist "only the verified model route";
then configure workspace, gateway, channels and agents. The verify-before-persist step is the good idea —
nothing is written to config until it has been proven to work.

Connecting Discord, however, is still seven manual steps in someone else's web UI
([channels/discord](https://docs.openclaw.ai/channels/discord)): create an application in the Developer
Portal; enable privileged gateway intents (**Message Content** required for guild messages, **Server
Members** recommended for role allowlists and name resolution, Presence optional); reset and copy the bot
token; build an OAuth2 invite URL with scopes `bot` + `applications.commands` and the permission set (View
Channels, Send Messages, Read Message History, Embed Links, Attach Files, plus Send Messages in Threads);
open that URL and pick a server; enable Developer Mode to collect server and user ids; allow server DMs in
privacy settings; then set the token and patch config. **No amount of wizard removes those steps** — they
are Discord's, not the gateway's. What a wizard *can* do is fetch the ids for the user, which is what step
six is really about.

Secrets: the interactive path offers "plaintext token storage (default) or opt into a `SecretRef`", and
non-interactive setup takes `--secret-input-mode ref` for env-backed refs. Config shows the ref form:

```json5
{ channels: { discord: { enabled: true,
    token: { source: "env", provider: "default", id: "DISCORD_BOT_TOKEN" } } } }
```

Everything under `~/.openclaw/` is assumed to contain secrets — `openclaw.json` (tokens, provider
settings), `credentials/**`, `state/openclaw.sqlite` (MCP OAuth tokens), per-agent
`agents/<agentId>/agent/openclaw-agent.sqlite`. Stated permissions: `~/.openclaw/` should be `700`,
`openclaw.json` should be `600` ([gateway/security](https://docs.openclaw.ai/gateway/security)). There is a
first-class `openclaw security audit` with `--deep` (live gateway probe) and `--fix`.

### 7. What they got wrong

From the issue tracker, all read on 2026-08-05:

- **Registry identity is not pinned, and channels silently vanish.** `loadOpenClawPlugins()` called more
  than once at runtime creates new `PluginRegistry` instances; each becomes active via
  `setActivePluginRegistry()`; a registry without initialized channel plugins makes `getChannelPlugin()`
  return `undefined`, so the message tool fails with `Unknown channel: telegram` for a channel that worked
  at startup. The contradiction is sharp: `isKnownChannel()` still returns true because it consults a
  hardcoded `CHANNEL_IDS` list, while `getChannelPlugin()` reads the empty live registry. There is also a
  race where "the registry can swap between" resolution and lookup inside `sendMessage()`. The same class
  of bug was fixed for HTTP routes by registry pinning in PR #47902 and "was not addressed" for channels
  ([issue #48790](https://github.com/openclaw/openclaw/issues/48790)). **Lesson: a static list of known
  channel ids and a dynamic registry of loaded ones will drift, and the drift presents as a lie.**
- **"Unknown channel" is the wrong error for "plugin not installed".** `Unknown channel: whatsapp`,
  `Unsupported channel: whatsapp` and `Package not found on npm` were all raised for what was really one
  situation: the WhatsApp plugin had been removed from bundled extensions and never published. The
  requested fix is to **distinguish a known channel type from an installed one** and say so —
  `Channel 'whatsapp' requires plugin @openclaw/whatsapp. Install it with: openclaw plugins install …` —
  and to stop using identical phrasing for "plugin not in allow list" and "plugin does not exist"
  ([#52965](https://github.com/openclaw/openclaw/issues/52965), and a duplicate
  [#52984](https://github.com/openclaw/openclaw/issues/52984), located by search but not opened).
  **A registry of channel *names* and a registry of channel *implementations* are two different things and
  the error message has to know which one failed** — the same root confusion as #48790 above, surfacing as
  a UX complaint instead of a bug.
- **A release disabled every channel plugin.** v2026.2.21 and v2026.2.22 broke Telegram, Discord, Slack,
  Signal and WhatsApp simultaneously against configs that worked on v2026.2.19 — **33 plugins disabled,
  only 4 utility plugins loading** — with the surfaced error being a path failure,
  `read failed: ENOENT: no such file or directory, access '/.../openclaw/extensions/stock/telegram/index.ts'`
  ([#24395](https://github.com/openclaw/openclaw/issues/24395), open, no maintainer response at time of
  reading). **Plugin loading that resolves entry files by path at runtime turns any packaging change into a
  total channel outage.**
- **A default-allow fallback turned a filter into a broadcast.** In 2026.6.8, plugin **approval prompts**
  reached every connected bot in a shared chat rather than the requesting agent's. The mechanism is worth
  reading closely because it is a two-line mistake: `isApprovalRecordVisibleToClient` compares device and
  connection ids and ends with `return true; // ← line 62: default-allow fallback`; when nothing matches
  it instead returns false for *every* client, so
  `resolveApprovalRequestRecipientConnIds()` yields an empty set, and the code falls through to
  "`params.context.broadcast(...)` — the unfiltered fallback — which delivers to every connected client".
  The missing ingredient is an `agentId` comparison in the visibility check
  ([#94768](https://github.com/openclaw/openclaw/issues/94768)). **An empty recipient set must mean send to
  nobody, never send to everybody** — and approvals are the worst possible payload to get this wrong on.
- **Disabled channels still warn.** `doctor` emits warnings for bundled channels whose generated modules
  are missing even when the channel is explicitly disabled
  ([#86039](https://github.com/openclaw/openclaw/issues/86039), located by search, not opened).

*(Provenance: #48790, #24395, #52965 and #94768 were fetched and read in full. #52984 and #86039 were
located by search and not opened; their one-line summaries are indicative only.)*

### What a stdlib-only Python port cannot take

The manifest-before-code split, the capability records, the presentation blocks, the four-valued send
outcome, the `<kind>:<id>` target grammar and the degradation rules are all pure data and pure logic —
they port directly. What does not port is underneath: OpenClaw's Discord and Slack channels are npm
packages wrapping maintained platform SDKs holding a websocket gateway connection. Discord's Message
Content intent exists precisely because the bot is expected to hold a live gateway socket. **A stdlib-only
Python process has no websocket client**, so a Discord channel is either a hand-rolled RFC 6455 client over
`socket`/`ssl` (feasible — it is a framing protocol, not a library problem, but it is real work including
the permessage-deflate negotiation you can decline) or it is not a live channel at all. Slack has an escape
hatch OpenClaw does not need and we do: **Events API over HTTPS** instead of Socket Mode, which is an
inbound HTTP server rather than an outbound socket — but that trades the websocket for a public URL.

---

## Hermes Agent

`NousResearch/hermes-agent` — a Python personal agent with a terminal UI and a gateway reachable from 27+
messaging platforms ([repo](https://github.com/nousresearch/hermes-agent),
[integrations](https://hermes-agent.nousresearch.com/docs/integrations/)).

**Which Hermes this is, and why.** "Hermes" is a badly overloaded name. This is the one that matches the
brief — an agent gateway with per-platform channel adapters, `plugins/platforms/<name>/adapter.py`, a
`gateway/` subsystem, a `SOUL.md` persona file and a `hermes send` outbound CLI. It is also the same
project examined in this repo's earlier
[`2026-07-29-what-a-gateway-tells-its-agent.md`](2026-07-29-what-a-gateway-tells-its-agent.md), which read
its `agent/prompt_builder.py` and `hermes_cli/default_soul.py`, so the two pages are about the same
codebase. Other projects called Hermes — the Nous Research *model* family of the same name, and unrelated
message-bus libraries — are not this.

It is the single most useful comparison here because it is **Python, single-process, launchd/systemd
service, SQLite-adjacent, per-profile isolation** — structurally where we are, minus the stdlib-only
constraint.

### 1. Plugin boundary

An **imported Python class in the same process**, discovered through **setuptools entry points**.

Adapters subclass `BasePlatformAdapter` from `gateway/platforms/base.py`. Read from source
([base.py](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/gateway/platforms/base.py)):

```python
class BasePlatformAdapter(ABC):
    """Base platform adapter interface for Telegram, Discord, WhatsApp, Weixin, etc."""

    @abstractmethod
    async def send_message(self, chat_id: str, text: str, **kwargs) -> SendResult: ...
    @abstractmethod
    async def send_photo(self, chat_id: str, photo_path: str, **kwargs) -> SendResult: ...
    @abstractmethod
    async def send_audio(self, chat_id: str, audio_path: str, **kwargs) -> SendResult: ...
    @abstractmethod
    async def delete_message(self, chat_id: str, message_id: str) -> bool: ...
```

with two normalized dataclasses that are the actual contract surface:

```python
@dataclass
class MessageEvent:                     # normalized inbound, any platform
    text: str
    message_type: MessageType = MessageType.TEXT
    source: SessionSource = None
    raw_message: Any = None
    message_id: Optional[str] = None
    media_urls: List[str] = field(default_factory=list)
    media_types: List[str] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class SendResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    error_kind: Optional[str] = None
    retry_after: Optional[float] = None
    continuation_message_ids: tuple = ()
```

`SendResult` is worth pausing on. `error_kind` plus `retry_after` means **rate limiting is part of the
contract**, not something each adapter re-invents; `continuation_message_ids` means **a long reply legally
becomes several platform messages** and the core still has all their ids for a later edit. Both are cheap
to copy and painful to retrofit.

A concrete adapter registers itself with a factory, not by being instantiated at import
([irc/adapter.py](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/plugins/platforms/irc/adapter.py)):

```python
class IRCAdapter(BasePlatformAdapter):
    """Async IRC adapter implementing the BasePlatformAdapter interface."""

    async def connect(self, *, is_reconnect: bool = False) -> bool: ...
    async def disconnect(self) -> None: ...
    async def send(self, chat_id: str, content: str,
                   reply_to: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None): ...

def register(ctx):
    """Plugin entry point: called by the Hermes plugin system."""
    ctx.register_platform(
        name="irc",
        label="IRC",
        adapter_factory=lambda cfg: IRCAdapter(cfg),
        # ...
        emoji="💬",
        pii_safe=False,
        allow_update_command=True,
    )
```

Discovery is the `hermes_agent.plugins` entry-point group, each pointing at a module exposing `register(ctx)`
([issue #34511](https://github.com/NousResearch/hermes-agent/issues/34511)). Bundled adapters live at
`plugins/platforms/<name>/adapter.py` and SDK imports are **deferred** — platform libraries import only when
the platform is actually used, not during ordinary CLI operations
([gateway-internals](https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals/)).
Adapters register through `gateway/platform_registry.py`.

### 2. Capability negotiation

**Essentially none — and the project's own documentation overstates it.** This is the most instructive
finding in the section, so both readings are given.

`AGENTS.md`, read via fetch, describes adapters declaring `supports_threads`, `supports_reactions`,
`supports_file_upload`, `supports_media`, `supports_voice`
([AGENTS.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/AGENTS.md)). The **source
does not bear this out**. `PlatformEntry`, the record `PlatformRegistry.register(self, entry: PlatformEntry)`
stores, carries no such flags
([platform_registry.py](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/gateway/platform_registry.py)):

```python
pii_safe: bool = False
allow_update_command: bool = True
emoji: str = "🔌"
max_message_length: int = 0
platform_hint: str = ""
cron_deliver_env_var: str = ""
allowed_users_env: str = ""
allow_all_env: str = ""
```

plus function-valued fields `check_fn` (is the dependency installed), `validate_config`, `is_connected`,
and `standalone_sender_fn`. And the canonical adapter confirms it from the other end: the IRC adapter
declares **no** thread or reaction attributes at all, implements `send_typing()` as a no-op with the
comment that "IRC has no typing indicator", and hand-rolls message splitting against IRC's "~512 byte line
limit" inside the adapter.

So the real model is: **capability is expressed as a silently-successful no-op inside each adapter.** The
core does not ask and cannot know. What it costs them:

- `max_message_length` is the *only* declared limit, so splitting logic is duplicated per adapter (IRC does
  its own) and the core cannot chunk generically the way OpenClaw's `limits.text.maxLength` lets it.
- There is no way to answer "can this channel stream?" — so there is no streaming/final-only distinction of
  the kind requirement (b) asks for, at the framework level. *(inferred from the absence of any capability
  field; not contradicted by anything read.)*
- A doc that claims flags the code does not have is itself the warning: **an undeclared capability model
  gets described as if it existed, because everyone needs one.**

The two capability-ish fields that *do* exist are worth noting because they are unusual and good:
`pii_safe` (per-platform, presumably gating what may be sent over that transport) and `standalone_sender_fn`
(this platform can deliver **without a running gateway**, i.e. a plain REST call). The second is a real
capability distinction and exactly the axis email/SMS/webhook fall on.

### 3. Identity

**Per-channel only. There is no cross-channel person record, and no equivalent of OpenClaw's
`identityLinks`.**

Session keys encode the channel into identity by construction
([gateway-internals](https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals/)):

```
agent:main:{platform}:{chat_type}:{chat_id}
agent:main:telegram:private:123456789
```

with the standing rule "Never construct session keys manually — always use `build_session_key()`" from
`gateway/session.py`. Adapters map platform identifiers onto internal `user_key`, `chat_id` and `thread_id`
([AGENTS.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/AGENTS.md)), and profiles add
a further namespace so "two profiles on the same platform/chat never collide".

Because the platform name sits *inside* the session key, the same human on Telegram and on Discord is two
sessions with two histories, by construction. Hermes documents this as intentional — sessions are keyed by
user id per platform "by design for privacy and context isolation". What continuity exists is at the *agent*
level, not the person level: the same memory, skill library and `SOUL.md` are reached through any platform.

**This is the cleanest possible demonstration of the design fork.** OpenClaw's `identityLinks` exists
precisely to punch a canonical id into the middle of a key that would otherwise be per-channel. Hermes did
not build that hole, so it does not have the capability. Choosing the key shape *is* choosing the identity
model, and it is very hard to change later because every stored session row is keyed by it.

*(Searched specifically for a Hermes contacts/roster/identity-link feature and found none — recorded as a
verified negative, not an unexamined gap.)*

### 4. Authorization

A layered chain evaluated on inbound, ordered
([gateway-internals](https://hermes-agent.nousresearch.com/docs/developer-guide/gateway-internals/)):

1. per-platform allow-all flag (e.g. `TELEGRAM_ALLOW_ALL_USERS`)
2. platform-specific allowlist, comma-separated user ids
3. DM pairing authentication for new users
4. global allow-all (`GATEWAY_ALLOW_ALL_USERS`)
5. default deny

Configuration is **environment variables**, one pair per platform — which is why `PlatformEntry` carries
`allowed_users_env` and `allow_all_env` as *strings naming the variables*. In practice
([messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)):

```
TELEGRAM_ALLOWED_USERS=123456789,987654321
DISCORD_ALLOWED_USERS=...
GATEWAY_ALLOW_ALL_USERS=true   # "NOT recommended for bots with terminal access"
```

Unlike OpenClaw, Hermes does have a **two-tier role** distinction, per platform:

```yaml
allow_admin_from: ["111"]
user_allowed_commands: [status, model]
```

— "Admins have full access; regular users can only run explicitly enabled slash commands", with a floor of
`/help` and `/whoami`. That floor is a nice touch: an unprivileged user can always find out who the bot
thinks they are, which makes allowlist debugging tractable.

Pairing mirrors OpenClaw's almost exactly — unknown users DMing the bot get a one-time code, expiring after
an hour, approved out-of-band with `hermes pairing approve telegram XKGH5N7P`, alongside `pairing list`,
`pairing revoke <platform> <user-id>` and `pairing clear-pending`
([cli-commands](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/reference/cli-commands.md)).
**Two independent projects converged on the same 1-hour expiring DM pairing code**, which is a strong signal
that it is the right shape for requirement (f).

### 5. Outbound addressing

`hermes send` — a one-shot send that deliberately does **not** start an agent or gateway loop, so cron jobs,
CI hooks and monitoring daemons can post
([cli-commands](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/reference/cli-commands.md)):

```bash
hermes send --to <TARGET> "message text"
hermes send --to <TARGET> --file <path>
echo "message" | hermes send --to <TARGET>
hermes send --list [platform]
```

Target grammar, four forms, in increasing specificity:

| form | meaning |
|---|---|
| `platform` | the home/default channel for that platform |
| `platform:chat_id` | a specific conversation |
| `platform:chat_id:thread_id` | a thread within it |
| `platform:#channel-name` | a named channel (Discord, Slack) |

with examples `telegram`, `telegram:-1001234567890`, `discord:#ops`, `discord:C0123ABCD`, `slack:#eng`,
`signal:+15551234567`. Named channels "are resolved against a channel directory cache at send time".

Three details worth taking:

- **The bare `platform` form.** `--to telegram` with no id means "the home channel". This is the closest
  anything surveyed comes to requirement (e) — a default destination per channel, so a script need not know
  an id. It is still per-*channel*, not per-*person*.
- **`--list [platform]` enumerates configured targets.** A discoverability affordance the other systems
  lack; it is what makes an opaque id grammar usable by a human.
- **Media as an in-band directive**, not a flag: `MEDIA:/tmp/chart.png` inside the message text, with
  `[[as_document]]` to prevent recompression. Convenient for piping, and a parsing hazard — the base class
  carries `_mask_protected_spans()` to "mask code blocks and inline code to preserve example MEDIA tags" and
  `_mask_json_string_media()` to "protect JSON string values from media extraction". **That is two
  defensive maskers to undo one convenience.** A flag would have cost nothing.

Other flags: `-s/--subject` (prepend a header line — the email affordance), `-q/--quiet`, `--json`.

The gateway/no-gateway split is explicit and important: "For bot-token platforms (Telegram, Discord, Slack,
Signal, SMS, WhatsApp-CloudAPI) no running gateway is required — `hermes send` talks directly to the
platform's REST endpoint", while plugin platforms needing a persistent adapter still require a live gateway.
**Sending and receiving have genuinely different infrastructure requirements, and the design admits it.**

### 6. Setup UX

`hermes gateway setup` — "the interactive wizard ... with arrow-key selection [that] shows which are already
configured" ([messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/)). Gateway
lifecycle is a full service story: `run` (foreground), `start`/`stop`/`restart`, `status`, `list` (all
profiles with PIDs), and `install`/`uninstall` which write **systemd or launchd** units
([cli-commands](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/website/docs/reference/cli-commands.md)).

Secrets are environment variables. Adapters holding unique credentials must call `acquire_scoped_lock()` in
`connect()` and `release_scoped_lock()` in `disconnect()` so that "two profiles [do not use] the same
credential" simultaneously, with the IRC adapter named as the canonical pattern
([AGENTS.md](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/AGENTS.md)). **A bot token is
a singleton resource** — two processes on one Discord token fight over the same gateway session — and Hermes
makes that a first-class lock rather than a documentation note. Directly applicable to us: one launchd job
per agent, several agents, one shared token is a real collision.

Per-platform Discord/Slack setup pages exist but were not reachable in the form fetched; the count of manual
steps for Hermes specifically is a **(gap)**. It is Discord's own flow, so OpenClaw's seven steps are the
right order of magnitude *(inferred)*.

### 7. What they got wrong

- **All-or-nothing platform startup.** With several platforms configured, one failing connection killed the
  whole gateway: `ERROR gateway.run: Gateway failed to connect any configured messaging platform`. The
  requested behaviour — "If at least one messaging platform connects successfully, the gateway should run
  with that platform", failed adapters logged and skipped — is obviously right in hindsight, and the
  reporter's scenario is the one that makes it bite: a fleet where nodes hold partial credentials could
  launch no gateway at all
  ([issue #5196](https://github.com/NousResearch/hermes-agent/issues/5196)).
- **Entry-point discovery broke silently in a packaged release.** In PyPI v0.15.1, `entry_points.txt`
  contained only console scripts and omitted the `hermes_agent.plugins` group, so "Python sees no plugin
  entry points for `hermes_agent.plugins`", the loader never called `register(ctx)`, and the gateway logged
  `WARNING gateway.run: No adapter available for discord` — while the adapter module sat installed and
  intact on disk, and `hermes setup gateway` did not offer Discord at all
  ([issue #34511](https://github.com/NousResearch/hermes-agent/issues/34511)). **Entry-point discovery makes
  packaging metadata a load-bearing runtime dependency, and it fails in a way that looks like a missing
  feature rather than a broken install.**
- **The gateway path and the CLI path diverged.** `SOUL.md` and `AGENTS.md` were not loaded for Telegram
  gateway sessions in v0.14.0 although they loaded correctly in the core/CLI path
  ([issue #32843](https://github.com/NousResearch/hermes-agent/issues/32843)). Two entry points into one
  agent will drift unless they share the assembly code.

### What a stdlib-only Python port cannot take

`BasePlatformAdapter` is `async`/`await` throughout, which is stdlib (`asyncio`) and fine. The problem is
underneath again: every bot-token platform adapter wraps a vendored SDK — the deferred-import machinery and
the `check_fn` "dependency availability" field exist *because* those third-party imports may be absent. A
stdlib-only build deletes both the SDKs and the reason for `check_fn`, and inherits the transport work
directly. Note the useful corollary in the other direction: **`standalone_sender_fn` — the platforms that
can send with a plain REST call and no persistent connection — is precisely the set a stdlib build gets
cheaply**, since `urllib.request` posting JSON to a Discord webhook, a Slack `chat.postMessage`, a Telegram
`sendMessage`, or `smtplib` to an SMTP server needs nothing else. Outbound-only is nearly free; inbound is
where the library dependency actually lives.

---

## Matterbridge

`42wim/matterbridge`, Go, bridges ~20 chat protocols. Included as the **control group**: it is the most
widely deployed cross-platform relay in existence and it has *no* identity model and *no* capability model.
What that costs is legible in its issue tracker, which makes it more useful than a success story.

### 1. Plugin boundary

A **compiled-in Go interface**, registered by factory. The entire adapter contract is four methods
([bridge/bridge.go](https://raw.githubusercontent.com/42wim/matterbridge/master/bridge/bridge.go)):

```go
type Bridger interface {
	Send(msg config.Message) (string, error)
	Connect() error
	JoinChannel(channel config.ChannelInfo) error
	Disconnect() error
}

type Config struct { *Bridge; Remote chan config.Message }
type Factory func(*Config) Bridger
```

Inbound is a push onto `Config.Remote`, a channel of messages; outbound is `Send`. `Send` returns **the
destination-native message id as a string**, which is the one hook that makes any later edit or delete
possible. The envelope is one flat struct for every protocol
([bridge/config/config.go](https://raw.githubusercontent.com/42wim/matterbridge/master/bridge/config/config.go)):

```go
type Message struct {
	Text, Channel, Username, UserID, Avatar, Account string
	Event, Protocol, Gateway, ParentID, ID string
	Timestamp time.Time
	Extra map[string][]interface{}
}
```

`Extra` is the untyped escape hatch — files, attachments and avatar payloads all travel through it, keyed by
strings. Cheap, and where the type safety dies.

There is a **second, out-of-process boundary worth copying**: the `api` protocol implements `Bridger` with
`Connect`/`Disconnect`/`JoinChannel` as no-ops returning `nil`, and `Send` merely enqueues into a ring
buffer ([bridge/api/api.go](https://raw.githubusercontent.com/42wim/matterbridge/master/bridge/api/api.go)).
Its routes are `GET /api/health`, `/api/messages`, `/api/stream`, `/api/websocket` and `POST /api/message`,
authenticated by a single shared bearer token. **The generic adapter for anything you do not want to write
in-process is an HTTP long-poll/SSE plus a POST, behind a static token** — that is a third-party channel SDK
in about forty lines, and it is entirely within `http.server` and `urllib.request`.

### 2. Capability negotiation

**There is none.** `Event` is a string discriminator on the message, not a declaration:

```go
EventJoinLeave, EventTopicChange, EventFailure, EventFileFailureSize, EventAvatarDownload,
EventRejoinChannels, EventUserAction, EventMsgDelete, EventFileDelete, EventAPIConnected,
EventUserTyping, EventGetChannelMembers, EventNoticeIRC
```

The core hands every event to every destination; each bridge's `Send` decides by `if msg.Event == …`
whether to act or drop it. **There is no `Supports(feature)` on `Bridger`.** A bridge that does not handle
`EventMsgDelete` silently swallows it.

The wiki's Features page was fetched specifically to find the capability matrix, and **there is no table** —
the entire capability documentation is prose ([Features wiki](https://github.com/42wim/matterbridge/wiki/Features)):

> "Support incoming and outgoing edits and deletes: Discord, Mattermost, Slack, Matrix and Telegram.
> Support only incoming edits: Gitter. Support only incoming edits/deletes: RocketChat. Support only edits:
> XMPP. Support no deletes or edits: IRC, Steam(NR)."

Reactions and threading are not covered on that page at all. **After a decade and ~20 protocols, the
capability model is a paragraph in a wiki.** That is the whole lesson: if capability declaration is not in
the interface on day one, it never arrives, and users learn what works by trying it.

Worse, the degradation is silent in the place it matters most. `bridge/discord/webhook.go` carries the
comment *"Cannot use the resulting ID for any edits anyway, so throw it away. This has to be re-enabled when
we implement message deletion."* — so Discord-over-webhook, the mode required for username spoofing,
**discards the message id**, structurally killing deletes for the configuration most people run.

### 3. Identity — a verified negative

**Matterbridge has no person model. It relays display names.** This was checked directly rather than
assumed: every occurrence of `UserID` in `gateway/gateway.go` is a pass-through — three of them add
`msgUserID` to a Tengo user script's scope, one substitutes `{USERID}` into a nick format
([gateway/gateway.go](https://raw.githubusercontent.com/42wim/matterbridge/master/gateway/gateway.go)).
There is no user table, no persistent store, no config mechanism mapping a user on one protocol to the same
human on another. Matterbridge has no database at all.

What happens instead is `modifyUsername(msg, dest)`, which reads the **destination's** `RemoteNickFormat`
and does string replacement over `{NICK}`, `{BRIDGE}`, `{LABEL}`, `{PROTOCOL}`, `{GATEWAY}`, `{CHANNEL}`,
`{USERID}`, `{TENGO}`, `{NOPINGNICK}`, defaulting to `"[{PROTOCOL}] <{NICK}> "`
([Settings wiki](https://github.com/42wim/matterbridge/wiki/Settings)). Tim-on-Slack arriving in Discord is
literally the string `[slack] <Tim>`, or — with webhooks — a spoofed `Username` + `AvatarURL`, truncated to
Discord's 32-character limit.

**`{NOPINGNICK}` is the tell.** It is the same nick with a zero-width space injected so it will not ping a
same-named local user. That variable exists because **name collisions across platforms are a known,
unsolved problem in a design that has only names to work with.**

One thing Matterbridge *does* have is a **cross-protocol message-id map** — a different thing from identity
and worth stealing. `FindCanonicalMsgID(protocol, mID)`, `getDestMsgID(...)` and `SendMessage(...,
canonicalParentMsgID)` are backed by an **LRU of 5000 entries** mapping one canonical origin id to each
protocol's native id, with the sentinel `"msg-parent-not-found"`. The failure mode is instructive: it is a
**bounded in-memory cache**, so edits and thread replies silently stop working once the parent ages out.
**In a SQLite-per-agent design this is a table, and the fidelity is free.**

### 4. Authorization

Essentially absent. What exists is filtering, not authorization: `ignoreMessage(msg)` and
`ignoreText(text, input)` driven by per-bridge `IgnoreNicks` and `IgnoreMessages` regexes, enforced in the
gateway core on the outbound path. No owner or admin concept, no command permission table. The only real
credential boundary is the `api` bridge's shared token. *(Searched for a per-user allowlist and found none —
recorded as a gap.)*

### 5. Outbound addressing

`(account, channel)` pairs joined by a named gateway. An account is the string `protocol.name`, split on the
dot; config sections are `[discord.mydiscord]`, `[slack.myslack]`. Routing:

```toml
[[gateway]]
name = "gateway1"
enable = true

[[gateway.inout]]
account = "irc.libera"
channel = "#testing"
```

backed by `type Gateway struct { Name string; Enable bool; In, Out, InOut []Bridge }`. **Direction is a
property of membership in the `In` / `Out` / `InOut` lists, not of the address** — which gives send-only
channels for free, as an entry that appears only in `Out`. That is the closest thing Matterbridge has to
declaring "this channel can only receive", and it costs one list.

### 6. Setup UX

Discord: a bot token from the developer portal plus `Server=`, with per-channel `WebhookURL` (or auto-webhook
mode) if you want username spoofing. Slack is worse — the wiki's modern path requires a **special link to
create a "classic" app** with the shouted instruction *"USE THE LINK AND DON'T CLICK THE 'Create New App'
BUTTON"*, then App Home → **"Add Legacy Bot User"**, scopes `channels:write`, `chat:write:bot`,
`chat:write:user`, `users.profile:read`, install to workspace for an `xoxb-` token, then `/invite @botname`
per channel ([Slack bot setup wiki](https://github.com/42wim/matterbridge/wiki/Slack-bot-setup)). The sample
config still documents legacy user tokens and says they are "not recommended and will disappear". Socket Mode
is not mentioned anywhere — this documentation is of the RTM/classic-app era *(inferred: stale, and a real
risk if copied)*.

Secrets live in **plaintext in `matterbridge.toml`**. No keychain, no env indirection in the sample.

### 7. What they got wrong

- **Maintenance stall.** [Issue #2212](https://github.com/42wim/matterbridge/issues/2212), opened
  2025-02-14: *"Seems @42wim haven't been active on github since September last year. Matterbridge has not
  seen an upgraded release since 2023."* ~295 open issues, 46 open PRs when read.
- **Threading was retrofitted and is still incomplete.**
  [Issue #638](https://github.com/42wim/matterbridge/issues/638), open since 2018, tracks thread support one
  platform at a time: Slack/Discord/RocketChat done, Mattermost/Matrix/Teams partial, Gitter "would require
  messy workarounds", IRC impossible. **This issue is what "no capability model" costs, itemised.**
- **Edits and deletes lose fidelity** — a Matrix→Mattermost edit renders as two separate messages
  ([#1821](https://github.com/42wim/matterbridge/issues/1821)); Telegram deletes never reach Discord
  ([#840](https://github.com/42wim/matterbridge/issues/840)).
- **Attachments require you to run a public file host.** `handleFiles()` sanitizes the filename with
  `[^a-zA-Z0-9]+` → `_`, takes an 8-char SHA1, then either PUTs to `MediaServerUpload` with basic auth or
  writes to `MediaDownloadPath`, building `durl := MediaServerDownload + "/" + sha1sum + "/" + fi.Name`
  ([gateway/handlers.go](https://raw.githubusercontent.com/42wim/matterbridge/master/gateway/handlers.go)).
  The FAQ confirms that for Telegram *"images/stickers/files are from non-public url's, you'll need to setup
  a mediaserver."* **This is the largest hidden infrastructure dependency in the project.**
- **You must choose between correct threading and correct attribution.** The FAQ's workaround for Discord
  replies forcing the bot identity is `PreserveThreading=false`
  ([FAQ wiki](https://github.com/42wim/matterbridge/wiki/FAQ)).

---

## Matrix application services and mautrix `bridgev2`

The Matrix appservice spec plus `mautrix/go`'s second-generation bridge framework. Included because it is
the **only** system surveyed with a real cross-channel identity model, and because its capability design is
the best answer anywhere to requirement (b).

### 1. Plugin boundary

Two nested boundaries.

**Outer: an HTTP service the homeserver pushes to.** Registration is YAML
([Application Service API spec](https://spec.matrix.org/latest/application-service-api/)): `id`
("A unique, user-defined ID of the application service which will never change"), `url` ("Optionally set to
null if no traffic is required"), `as_token` (appservice → homeserver), `hs_token` (homeserver →
appservice), `sender_localpart`, and `namespaces` with `users`/`aliases`/`rooms`, each an array of
`{exclusive: bool, regex: "..."}`.

Delivery is `PUT /_matrix/app/v1/transactions/{txnId}` carrying `events`, plus an optional `ephemeral`
stream (`m.presence`, `m.typing`, `m.receipt`) **gated behind `receive_ephemeral`**. The homeserver "must
maintain a queue of transactions" with retry, **using `txnId` for idempotency**. Two things port directly:
**at-least-once delivery with an explicit dedupe key**, and **making the noisy ephemeral stream opt-in so a
send-only adapter is not spammed with typing notifications.**

**Inner: a Go interface pair**, and the split is the lesson
([bridgev2/networkinterface.go](https://raw.githubusercontent.com/mautrix/go/main/bridgev2/networkinterface.go)):

```go
type NetworkConnector interface {
	Init(*Bridge)
	Start(context.Context) error
	GetName() BridgeName
	GetCapabilities() *NetworkGeneralCapabilities
	GetConfig() (example string, data any, upgrader configupgrade.Upgrader)
	LoadUserLogin(ctx context.Context, login *UserLogin) error
	GetLoginFlows() []LoginFlow
	CreateLogin(ctx context.Context, user *User, flowID string) (LoginProcess, error)
	...
}

type NetworkAPI interface {
	Connect(ctx context.Context)
	Disconnect()
	IsLoggedIn() bool
	LogoutRemote(ctx context.Context)
	IsThisUser(ctx context.Context, userID networkid.UserID) bool
	GetChatInfo(ctx context.Context, portal *Portal) (*ChatInfo, error)
	GetUserInfo(ctx context.Context, ghost *Ghost) (*UserInfo, error)
	GetCapabilities(ctx context.Context, portal *Portal) *event.RoomFeatures
	HandleMatrixMessage(ctx context.Context, msg *MatrixMessage) (*MatrixMessageResponse, error)
}
```

**`NetworkConnector` is the adapter *type*** — config, login flows, bridge-wide capabilities.
**`NetworkAPI` is one authenticated *session*** — one user's Discord login. Matterbridge conflates these
into one struct, which is exactly why it cannot model "Tim's Slack account" separately from "the Slack
adapter". **We will have the same problem the first time one agent needs two Discord accounts, or two agents
share one.**

### 2. Capability negotiation — the best answer found anywhere

Two complementary mechanisms, and both are worth taking.

**(i) Capability is which methods you implement.** A connector declares what it can do by satisfying an
optional interface:

```go
type EditHandlingNetworkAPI interface {
	NetworkAPI
	HandleMatrixEdit(ctx context.Context, msg *MatrixEdit) error
}
type ReactionHandlingNetworkAPI interface {
	NetworkAPI
	PreHandleMatrixReaction(ctx, msg *MatrixReaction) (MatrixReactionPreResponse, error)
	HandleMatrixReaction(ctx, msg *MatrixReaction) (*database.Reaction, error)
	HandleMatrixReactionRemove(ctx, msg *MatrixReactionRemove) error
}
type TypingHandlingNetworkAPI interface { NetworkAPI; HandleMatrixTyping(...) error }
type ReadReceiptHandlingNetworkAPI interface { NetworkAPI; HandleMatrixReadReceipt(...) error }
type RedactionHandlingNetworkAPI interface { NetworkAPI; HandleMatrixMessageRemove(...) error }
type IdentifierResolvingNetworkAPI interface {
	NetworkAPI
	ResolveIdentifier(ctx, identifier string, createChat bool) (*ResolveIdentifierResponse, error)
}
type BackfillingNetworkAPI interface { NetworkAPI; FetchMessages(...) (*FetchMessagesResponse, error) }
```

plus `RoomNameHandling…`, `RoomAvatarHandling…`, `RoomTopicHandling…`, `MembershipHandling…`,
`PowerLevelHandling…`, `PollHandling…`, `ChatViewing…`, `DeleteChatHandling…`.

**The minimum viable adapter is `NetworkAPI` alone: receive, and send one message. Everything else is
opt-in.** This is the same idea as OpenClaw's optional adapter slots, arrived at independently, and it is
the one to copy. In stdlib Python it is `typing.Protocol` with `@runtime_checkable` and `isinstance`, or
plain `hasattr` — no machinery at all.

**(ii) A runtime, per-destination capability document.** `GetCapabilities(ctx, portal) *event.RoomFeatures`
([event/capabilities.d.ts](https://raw.githubusercontent.com/mautrix/go/main/event/capabilities.d.ts)):

```typescript
export interface RoomFeatures {
	formatting?: Record<FormattingFeature, CapabilitySupportLevel>
	file?: Record<CapabilityMsgType, FileFeatures>
	max_text_length?: integer
	thread?: CapabilitySupportLevel
	reply?: CapabilitySupportLevel
	edit?: CapabilitySupportLevel
	edit_max_count?: integer
	edit_max_age?: seconds
	delete?: CapabilitySupportLevel
	delete_max_age?: seconds
	reaction?: CapabilitySupportLevel
	reaction_count?: integer
	allowed_reactions?: string[]
	custom_emoji_reactions?: boolean
	poll?: CapabilitySupportLevel
	poll_max_options?: number
	...
}

export enum CapabilitySupportLevel {
	Rejected = -2,
	Dropped = -1,
	Unsupported = 0,
	PartialSupport = 1,
	FullySupported = 2,
}
```

Two ideas here beat everything else in this page.

**`CapabilitySupportLevel` is five-valued, not boolean.** `Rejected` (-2) means "I will refuse and error";
`Dropped` (-1) means "I will accept and silently discard"; then `Unsupported`, `PartialSupport`,
`FullySupported`. **Matterbridge's entire failure mode is that everything is implicitly `Dropped` with no way
to find out.** The distinction between *rejected loudly* and *dropped quietly* is what lets a caller decide
whether to degrade or to fail, and a boolean cannot express it.

**Quantitative caps sit alongside the boolean ones** — `max_text_length`, `edit_max_count`, `edit_max_age`,
`delete_max_age`, `reaction_count`, `allowed_reactions[]`. For our channels these are the fields that
actually decide behaviour: SMS is `max_text_length: 160`; email is `edit: Unsupported`,
`reaction: Unsupported`, `thread: PartialSupport` (via `In-Reply-To`); Discord DM is `edit: FullySupported`
with a large `edit_max_count`. **"Can this channel stream?" is not a flag — it is
`edit >= PartialSupport && edit_max_count > n`.** That is requirement (b), computed rather than declared
twice.

These are published **as a Matrix state event in the room**, so clients adapt their UI from the same data
the bridge uses. Capability as data on the wire, not an internal check.

*(This replaced an earlier `*bridgev2.NetworkRoomCapabilities`; the current interface returning
`*event.RoomFeatures` was read directly, the changeover date was not verified from a primary source —
mentioned in [mau.fi's Twilio bridge walkthrough](https://mau.fi/blog/megabridge-twilio/).)*

### 3. Identity — three persisted roles

This is the part nothing else has.

**Ghosts — deterministic virtual users for remote humans.** The appservice claims an *exclusive namespace*
of Matrix user ids; the spec says exclusive namespaces "should begin with an underscore after the sigil",
and an exclusive namespace "prevents humans and other application services from creating/deleting entities
in that namespace", returning `M_EXCLUSIVE` on violation. mautrix-discord sets
`username_template: discord_{{.}}` where `{{.}}` is the Discord user id
([example-config.yaml](https://raw.githubusercontent.com/mautrix/discord/main/example-config.yaml)). So
Tim-on-Discord becomes a real, addressable, mentionable entity whose id is **derived deterministically from
the remote id** — where Matterbridge produces the string `[discord] <Tim>`, Matrix produces something you can
DM, mention, ban and attach a profile to.

**The tables.** The concrete schema is the most directly transcribable artifact in this whole page
([mautrix-discord `00-latest-revision.sql`](https://raw.githubusercontent.com/mautrix/discord/main/database/upgrades/00-latest-revision.sql)):

```sql
CREATE TABLE puppet (            -- a remote person we do not control
    id TEXT PRIMARY KEY,         -- Discord user ID
    name TEXT NOT NULL, avatar TEXT NOT NULL, avatar_url TEXT NOT NULL,
    global_name TEXT NOT NULL DEFAULT '', username TEXT NOT NULL DEFAULT '',
    is_bot BOOLEAN NOT NULL DEFAULT false, is_webhook BOOLEAN NOT NULL DEFAULT false,
    custom_mxid TEXT,            -- <-- the double-puppet link
    access_token TEXT            -- <-- the real human's own credential
);

CREATE TABLE "user" (            -- the real human
    mxid TEXT PRIMARY KEY,
    dcid TEXT UNIQUE,            -- their Discord ID
    discord_token TEXT,
    management_room TEXT, space_room TEXT, dm_space_room TEXT
);

CREATE TABLE message (
    dcid TEXT, dc_attachment_id TEXT, dc_chan_id TEXT, dc_chan_receiver TEXT,
    dc_sender TEXT NOT NULL, timestamp BIGINT NOT NULL,
    mxid TEXT NOT NULL UNIQUE,   -- <-- the cross-platform id map, persisted
    PRIMARY KEY (dcid, dc_attachment_id, dc_chan_id, dc_chan_receiver)
);

CREATE TABLE reaction (
    dc_chan_id TEXT, dc_chan_receiver TEXT, dc_msg_id TEXT, dc_sender TEXT,
    dc_emoji_name TEXT,
    mxid TEXT NOT NULL UNIQUE,
    PRIMARY KEY (dc_chan_id, dc_chan_receiver, dc_msg_id, dc_sender, dc_emoji_name)
);
```

Note `message.mxid` and `reaction.mxid` are **`UNIQUE` columns in a durable table** — the same job
Matterbridge does in a 5000-entry LRU that forgets. And note `reaction`'s composite primary key
`(channel, message, sender, emoji)`: that is the natural key for reaction identity, it is not obvious, and
it is worth copying verbatim.

The generic v2 form is the shape to steal for people
([userlogin.go](https://raw.githubusercontent.com/mautrix/go/main/bridgev2/database/userlogin.go)):

```go
type UserLogin struct {
	BridgeID      networkid.BridgeID
	UserMXID      id.UserID              // the real human
	ID            networkid.UserLoginID  // ONE remote account
	RemoteName    string
	RemoteProfile status.RemoteProfile
	Metadata      any
}
```

with `GetAllForUser()`. **One `UserMXID` → many `UserLogin`s.** That is literally requirement (c):
`person(id) ← account(person_id, adapter, remote_id, …)`. The `ghost` table
([ghost.go](https://raw.githubusercontent.com/mautrix/go/main/bridgev2/database/ghost.go)) carries
`bridge_id, id, name, avatar_*, is_bot, identifiers, extra_profile, metadata` keyed
`WHERE bridge_id=$1 AND id=$2`, where `identifiers` is a list field — *(inferred: this is where alternate
handles like a phone number or email for the same remote user go; the code using it was not read)*.

**Double puppeting — how a real human proves an account is theirs.**
([double-puppeting.md](https://raw.githubusercontent.com/mautrix/docs/master/bridges/general/double-puppeting.md)):

> "By giving the bridge access to your Matrix account, you can replace the Matrix ghost of your remote
> account."

The automatic method registers a second appservice with `url: null` — *"since the homeserver shouldn't push
events"*; it exists only to issue tokens — with a namespace regex covering the whole domain, then:

```yaml
double_puppet:
  secrets:
    your.domain: "as_token:meow"
```

This works because of the spec's **masquerading** mechanism: the appservice passes `as_token` as
`access_token` plus `?user_id=@_irc_user:example.org`, and the homeserver acts as that user provided it is
in the registered namespace. **A namespace-wide appservice is "impersonate any local user", which is why it
needs homeserver admin** — and why it cannot be used for accounts on someone else's server, where "manual
login is the only option" (the human obtains a token themselves and sends `login-matrix <token>` to the
bridge bot).

**The transferable structure is the three roles**: the *bot* (`sender_localpart`), *ghosts* (deterministic
virtual users for remote humans we do not control), and *double puppets* (an account the human has proven
they own by handing over a credential). Matterbridge has only the first. **We need all three, and the proof
step must exist in the UX, because ownership cannot be inferred from display names** — Matterbridge tried
and produced `{NOPINGNICK}`.

**And the fallback when identity is unknown couples (a) to (b).** In relay mode, messages from
unauthenticated users go out through a designated relay login with a displayname prefix — i.e. it degrades
exactly to the Matterbridge model. Critically
([relay-mode.md](https://raw.githubusercontent.com/mautrix/docs/master/bridges/general/relay-mode.md)):

> "reactions from relayed users will not be bridged at all, because the bot wouldn't be able to bridge
> sender info nor multiple reactions of the same emoji."

**A destination's capability set is a function of whether identity is linked.** Model capability as
`f(adapter, destination, identity_state)`, not `f(adapter)`.

### 4. Authorization

A `permissions` map keyed by `*` (everyone), a **domain**, or an **individual id**, with three levels
([mautrix-discord example-config.yaml](https://raw.githubusercontent.com/mautrix/discord/main/example-config.yaml)):

| level | grants |
|---|---|
| `relay` | relaybot only — your messages are relayed via someone else's login; you cannot log in |
| `user` | may use the bridge and log in |
| `admin` | administration tools as well |

Defaults are `relay` for `*`, `user` for the local domain, `admin` for named accounts. Setting a relay is
`admin_only: true` by default. **Most-specific-key-wins over `*` < domain < exact id** is clean and is a
three-line dict lookup in Python. *(The config schema and prose were read; the enforcement site in code was
not — inferred that it is checked against the sender id on inbound.)*

Note the `relay` level in particular: it is a distinct tier for **"I know who you are well enough to carry
your text, but not well enough to attribute it"**, which is a genuinely useful third state between denied
and allowed, and matches how an unlinked human first appears.

### 5. Outbound addressing

Not an address — a **portal**. Every remote chat gets a persistent local room, keyed
`(dcid, receiver)`: the remote channel id plus **which user's login it was seen through**, so two users
bridging the same DM do not collide. For originating *new* conversations there is
`ResolveIdentifier(ctx, identifier string, createChat bool)` on the optional
`IdentifierResolvingNetworkAPI` — **free text (a phone number, a username, an email) resolved by the adapter
into a chat.** That is the closest anything surveyed comes to requirement (e), and note that it is optional:
adapters that cannot originate conversations simply do not implement it.

**`(remote_chat_id, receiver_login_id) → local_conversation_id` is a better addressing primitive than
Matterbridge's `account:channel` string**, because it survives multiple accounts on one platform.

### 6. Setup UX — the best abstraction found

Phase one is operator-only and once: generate a registration file, copy it into the homeserver config,
restart both. Phase two is per user, per network, and is **data-driven**:

```go
func (tc *TwilioConnector) GetLoginFlows() []bridgev2.LoginFlow {
	return []bridgev2.LoginFlow{{
		Name:        "Auth token",
		Description: "Log in with your Twilio account SID and auth token",
		ID:          "auth-token",
	}}
}
```

with `CreateLogin(ctx, user, flowID) (LoginProcess, error)` returning a stepwise process, in **three step
types — user input, cookies/webview, and display-and-wait** (the last covers QR codes and "approve on your
phone"), carrying intermediate state across `SubmitUserInput` calls
([mau.fi Twilio walkthrough](https://mau.fi/blog/megabridge-twilio/)).

**This makes "connect Discord" a generic wizard the core renders from adapter-supplied data**, rather than
per-adapter README prose (Matterbridge) or a bespoke form. Three step types covers every real case: token
paste (Discord bot, Slack `xoxb-`), OAuth redirect (webview), QR/device approval (WhatsApp). In a stdlib
Python CLI, *user input* and *display-and-wait* are trivial; *webview* is the one to punt on — which is
exactly the one that needs an OAuth callback server we cannot have.

### 7. What they got wrong

The troubleshooting FAQ is a catalogue of the complexity tax
([troubleshooting.md](https://raw.githubusercontent.com/mautrix/docs/master/bridges/general/troubleshooting.md)):
the bot silently not accepting invites because "the homeserver may not be reaching the appservice"; token
rejection from forgetting to restart one of two services after regenerating tokens; encryption warnings
("Encrypted by deleted session") that "may persist until proper delegation specs are implemented"; DMs
rendering as rooms because Matrix stores DM-ness separately; advice to use separate databases per bridge to
avoid foreign-table conflicts. Double puppeting specifically requires homeserver admin — a hard blocker on
someone else's server — and the older shared-secret-login mechanism was **removed**, breaking existing
setups.

**Matrix buys a real identity model and pays for it with an enormous operational surface.** Every capability
gained is a config file, a token pair, a restart, and a class of silent failure. That trade is the thing to
be deliberate about: we want the *tables*, not the *appservice*.

---

## Zulip

Included for one specific idea — **send-only as an enforced principal type rather than a flag** — and for
the cleanest separation of transport from handler in the survey.

### 1. Plugin boundary

Two boundaries, and a bridge between them.

**(a) Outgoing webhook: an HTTP service you host.** Zulip POSTs
([outgoing webhook payload](https://zulip.com/api/outgoing-webhook-payload)) an envelope carrying
`bot_email`, `bot_full_name`, `data`, `token`, `trigger`, and a full `message` object. Two design points:
the envelope **reuses the platform's own canonical message schema** rather than inventing a bridge schema —
the opposite of Matterbridge's flattened struct — and `data` is a **pre-extracted, mention-stripped
convenience field**, separate from `message.content` and `message.rendered_content`, so a trivial bot never
parses anything. **Our inbound envelope probably wants both: a normalized minimal view and a `raw`
passthrough.**

`trigger` is only `direct_message` or `mention` (renamed from `private_message` in Zulip 8.0, feature level
201) — deliberately tiny.

**(b) `zulip_bots`: an imported Python class**, and the contract is an injected capability object rather
than a return value
([zulip_bots/lib.py](https://raw.githubusercontent.com/zulip/python-zulip-api/main/zulip_bots/zulip_bots/lib.py)):

```python
class AbstractBotHandler(Protocol):
    user_id: int
    email: str
    full_name: str

    @property
    def storage(self) -> BotStorage: ...
    def identity(self) -> BotIdentity: ...
    def react(self, message: Dict[str, Any], emoji_name: str) -> Dict[str, Any]: ...
    def send_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...
    def send_reply(self, message: Dict[str, Any], response: str,
                   widget_content: Optional[str] = None) -> Optional[Dict[str, Any]]: ...
    def update_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]: ...
    def get_config_info(self, bot_name: str, optional: bool = False) -> Dict[str, str]: ...
    def quit(self, message: str = "") -> None: ...
```

invoked as `message_handler.handle_message(message=message, bot_handler=restricted_client)`. Note it is a
`typing.Protocol` — **structural, not nominal**, which is the stdlib Python mechanism for exactly the
optional-interface pattern mautrix gets from Go. And note the inversion: **the bot's ability to reply, edit
and react is expressed as which methods exist on the injected handler**, not as flags it inspects.

**(c) The bridge: the Botserver.** It does `event = request.get_json(force=True)`, matches
`event["bot_email"]`, checks `if bot_config["token"] != event["token"]: raise Unauthorized(...)`, and calls
**the same** `message_handler.handle_message(...)`
([zulip_botserver/server.py](https://raw.githubusercontent.com/zulip/python-zulip-api/main/zulip_botserver/zulip_botserver/server.py)).
**One handler contract serves both the long-polling bot and the HTTP-webhook bot** — the adapter *transport*
is decoupled from the handler contract. That is the structurally cleanest idea Zulip has for us, because our
channels split exactly this way: some poll, some receive webhooks, some only send.

*(The token check is a plain `!=`, not constant-time — in stdlib Python this is `hmac.compare_digest`.)*

### 2. Capability negotiation

Zulip is single-platform, so it has no cross-platform capability problem — but it does have a capability
model, and it is expressed as **bot type** ([bots overview](https://zulip.com/help/bots-overview)):

| type | can |
|---|---|
| Generic | act as a normal user, API-only, listen to channels |
| **Incoming webhook** | **"limited to only sending messages into Zulip"** |
| Outgoing webhook | receive messages by HTTP POST when mentioned or DM'd |

with the guidance to use "the most limited bot type" because "anyone with the bot's API key can do anything
the bot can." **Send-only is a server-enforced principal type, not a convention.** For our email and SMS and
webhook channels that is the right framing: a send-only channel should be *unable* to be wired for inbound,
not merely documented as not supporting it.

### 3. Identity

One realm, so there is no cross-platform question. The relevant find is `can_forge_sender`, an
administrator-granted permission letting a bot "send messages on behalf of multiple users", described as
requiring manual configuration. **This is Zulip's ghost-user equivalent, and it is deliberately a named,
privileged, scary capability rather than an ambient feature.** If our gateway ever posts *as* Tim rather
than *about* Tim, that should be a named privilege on the same footing.

### 4. Authorization

Bots have **owners**, and **inherit their owner's sending permissions**; they can be given channel
permissions like a regular user; enforcement is server-side in Zulip's ordinary user permission system.
The design lesson is worth stating flatly: **do not build a parallel permission system for adapters — make
the adapter's identity a principal in the system you already have.** Any bot added is "visible and available
for anyone to use", and by default anyone other than guests may add one.

### 5. Outbound addressing

`message.type` is `stream` or `private`; a stream message carries `stream_id` + `subject` (the docs call
`subject` a "legacy field name" for topic), a DM carries `display_recipient`. So the address is
`(type, stream_id | recipients, topic)`.

But the interesting one is `send_reply(message, response)`, which **sidesteps addressing entirely by
echoing the inbound envelope**. *Reply-by-envelope rather than reply-by-address* is a very good default for
a multi-channel gateway: the overwhelmingly common case — answer the person who just spoke, wherever they
spoke — should require no address at all, and should be impossible to misroute.

For incoming webhooks the address is instead **encoded in the URL** — `api_key=…` plus `stream` ("either the
channel ID or the URL-encoded channel name") and `topic`
([incoming-webhooks-overview.md](https://raw.githubusercontent.com/zulip/zulip/main/docs/webhooks/incoming-webhooks-overview.md)).

### 6. Setup UX

Create a bot in Zulip settings, pick the bot type, supply an endpoint URL for outgoing webhooks; Zulip
generates the `token` and `api_key`. Credentials land in a **`zuliprc`** file or the env vars
`ZULIP_EMAIL`, `ZULIP_API_KEY`, `ZULIP_SITE`; third-party bot config goes in a separate `--bot-config-file`
([running bots](https://zulip.com/api/running-bots)). Nothing to click in Discord or Slack, because Zulip is
the platform — which is precisely why its setup is the easiest here and why that ease does not transfer.

### 7. What they got wrong

Honestly, little that bites — the framework is narrow enough not to have Matterbridge's failure surface.
The real limits are structural: `trigger` fires only on mention or DM, so an outgoing-webhook bot cannot
passively observe a channel; and the bot API key is a full principal ("anyone with the bot's API key can do
anything the bot can"). *(A current maintenance-status statement for `python-zulip-api` was looked for and
not found — gap.)*

### Gaps recorded rather than guessed

The `@webhook_view` decorator's exact signature and the example view code could not be retrieved:
`zulip.com/api/incoming-webhooks-overview` 301s to readthedocs, which returned HTTP 429 twice, and the
GitHub markdown source does not contain the sample.

---

## Apprise

`caronc/apprise` — a Python notification fan-out library, 155 service plugins, **send-only**. Included
because it is the direct answer to the "email only gets the final message" half of requirement (b), because
its URI scheme is the most-copied addressing design in the field, and because it is stdlib-adjacent Python
we can read as a peer rather than translate from Go.

Source files read at HEAD of `master` on 2026-08-05: `apprise/plugins/base.py`, `apprise/url.py`,
`apprise/manager.py`, `apprise/apprise.py`, `apprise/config/base.py`, `apprise/common.py`, `apprise/cli.py`,
`apprise/decorators/notify.py`, and the `discord`, `slack`, `twilio`, `telegram` and `email` plugins.

### 1. Plugin boundary

**An imported Python class in the same process. There is no manifest file at all** — metadata is class
attributes. Discovery is filesystem plus `importlib` scanning under three hard naming rules
(`apprise/manager_plugins.py`):

```python
class NotificationManager(PluginManager):
    name = "Notification Plugin"
    fname_prefix = "Notify"
    _id = "plugins"
    module_name_prefix = f"apprise.{_id}"
    module_path = join(abspath(dirname(__file__)), _id)
    module_filter_re = re.compile(
        r"^(?P<name>" + fname_prefix + r"(?!Base|Format|ImageSize|Type)[A-Za-z0-9]+)$")
```

So `apprise/plugins/discord.py` must contain a class named `NotifyDiscord`; the loader additionally requires
`hasattr(plugin, "app_id")`, then registers the schemes the class claims. **Collision handling is
first-wins-plus-error-log, not an exception** (`apprise/manager.py`):

```python
for schema in schemas:
    if schema in self._schema_map:
        logger.error(f"{self.name} schema ({schema}) mismatch detected - ...")
        continue
    self._schema_map[schema] = plugin
```

The base class is `NotifyBase(URLBase)`. Identity and capability live as class attributes; the methods a
plugin must implement are only three:

```python
def send(self, body: str, title: str = "",
         notify_type: NotifyType = NotifyType.INFO, **kwargs: Any) -> bool:
    """Should preform the actual notification itself."""
    raise NotImplementedError("send() is not implemented by the child class.")

@staticmethod
def parse_url(url: str, verify_host: bool = True,
              plus_to_space: bool = False) -> Optional[dict[str, Any]]: ...

def url(self, privacy=False, *args, **kwargs): ...
```

`parse_url` returns a dict that is splatted into `__init__`; `url()` must round-trip — emit a URL that
re-instantiates the same object, with `privacy=True` masking secrets. **The real `send()` signature is not
uniform**: Discord widens it with `attach: list[AttachBase] | None = None`, Slack with `body_format=None`.
It is a soft contract enforced by convention only.

**The second, lighter boundary is the one to steal.** For user-supplied plugins there is a decorator, and a
`.py` file dropped into `~/.apprise/plugins` (`apprise/decorators/notify.py`):

```python
@notify(on="foobar", name="My Foobar Process")
def your_action(body, title, notify_type, body_format, meta, attach, *args, **kwargs):
    ...
```

> "Your wrapper should return True if processed the send() function as you expected and return False if
> not. If nothing is returned, then this is treated as a success (True)."

**Full class contract for first-party adapters, one decorated function for third-party ones** is a good
two-tier answer to "let third parties write their own adapter" without making them learn the whole object.

### 2. Capability negotiation

**Purely declared, statically, as class attributes; nothing is discovered from the remote service.** The
caller never asks "does this support attachments" — the framework reads the attribute and adapts. This is
the richest capability *vocabulary* in the survey:

| Attribute | Default | Meaning | Real values |
|---|---|---|---|
| `notify_format` | `TEXT` | what the service natively wants | Slack `MARKDOWN`, email `HTML`, Telegram `HTML` |
| `attachment_support` | `False` | gate for attachments | Discord/Slack/Telegram/email `True` |
| `title_maxlen` | `250` | **`0` means no title support at all** | Twilio `0`, Telegram `0` |
| `body_maxlen` | `32768` | character cap | Discord `2000`, Telegram `4096`, Slack `35000` |
| `body_max_line_count` | `0` | `0` = disabled | |
| `request_rate_per_sec` | `5.5` | client-side throttle | Discord `0` — reads `X-RateLimit-*` instead |
| `overflow_mode` | `UPSTREAM` | `UPSTREAM` / `TRUNCATE` / `SPLIT` | |
| `overflow_amalgamate_title` | `False` | title counts against `body_maxlen` | Discord `True` |

```python
class OverflowMode(str, Enum):
    UPSTREAM = "upstream"   # Send as is; let the upstream server decide
    TRUNCATE = "truncate"   # Always truncate when it exceeds the maximum
    SPLIT = "split"         # Split into multiple smaller messages
```

**The negotiation happens once, in the base class**, in `NotifyBase._apply_overflow()`, which returns a
**list** of `{title, body}` dicts — one logical message becomes N platform messages. The title-folding is
the part to copy verbatim:

```python
# If the service does not support a title, amalgamate into body
if self.title_maxlen <= 0 and len(title) > 0:
    if self.notify_format == NotifyFormat.HTML:
        body = (f"<{self.default_html_tag_id}>{title}"
                f"</{self.default_html_tag_id}><br />\r\n{body}")
    elif (self.notify_format == NotifyFormat.MARKDOWN
          and body_format in (NotifyFormat.TEXT, NotifyFormat.HTML)):
        title = title.lstrip("\r\n \t\v\f#-")
        if title:
            body = f"# {title}\n{body}"
    else:
        body = f"{title}\r\n{body}"
    title = ""
```

**`title_maxlen = 0` as the sentinel for "this channel has no concept of a subject line"** is elegant, and
directly applicable to SMS and WhatsApp. The shared base owns all format, length and title adaptation; a
plugin declares numbers and gets the behaviour. That is precisely OpenClaw's `limits` idea, arrived at
independently, in Python, seven years earlier.

Plugins also declare their own pip dependencies and self-disable if the import fails —
`requirements: {"packages_required": [...], "packages_recommended": [...]}` plus `enabled` / `enable()` /
`disable()` / `runtime_deps()`. A symptom of 155 plugins, not a cure.

### 3. Identity

**None. A target is purely a per-service address, and there is no cross-channel person object.** Verified by
absence: grepping `plugins/base.py` and `apprise.py` for `owner|allowed_user|authoriz|permission` returns
nothing. There is no contact, person or recipient registry anywhere.

The only cross-service grouping primitive is the **tag** — a free-text label on a URL with no semantics. You
can approximate "notify Tim" by tagging `tim` on his `mailto://`, `discord://` and `twilio://` URLs, **but
Apprise has no idea those are the same human**; it is a routing coincidence, not a fact it knows. `groups`
in the config are aliases over *tags*, not over URLs — one further layer of indirection, still with no
person in it.

`url_identifier` is identity of a *connection*, not of a person, and its documented rule is explicit —
"**Include** scheme or protocol, credentials, and upstream connection identity. **Exclude** targets
(channels, recipients, endpoints)" ([appriseit.com/library/plugin](https://appriseit.com/library/plugin/)).

### 4. Authorization

**None.** No owner concept, no allowlist, no per-caller policy — verified by the same grep. Whoever can call
`Apprise.notify()` or read the config file can send to everything in it. The documentation's only advice is
to "lock all of your tokens, passwords and usernames in a yaml file that has permissions that only you can
access" ([config wiki](https://github.com/caronc/apprise/wiki/config)). Tag filtering is a *routing* filter,
not a security boundary — nothing prevents `tag="all"`.

### 5. Outbound addressing — the URI scheme

Apprise's whole design collapses to one idea: **a single URI string is simultaneously the plugin selector,
the credential store, the target list and the option bag.** There is no separate config object.

```
{schema}://{user}:{password}@{host}:{port}/{target1}/{target2}/...?{opt}={val}&...
```

| Element | Role | Example |
|---|---|---|
| `schema` | picks the plugin class via `_schema_map` | `discord`, `slack`, `mailto`, `tgram`, `twilio` |
| userinfo | credentials — or, abusively, a bot display name | `twilio://{SID}:{Token}@…`, `discord://{botname}@…` |
| host | server, or the leading credential token, or the sender | `mailto://user:pass@gmail.com` |
| path segments | **the target list** | `/#channel1/#channel2`, `/18005551223` |
| query string | per-send options declared in `template_args` | `?format=markdown&overflow=split&tts=no` |
| `?:key=value` | free-form tokens via `template_kwargs` prefix | `?:service=api-gateway` |

Verified examples, read from the plugin source headers and the service docs:

```
# Discord — note the native webhook URL is accepted directly
https://discord.com/api/webhooks/417429632418316298/JHZ7lQml277CDHmQKMHI8qBe7bk2ZwO5UKjCiOAF7711o33MyqU344Qpgv7YTpadV_js
discord://WEBHOOK_ID/WEBHOOK_TOKEN
discord://{botname}@{WebhookID}/{WebhookToken}/
discord://4174216298/JHMHI8qBe7bk2ZwO5U711o3dV_js?format=markdown

# Slack — webhook or bot token, three target sigils: #channel, @user_id, +encoded_id
slack:///T1JJ3T3L2/A1BRTD4JD/TIiajkdnlazkcOXrIdevi7F/#nuxref
slack://xoxb-1234-1234-4ddbc191d40ee098cbaae6f3523ada2d/#general
slack://{botname}@{tokenA}/{tokenB}/{tokenC}/@{user_id}/#{channel}/+{encoded_id}
slack://xoxb-.../%23ops/          # '#' must be percent-encoded in some contexts

# Email — stdlib smtplib underneath
mailto://user:pass@gmail.com
mailtos://user:pass@host:port/to@example.com?cc=…&bcc=…&from=…&mode=starttls

# Telegram
tgram://{bot_token}
tgram://{bot_token}/{targets}

# Twilio / SMS — note the 'w:' sigil for WhatsApp
twilio://AC735c307c62944b5a:e29dfbcebf390dee9@19005559999/18005551223
twilio://AC735c307c62944b5a:e29dfbcebf390dee9@19005559999/18005551223?method=call
twilio://AC735c307c62944b5a:e29dfbcebf390dee9@19005559999/w:15551233456
```

The per-plugin metadata that makes this work is declarative
(`apprise/plugins/discord.py`):

```python
templates = (
    "{schema}://{webhook_id}/{webhook_token}",
    "{schema}://{botname}@{webhook_id}/{webhook_token}",
)
template_tokens = dict(NotifyBase.template_tokens, **{
    "botname":       {"name": _("Bot Name"), "type": "string", "map_to": "user"},
    "webhook_id":    {"name": _("Webhook ID"), "type": "string",
                      "private": True, "required": True},
    "webhook_token": {"name": _("Webhook Token"), "type": "string",
                      "private": True, "required": True},
})
template_args = dict(NotifyBase.template_args, **{
    "tts":    {"name": _("Text To Speech"), "type": "bool", "default": False},
    "thread": {"name": _("Thread ID"), "type": "string"},
    "url":    {"alias_of": "href"},
    ...
})
template_kwargs = {"tokens": {"name": _("Template Tokens"), "prefix": ":"}}
```

Type grammar is `((choice|list):)?(string|bool|int|float)`; directives are `name, type, required, private,
default, values, min, max, regex, delim, prefix, map_to, alias_of`. `map_to` renames a URL token to an
`__init__` kwarg, `alias_of` makes a synonym, `private: True` marks a secret for masking. Apprise's own unit
tests enforce that every `template_tokens` entry maps to an `__init__` arg and that `url()` output re-parses
— **the round-trip is a tested invariant, not a hope.**

**`parse_native_url()` is the single highest-leverage UX idea in the survey** (`plugins/base.py`):

> "This is a base class that can be optionally over-ridden by child classes who can build their Apprise URL
> based on the one provided by the notification service they choose to use. The intent of this is to make
> Apprise a little more userfriendly to people who aren't familiar with constructing URLs and wish to use
> the ones that were just provided by their notification service."

That is why pasting a raw `https://discord.com/api/webhooks/…` or `https://hooks.slack.com/services/…`
just works — each plugin gets a chance to claim an arbitrary vendor URL and rewrite it into its own scheme.
It costs almost nothing and removes an entire class of setup error.

**Fan-out** is by tag, with top-level OR and nested AND (`apprise.py`):

```
tag="tagA, tagB"                = tagA or tagB
tag=['tagA', 'tagB']            = tagA or tagB
tag=[('tagA', 'tagC'), 'tagB']  = (tagA and tagC) or tagB
```

Two reserved tags: `MATCH_ALL_TAG = "all"` and `MATCH_ALWAYS_TAG = "always"` (fires regardless of the
filter). `notify()` returns a **tristate** — "True if all notifications were successfully sent, False if
even just one of them fails, and None if no notifications were sent at all as a result of tag filtering."
**"Nothing matched" is distinguishable from "everything failed"**, which a boolean loses and which is
exactly the distinction a scheduled "email me the daily report" needs.

The config file has two formats. TEXT is one regex and its whole grammar is in the docstring
(`config/base.py`):

```
<Tag(s)>=<URL>
<URL>
include <ConfigURL>
<Group(s)>=<Tag(s)>
```

```
desktop=gnome://
tv,kitchen=kodi://user:pass@kitchen.host
user1=mailto://credentials
user2=mailto://credentials
friends = user1, user2          # a group of TAGS, not of URLs
include /etc/apprise/secrets.conf
```

**Any malformed line aborts the entire file** (`return ([], [])`) — a defensible fail-closed choice for a
secrets file, and worth copying. YAML is the other format, and it is the one that needs PyYAML.

### 6. Setup UX

**Two steps: obtain the credential, paste the URL.**

```bash
apprise -vv -t "Task Complete" -b "The backup finished." "discord://webhook_id/webhook_token"
```

No OAuth dance, no callback URL, no daemon, no bot invite — because a Discord *webhook* is not a bot. **That
is the benchmark to beat for requirement (f), and the reason it is achievable is that outbound-only needs no
gateway connection and no privileged intents.** Slack is the same shape in webhook mode; its bot mode needs
the app and the `xoxb-` token.

Secrets live in plaintext in the config file, protected by filesystem permissions alone — across a
**27-path search list** (`~/.apprise`, `~/.apprise.conf`, `~/.apprise.yml`, `~/.config/apprise/…`,
`/etc/apprise/…` and more, in `cli.py`). Do not copy that; pick one path plus an env override.

### 7. What they got wrong

- **Send-only by construction, and structurally unable to grow inbound.** Verified by absence: grepping
  `def (receive|poll|listen|on_message|inbound)` across `plugins/base.py`, `url.py`, `apprise.py` and
  `manager.py` returns **zero hits**. The base class has exactly one verb. Worse, **`send()` returns
  `bool`** — no message id — so you cannot correlate a sent message with anything later, which forecloses
  edits, reactions and threading as well as replies. The lone exception is Telegram's `?detect=`, which
  calls `getUpdates` purely to learn a chat id. *(No maintainer statement or tracking issue for inbound
  support was found; this reads as a settled scope decision, but the absence of complaints was not
  confirmed — gap.)*
- **Credentials in URLs required three separate mechanisms to undo.** `secure_logging` defaults to `True`,
  a `cwe312_url()` sanitizer is applied at every log site, `privacy=False` is a parameter on every `url()`,
  and `"private": True` marks every secret token. **Three redaction mechanisms to undo one design
  decision**, and the failure mode is silent — miss `privacy=True` at one call site and you print a bot
  token.
- **URL encoding is a permanent user-facing wound.** From their own troubleshooting page: "The `&`, `/`, and
  `%` all have extremely different meanings and if they also reside in your password or user-name, they can
  cause quite a troubleshooting mess" … "The `&` causes the shell to execute everything defined before them
  into a background process" ([Troubleshooting wiki](https://github.com/caronc/apprise/wiki/Troubleshooting)).
  Slack channels become `%23ops`.
- **Config and secrets were never separated.** Open requests for env-var interpolation
  ([#1156](https://github.com/caronc/apprise/issues/1156),
  [#1228](https://github.com/caronc/apprise/issues/1228)); the answer remains "chmod the YAML file".
- **SPLIT mode is a footgun, in their own words**: "if you send thousands of log entries… to you via an SMS
  notification service. Be prepared to get hundreds of text messages." Also that splitting is not
  markup-aware — "HTML formatting can break if split/truncate operations cut messages mid-tag".
- **Stringly-typed feature creep.** Current master encodes priority and retry into the tag token itself —
  `"3:endpoint:2"` meaning priority-3 exclusive match with 2 retries — alongside `?:key=value` template
  tokens, `w:` WhatsApp prefixes and Slack's `+`/`#`/`@` sigils. Each is locally reasonable; together the
  "one URL" abstraction has become a small undocumented DSL. **This is what the URI-as-config decision
  costs at maturity.**

### What a stdlib-only Python port cannot take

Mandatory core dependencies are `certifi`, `requests`, `requests-oauthlib`, `click`, `markdown`, `PyYAML`.

- **`requests`** — every HTTP plugin imports it. Replacing with `urllib.request`/`http.client` is doable but
  you re-implement multipart attachment encoding by hand and lose `Session` reuse. Note that the
  `request_rate_per_sec` throttling is Apprise's own code and **ports cleanly**.
- **`PyYAML`** — the entire YAML config format. Stdlib has no YAML parser. But the TEXT format is a single
  regex, and is honestly the better fit for us anyway; `tomllib` (read-only, stdlib) or JSON are the other
  options.
- **`markdown`** — Markdown→HTML body conversion. Without it we are restricted to pass-through formats.
- **`requests-oauthlib`** — any OAuth-flow plugin is off the table.

**The email plugin is the exception that matters: it uses stdlib `smtplib` and `email`**, so an SMTP channel
is genuinely stdlib-clean today. And **no hosted service is assumed anywhere in the library** — Apprise
talks directly to each vendor's API. That is a real strength and the right posture for us.

---

## Home Assistant `notify`

Included for exactly one contrast with Apprise: **HA addresses a registry row with a stable id, where
Apprise addresses a URI value-string.** That single difference is the source of everything HA can do that
Apprise cannot — per-destination ACLs, capability queries from outside the process, group aggregation — and
it is the most consequential design choice on this page for a project with SQLite per agent.

Source read at HEAD of `dev` on 2026-08-05: `components/notify/{__init__,const,legacy,repairs}.py`,
`components/notify/{services.yaml,manifest.json}`, `components/group/notify.py`,
`components/slack/{notify.py,manifest.json}`, `components/telegram_bot/const.py`, `helpers/service.py`.

### 1. Plugin boundary

**A Python module inside `homeassistant/components/<domain>/`, imported in-process, declared by a JSON
manifest** — the manifest being the thing Apprise lacks entirely:

```json
{
  "domain": "slack",
  "name": "Slack",
  "config_flow": true,
  "integration_type": "service",
  "iot_class": "cloud_push",
  "loggers": ["slack"],
  "requirements": ["slack_sdk==3.33.4", "aiofiles==25.1.0"]
}
```

`requirements` is a literal pip list resolved at integration setup; `config_flow: true` means "has a UI
setup wizard"; `iot_class` declares the connectivity model. **`requirements` structurally assumes a package
manager runs at setup time** — the single least portable idea here.

Two generations coexist. **Legacy** is a module-level factory returning a service object, with the contract
written as an explicit `Protocol` (`notify/legacy.py`):

```python
class LegacyNotifyPlatform(Protocol):
    async def async_get_service(self, hass, config, discovery_info=...) -> BaseNotificationService | None: ...
    def get_service(self, hass, config, discovery_info=...) -> BaseNotificationService | None: ...

class BaseNotificationService:
    registered_targets: dict[str, Any]        # name => target

    @property
    def targets(self) -> Mapping[str, Any] | None:
        return None

    def send_message(self, message: str, **kwargs: Any) -> None:
        """kwargs can contain ATTR_TITLE to specify a title."""
        raise NotImplementedError

    async def async_send_message(self, message: str, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(
            partial(self.send_message, message, **kwargs))
```

Note the `kwargs`-only signature — `title`, `target` and `data` are all untyped bag entries, not parameters.
**That is the root of most of the pain in section 7.** Note also the sync/async bridge via
`async_add_executor_job`, which in stdlib Python is `concurrent.futures.ThreadPoolExecutor`.

**Current generation** is `NotifyEntity`, and two of its details are worth taking wholesale
(`notify/__init__.py`):

```python
class NotifyEntityFeature(IntFlag):
    TITLE = 1

class NotifyEntity(RestoreEntity):
    _attr_supported_features: NotifyEntityFeature = NotifyEntityFeature(0)

    def send_message(self, message: str, title: str | None = None) -> None:
        raise NotImplementedError

    @final
    async def _async_send_message(self, **kwargs: Any) -> None:
        """Send a notification message (from e.g., service call).

        Should not be overridden, handle setting last notification timestamp.
        """
        await self.async_send_message(**kwargs)
        self._async_record_notification()
```

**The `@final` template-method wrapper makes per-send bookkeeping impossible for an adapter author to
skip** — the entity's state *is* the last-notified timestamp, persisted across restarts by `RestoreEntity`.
For us the equivalent is: the base class writes the delivery row and the message-id mapping, and the adapter
only ever implements the inner send. An adapter author who forgets cannot break the ledger.

### 2. Capability negotiation

**Declared as an `IntFlag` bitmask published as a state attribute — externally queryable, which Apprise's
class attributes are not.** The UI consumes it directly (`notify/services.yaml`):

```yaml
send_message:
  target:
    entity:
      domain: notify
  fields:
    message: {required: true, selector: {text: }}
    title:
      required: false
      selector: {text: }
      filter:
        supported_features:
          - notify.NotifyEntityFeature.TITLE
```

**But the vocabulary is one bit wide. `NotifyEntityFeature` has exactly one member: `TITLE`.** No
attachment flag, no format declaration, no length limits, no rate limit — against Apprise's ten-plus. And
**there is no truncation or overflow handling anywhere in the notify component**: a 5000-character message
to an SMS integration is that integration's problem. Everything not covered by the one bit falls into an
unvalidated `data: dict`.

Enforcement is a **silent drop**, not an error:

```python
if (title is not None and self.supported_features
    and self.supported_features & NotifyEntityFeature.TITLE):
    kwargs[ATTR_TITLE] = title
```

**The verdict is the design brief for us: HA's capability *mechanism* is better than Apprise's, and its
capability *vocabulary* is far worse.** Take Apprise's attribute set, expressed as HA-style externally
queryable declarations on a registry row.

### 3. Identity

**Also none in `notify`.** HA *has* a `person` integration that unifies one human across device trackers,
and it is **not wired into `notify`** — there is no `notify.person` platform. `notify/const.py` defines and
exports an `ATTR_RECIPIENTS = "recipients"` constant for which **no consumer was found** — *(inferred: a
placeholder for the unbuilt recipient model)*.

The architecture discussion is explicit that this is the unsolved problem, and the quotes are worth having
because they are the exact objections we will face
([architecture discussion #1041](https://github.com/home-assistant/architecture/discussions/1041)):

> "The problem with that is that we don't know all targets before hand in some integrations."

with the one-entity-per-target alternative rejected because "integrations couldn't represent all possible
phone contacts as entities beforehand", and the stated future direction being "a proposal for config
subentries… which can function as a contact registry". There is a separate standing request to
[notify a `person.*` entity](https://github.com/orgs/home-assistant/discussions/793) and have HA infer the
device.

**Status: aspirational, not built — and a project with Home Assistant's resources has been circling it for
two years.** That is a calibration point on requirement (c): it is the genuinely hard part, and nobody has
shipped it. The reason is visible in the quote — the tension between a *contact registry* (few, known,
per-person) and *targets* (many, discovered, per-service).

### 4. Authorization — HA's clear win

Authorization is not in `notify` at all; it is in the core, and `notify` inherits it **because destinations
are entities with ids**. Every service call carries a `context.user_id`, and `helpers/service.py` enforces a
per-entity control policy:

```python
from homeassistant.auth.permissions.const import CAT_ENTITIES, POLICY_CONTROL
...
if not entity_perms(entity_id, POLICY_CONTROL):
    raise Unauthorized(..., permission=POLICY_CONTROL)
```

So "user X may call `notify.send_message` on `notify.slack_ops` but not on `notify.ceo_sms`" is expressible.
**Crucially this only works for the entity generation** — legacy `notify.<service_name>` registrations have
no entity to hang a policy on. *(Inferred: the entity-permission path was read; a legacy call was not traced
end-to-end, but the absence of an entity id makes the bypass structural.)*

**The design lesson is the one to carry into our schema: make every addressable destination a first-class
registry row with a stable id, precisely so there is something to hang an ACL on. A URI string has no
identity to authorize.**

### 5. Outbound addressing

Three layers, oldest to newest.

**Legacy: the service registry *is* the address book.** Each platform registers `notify.<slug>`, and every
entry in `targets` registers an *additional* service (`notify/legacy.py`), so a Slack integration with three
channels yields `notify.slack_ops`, `notify.slack_alerts`, `notify.slack_general`, with stale targets
garbage-collected on re-register.

**The `target:` field**, which is `list[str]` and **completely opaque to the framework**, plus `data` as a
bare unvalidated `dict` (`notify/const.py`):

```python
NOTIFY_SERVICE_SCHEMA = vol.Schema({
    vol.Required(ATTR_MESSAGE): cv.string,
    vol.Optional(ATTR_TITLE): cv.string,
    vol.Optional(ATTR_TARGET): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_DATA): dict,
})
```

A per-target service **overrides** a caller-supplied `target:`. Slack then does the same `#channel`
normalization Apprise does with a sigil, only in Python.

**Entity generation: `target:` is the entity, not the recipient.**

```yaml
actions:
  - action: notify.send_message
    target:
      entity_id: notify.my_device
    data:
      message: The garage door has been open for 10 minutes.
```

**This is the key architectural inversion against Apprise.** Apprise addresses `(plugin, credential,
target)` as one opaque URI; HA addresses a pre-registered entity id and pushes credential and target into
that entity's own config. **An entity id is a primary key you can join on, log against and authorize.
Apprise's URI is a value, not a key.**

**Notify groups** are the best-worked fan-out semantics found. The legacy group deep-merges per-member
default `data` so a member can carry channel-specific defaults the caller may override
(`components/group/notify.py`):

```python
def add_defaults(input_data, default_data):
    for key, val in default_data.items():
        if isinstance(val, Mapping):
            input_data[key] = add_defaults(input_data.get(key, {}), val)
        elif key not in input_data:
            input_data[key] = val
    return input_data
```

and the entity group aggregates capability by **intersection**:

```python
# Support title if all members support it
self._attr_supported_features |= NotifyEntityFeature.TITLE
for entity_id in self._entity_ids:
    state = self.hass.states.get(entity_id)
    if (state is None
        or not state.attributes.get(ATTR_SUPPORTED_FEATURES, 0) & NotifyEntityFeature.TITLE):
        self._attr_supported_features &= ~NotifyEntityFeature.TITLE
        break
```

while availability is a **union** (`any(state != STATE_UNAVAILABLE)`). **Intersect capabilities, union
availability** — that asymmetry is exactly right and it is three lines.

### 6. Setup UX

Slack, from the integration docs: create an app at `api.slack.com/apps`; add **ten scopes** (`chat:write`,
`dnd:read`, `channels:manage`, `channels:read`, `groups:read`, `groups:write`, `im:read`, `im:write`,
`mpim:read`, `mpim:write`, optionally `chat:write.customize`); copy the Bot User OAuth Token; **invite the
bot to each channel** with `/invite @bot`; then paste key and default channel into the HA config flow
([HA Slack docs](https://www.home-assistant.io/integrations/slack/)).

**Ten scopes and a bot invite before a single message sends, against Apprise's two steps.** The difference
is entirely bot-versus-webhook, not framework quality — which is the single most useful setup-UX fact in
this page.

Secrets live in `.storage/core.config_entries` as JSON on disk rather than in a URL — better for logging,
similar at rest. *(Inferred: the `.storage` writer was not read this session.)*

### 7. What they got wrong

- **The legacy→entity migration is the dominant, ongoing complaint, and they built a whole `repairs`
  subsystem for it** — `notify/manifest.json` lists `"dependencies": ["repairs"]` and `notify/repairs.py`
  exists solely to raise `migrate_notify_{domain}_{service_name}` issues with a `breaks_in_ha_version`.
  The dev blog states the consequence plainly: "users will need to use the new `notify.send_message`
  service, so the migration changes will cause automations to break after the deprecation period is over"
  ([dev blog](https://developers.home-assistant.io/blog/2024/04/10/new-notify-entity-platform/)).
- **Concrete breakage**: the Telegram deprecation warning told users to delete their `notify:` config, and
  doing so broke alerts — "Failed to call notify.telegram_bot_xxxx_yyyy, retrying at next notification
  interval" — "because the Notify is not registering a per entity service". **Closed as "not planned"**
  ([core#164855](https://github.com/home-assistant/core/issues/164855)).
- **Groups regressed in the migration.** A developer confirmed "Groups are not supported yet but there's an
  ongoing change for that", and users who had `configuration.yaml` notify groups bundling chat ids had to
  enumerate `notify.telegram_bot_[chatid]_[userid]` entity ids individually
  ([community thread](https://community.home-assistant.io/t/telegram-notify-service-migration-2025-11-not-very-clear/949325)).
- **The new generation cannot express what the old one could** — from the same thread, "You can only use the
  entities with the generic notify action. The telegram actions… require you to use the numeric chat id,
  not the event entity."
- **`data:` is an unresolved architectural argument**: "I don't think we should add any parameters that
  allows non typed non validated values to the new action service." The result is that every non-text
  capability — attachments, blocks, threads, buttons — is stranded, waiting either for a standardized typed
  parameter or a per-integration custom service that defeats the abstraction.
- **They shipped an MVP that could not carry the existing integrations.** Phase one covered **nine**
  integrations, chosen because they "only use `message` as a parameter", against 67+ legacy notify
  integrations — "As soon as we have `title` and/or `recipient` support we can migrate more." Two years on,
  `recipient` support still is not there.

### What a stdlib-only Python port cannot take

Essentially all of the code and none of the obstacles. `voluptuous` is load-bearing for every schema;
`aiohttp` for the async HTTP client (stdlib has none — the port is threads plus `urllib`); `PyYAML` for
`services.yaml` and all config; per-integration pip `requirements` such as `slack_sdk==3.33.4`; and the
whole framework — `EntityComponent`, `ConfigEntry`, the entity/device/issue registries, `hass.services`,
`hass.states`, `RestoreEntity`. **We are borrowing ideas here, not code.** The useful corollary is that
every capability HA gets from `slack_sdk` is plain JSON over HTTPS underneath, so `urllib.request` reaches
it — what is lost is SDK convenience, not reach.

Note also that HA solved inbound with a **completely separate mechanism**: `components/telegram_bot/` has
its own `polling.py`, `webhooks.py` and `event.py`, firing `telegram_text`, `telegram_command`,
`telegram_callback` and `telegram_sent` events, and the `notify` platform plays no part in any of it. **Both
Apprise and Home Assistant treat inbound and identity as out of scope for their channel abstraction. For us
they are the product.**

---

## Errbot

`errbotio/errbot` — a Python chatbot with pluggable "backends". **Structurally the closest analogue to us in
the survey**: Python, class-based adapters, one process, Discord/Slack/IRC/XMPP/Telegram. It is also the
clearest catalogue of what goes wrong, because it has been running into these walls since 2012.

Repo state when read on 2026-08-05: default branch `master`, last push **2026-08-01**, 3,293 stars, 46 open
issues, **last release 6.2.0 on 2024-01-04** (previous 6.1.9, 2022-06-11). **Code moves; releases do not.**

### 1. Plugin boundary

**An in-process imported Python class, and exactly one backend per bot process.** Discovery is two-tier
(`errbot/backend_plugin_manager.py`): a scan for `**/*.plug` files — an **INI manifest**, not Python
metadata — over the base directory, `BOT_EXTRA_BACKEND_DIR`, and **setuptools entry points in group
`errbot.backend_plugins`**. The whole manifest:

```ini
[Core]
Name = Text
Module = text

[Documentation]
Description = This is the text backend for Errbot.
```

`load_plugin()` appends the plugin's parent directory to `sys.path`, loads classes matching the base class,
and **requires exactly one match** — more than one raises `PluginNotFoundException`. Selection is a single
`BACKEND` string in `config.py`.

The abstract contract is `class Backend(ABC)` in `errbot/backends/base.py`:

```python
@abstractmethod def send_message(self, msg: Message) -> None
@abstractmethod def change_presence(self, status: str = ONLINE, message: str = "") -> None
@abstractmethod def build_reply(self, msg, text=None, private=False, threaded=False)
@abstractmethod def build_identifier(self, text_representation: str) -> Identifier
@abstractmethod def prefix_groupchat_reply(self, message: Message, identifier: Identifier)
@abstractmethod def query_room(self, room: str) -> Room
@abstractmethod def callback_presence(self, presence: Presence) -> None
@abstractmethod def callback_room_joined/left/topic(self, ...) -> None
@abstractmethod def connect_callback(self) / disconnect_callback(self) -> None
@property @abstractmethod def mode(self) -> str
@property @abstractmethod def rooms(self) -> Sequence[Room]
```

with non-abstract defaults for `serve_forever()` (loops `serve_once`, handles reconnect),
`serve_once()` (raises `NotImplementedError`), `build_message()`, `is_from_self()` and
`_delay_reconnect()` (exponential backoff with jitter, in the base class — a good thing to inherit).

**And here is the structural mistake, which is the most valuable thing Errbot has to teach.** Four of those
abstract methods — `callback_presence`, `callback_room_joined`, `callback_room_left`, `callback_room_topic`
— are **never implemented by backends**; their docstrings say "Implemented by errBot". They are abstract
because `class ErrBot(Backend, StoreMixin)` is the mixin that satisfies them, and **a concrete backend
subclasses `ErrBot`, not `Backend`**.

So `Backend` is not an interface. It is half "what the adapter provides" and half "what the core provides",
fused by inheritance. **The adapter and the dispatcher are the same object.** The consequences are all
visible: a backend author gets the whole bot's namespace and reaches into it; every backend re-implements
`send_message` with a `super().send_message(msg)` call to fire `callback_botmessage`; there is no way to
unit-test a backend against the contract alone; there is no way to run two; and `errbot/backends/test.py` is
22.5 KB of harness that exists precisely because the boundary is not clean *(inferred from the structure and
file sizes)*.

The identifier hierarchy is `Identifier` → `Person` (abstract `person`, `client`, `nick`, `aclattr`,
`fullname`; non-abstract `email` defaulting to `""`), `RoomOccupant` (abstract `room`), and `Room` (whose
`join`/`leave`/`create`/`destroy`/`topic`/`occupants` all raise `NotImplementedError` by default). `Message`
carries `body, frm, to, parent, delayed, partial, extras: Mapping, flow`.

*(Stale documentation note: `docs/user_guide/backend_development/index.rst` still instructs "Room class:
Inherit from MUCRoom", and `BotPlugin.query_room`'s docstring still says it returns "an instance of
MUCRoom" — a class that no longer exists in `base.py`. A v4-era rename that never reached the docs.)*

### 2. Capability negotiation

**There is none, and `mode` — a bare string — is the de facto capability system.** The costs are concrete:

- **Rooms are mandatory-abstract for a feature many channels lack.** `rooms` and `query_room` must be
  implemented, so a backend without rooms implements them and throws. Telegram does exactly that:

  ```python
  class RoomsNotSupportedError(RoomError):
      def __init__(self, message: Optional[str] = None):
          if message is None:
              message = (
                  "Room operations are not supported on Telegram. "
                  "While Telegram itself has groupchat functionality, it does not "
                  "expose any APIs to bots to get group membership or otherwise "
                  "interact with groupchats."
              )
  ```

  **And the core does not catch it.** `errbot/core_plugins/chatRoom.py` catches only `RoomNotJoinedError`
  around `room_occupants` and `room_topic`; `!room list` calls `self.rooms()` unguarded. So on Telegram the
  built-in room commands surface a raw exception at the user. **Capability is discovered by calling and
  catching, and the caller forgot to catch.**
- **Reactions and edits are entirely undeclared and off-contract.** `Backend` has no `add_reaction` and no
  `update_message`. The Slack backend defines `add_reaction`, `remove_reaction` and `update_message` as
  **backend-only extensions**. A plugin wanting reactions must branch on `self.mode == "slackv3"` and hope.
- **Threads are declared only as `build_reply(..., threaded=False)` and `Message.parent`**; backends that
  cannot thread silently ignore both.
- **Backend-specific data leaks through `Message.extras`**, an untyped `Mapping` — the Slack backend reads
  `msg.extras["slack_event"]["thread_ts"]` directly. **Every use of `extras` makes a plugin non-portable.**

There are exactly two graceful degradations in the system, and both are worth copying because neither needs
a flag. **Cards fall back by template** (`errbot/core.py`):

```python
def send_card(self, card: Message) -> None:
    """
    Sends a card, this can be overriden by the backends *without* a super() call.
    """
    self.send_templated(card.to, "card", {"card": card})
```

— the default renders `errbot/templates/card.md` to markdown and sends it as text; a rich backend overrides
to build a native attachment payload. **Default implementation degrades, override to enrich, no negotiation
needed.** And **size limits split**: `split_and_send_message()` loops
`split_string_after(msg.body, self.message_size_limit)`, cloning the message and setting `partial = True`,
with each backend setting its own limit (Telegram: `set_message_size_limit(limit=1024, hard_limit=1024)`).

### 3. Identity

**No cross-channel identity, and structurally there cannot be — one process runs one backend.** That single
line in `bootstrap.py` (one `backend_name`, one `load_plugin()`) forecloses requirement (c) permanently.

Within a backend there are three or four different strings, and they disagree per backend:

| property | Slack | IRC | Telegram |
|---|---|---|---|
| `person` | `f"{self._userid}"` (`U12345`) | **`nick`** | numeric `id` |
| `nick` | `display_name` | `nickmask.nick` | `username` |
| `fullname` | `real_name` | **`return None  # TODO`** | first + last |
| `aclattr` | `f"{self._userid}"` | `{nick}!{user}@{host}` | `id` |
| `client` | `channelid` | `nickmask.userhost` | `None` |

`__str__` is lossy and also per-backend: Slack returns `f"<@{self.aclattr}>"`, text returns `"@" + person`,
a text room occupant returns `"#room/person"`. **The string form of an identifier is not a stable
cross-backend key.** The only persistence is `StoreMixin`, a per-plugin key/value store — not a person
registry. *(Searched for any cross-backend person record, identity linking or account merge; found none.)*

### 4. Authorization — the part to copy, with its key replaced

Two layers, both enforced in **one place**: `acls()` in `errbot/core_plugins/acls.py`, decorated
`@cmdfilter`, which every command traverses via `_process_command_filters()`.

The user key is `get_acl_usr(msg)` — a custom `aclattr` on the sender if present, else `msg.frm.person`.
Rules start from `ACCESS_CONTROLS_DEFAULT`, iterate `ACCESS_CONTROLS`, match the command as
`plugin:command` with **`fnmatch`, case-insensitive, first match wins**. Checks run in order:
`allowargs`/`denyargs` → `allowusers`/`denyusers` → (group) `allowmuc: False` denies, then
`allowrooms`/`denyrooms` → (DM) `allowprivate: False` denies → the admin gate, where commands carrying
`_err_command_admin_only` require a glob match against `BOT_ADMINS`, under a rule quoted from the source:

> "For security reasons, admin-only commands are direct-message only UNLESS specifically overridden by
> setting allowmuc to True for such commands."

**The single filter chain that every command traverses is the right shape and we should take it. The key is
what to fix.** `aclattr` is *a string chosen by the adapter* and the matcher is `fnmatch` on a free string,
and the results are what you would predict:

- On IRC, `person = nick` and `aclattr = "{nick}!{user}@{host}"`. Nick and ident are attacker-influenced;
  the documented example `BOT_ADMINS = ('gbin!gbin@*', '*!*@trusted.host.com')` shows that only the
  hostmask-anchored form is hard to forge, and it is not the shape users reach for.
- `BOT_ADMINS = ('@admin*',)` matches `@adminfoo`.
- **The two first-party backends disagree with each other.** The Discord backend's README tells users
  `BOT_ADMINS = ('@YourDiscordUsername',)` — **a mutable display name**, not a snowflake — while the Slack
  backend's docs correctly require raw `Uxxxxxx` ids.
- The administration documentation lists the eight glob filters and says only that "Different backends have
  different formats to identify users", with **no warning that some of those formats are spoofable**.

**Rule for us: the ACL key is an opaque, immutable, provider-issued id recorded in our own database at link
time. Never a display name, and never `fnmatch` on a free string.**

### 5. Outbound addressing

`bot.send(identifier, text, in_reply_to=None, groupchat_nick_reply=False)`, where the identifier must first
be built by `build_identifier(str)` — whose docstring says only "(backend dependent)". **The formats are
mutually incompatible, and this is the concrete failure:**

| backend | accepted strings |
|---|---|
| text | `@username`, `#roomname`, `#roomname/person` |
| IRC | `#channel`; **`"member\nroom"` — a literal newline separator**; else Person(nick) |
| Telegram | **numeric only** — `ValueError("Telegram identifiers must be numeric.")`; `>0` Person, `<0` Room |
| Slack | `<#C12345>`, `<#C12345\|channel>`, `<@U12345>`, `@user` *(both marked "deprecated for removal")*, `#channel/user`, `#channel` |
| Discord | `<@userid>`, `<#channelid>`, `@user#discriminator`, `#channel`, `#channel#guild_id` |

Nothing normalizes these. There is no scheme prefix and no common grammar, and the Slack backend's failure
path raises with the text "You found a bug… please file a bug." Compare OpenClaw's `<kind>:<id>` and Hermes's
`platform:chat_id:thread_id`, both of which are grammars.

One thing Errbot gets right: **the outbound path is identical for handler-initiated and webhook-initiated
sends** — a webhook handler reaches chat through the same `build_identifier()` + `send()` pair. Webhooks
themselves are Flask (`flask_app.add_url_rule(uri_rule, view_func=..., methods=verbs)`), with three body
modes driven by `_err_webhook_raw` and `_err_webhook_form_param`.

### 6. Setup UX

**Secrets live in `config.py`, a Python file, as literals** — `BOT_IDENTITY = {...}`, `BOT_ADMINS = (...)`,
`BACKEND = "..."`. No env-var indirection is offered by the template, so a plaintext token file on disk is
the default posture. (It is Python, so a user can write `os.environ[...]` themselves.)

Slack goes through `err-backend-slackv3`, which supports three protocols **auto-selected by sniffing the
token type** rather than configured: legacy RTM, Events over HTTP (needs a public Request URL), and Events
over Socket Mode (`xoxb-` bot token plus an `xapp-` app token, no inbound URL). Realistic step count is
**~9**. Discord goes through `err-backend-discord`, which depends on `discord.py==2.7.1`; **~5 steps**, of
which the two privileged intents (`SERVER MEMBERS`, `MESSAGE CONTENT`) are the classic silent-failure trap —
the bot connects and receives nothing.

### 7. What they got wrong

- **Backend rot is the headline, documented in their own `CHANGES.rst`**: v6.1.8 removed the GUI backend;
  v6.1.9 deprecated the built-in Slack and SlackRTM backends and **removed HipChat entirely**; v6.2.0
  **removed the Slack backends** and moved Slack, Mattermost and Discord out to install extras. Core
  `errbot/backends/` today contains only `text, test, null, irc, xmpp, telegram_messenger` — **no Slack, no
  Discord, no Mattermost.**
- **The Slack RTM death spiral**, in their own words
  ([issue #1545](https://github.com/errbotio/errbot/issues/1545)): "Slack is changing the response from its
  deprecated rtm.start endpoint on 09/20/2022, which errbot's backend, slackclient, uses" — compounded by
  "slackclient itself is already deprecated and errbot is pinned to slackclient>=1.0.5,<2.0, which is
  already an old major version." **A vendored SDK pinned to a major version is a slow-motion outage.**
- **Two competing Slack backends at once**, which forced a formal four-phase deprecation plan
  ([issue #1480](https://github.com/errbotio/errbot/issues/1480)): "Multiple PRs for the same features are
  being created. Features are applied to one slack backend but not the other. Inconsistent behaviour
  between backends makes debugging confusing."
- **`build_identifier` inconsistency is a filed, still-open bug** — opened **2017-04-10 and still open** —
  complaining that it "does not play nice with a single string identifier as used in the example", "does
  not return a single identifier object (as done so within the other backends)", and that "There's no
  documentation on what string identifiers may be used"
  ([Vaelor/errbot-mattermost-backend#14](https://github.com/Vaelor/errbot-mattermost-backend/issues/14)).
  **Nine years unresolved.**
- **Release cadence**: 26 months between 6.1.9 and 6.2.0, and 31 months since 6.2.0 with an active master.

### What a stdlib-only Python port cannot take

Errbot's *core* runtime dependencies — none of them stdlib — are `flask`, `requests`, `jinja2`, `pyOpenSSL`,
`colorlog`, `markdown`, `ansi`, `Pygments`, `pygments-markdown-lexer`, `dulwich`, `deepmerge`, `daemonize`.
Mapping them out: `flask` (webhooks) → `http.server`; `jinja2` (the card fallback and `send_templated`) →
`string.Template`; `markdown`/`Pygments`/`ansi` (their whole rendering pipeline, which converts markdown to
HTML, text, IM and ANSI) → drop or minimally reimplement; `requests` → `urllib.request`; `dulwich` (plugin
install from git) → drop. Per backend it is `slack-sdk` + `slackeventsapi` + `aiohttp`, `discord.py==2.7.1`,
`python-telegram-bot==13.15`, `irc==20.5.0`, `slixmpp`.

**The transport conclusion is the important one, and it is consistent across every system in this page.**
Telegram's backend proves the stdlib shape works — its `serve_once` "retrieves updates in an infinite loop
with offset tracking", which is `urllib.request` and nothing else. Slack Socket Mode and the Discord gateway
are WebSocket-only, and Python's standard library has **no WebSocket client**.

---

## Rasa

`RasaHQ/rasa` — channel "connectors". Included for two ideas that are better than anything else surveyed at
their specific jobs: **text-flattening defaults**, and **`output_channel=latest`**.

*(Repo state 2026-08-05: Apache-2.0, **default branch `3.6.x`** — a maintenance branch — last push
2026-07-24, 21,282 stars, not archived. The commercial product is Rasa Pro.)*

### 1. Plugin boundary

An imported Python class **pair**, referenced by **dotted module path in `credentials.yml`**
(`rasa/core/channels/channel.py`):

```python
class InputChannel:
    @classmethod def name(cls) -> Text
    @classmethod def from_credentials(cls, credentials: Optional[Dict]) -> "InputChannel"
    def url_prefix(self) -> Text
    def blueprint(self, on_new_message: Callable[[UserMessage], Awaitable[Any]]) -> Blueprint
    def get_output_channel(self) -> Optional["OutputChannel"]   # default None
    def get_metadata(self, request: Request) -> Optional[Dict]  # default None

class OutputChannel:
    @classmethod def name(cls) -> Text
    async def send_response(self, recipient_id, message: Dict) -> None
    async def send_text_message(self, recipient_id, text, **kwargs) -> None   # NotImplementedError
    async def send_image_url / send_attachment / send_text_with_buttons
    async def send_quick_replies / send_elements / send_custom_json
```

Built-ins register as `BUILTIN_CHANNELS = {c.name(): c for c in input_channel_classes}` over 15 classes;
custom channels bypass the registry entirely, keyed in `credentials.yml` by module path:

```yaml
addons.custom_channel.MyIO:
  username: "user_name"
  another_parameter: "some value"
```

**`blueprint()` returning a `sanic.Blueprint` is the hard dependency**, and it is in the *base class*, so it
is unavoidable. The adapter does not merely use HTTP — it hands the core a Sanic object and mounts routes
into the core's Sanic app. There is no transport abstraction, and every Sanic major bump is a breaking
change for every third-party connector. **The stdlib equivalent is to have the adapter return
`(path, handler)` pairs that our own `http.server` router mounts** — same idea, no framework in the
contract.

### 2. Capability negotiation

**None declared — but the degradation is far better engineered than Errbot's, and this is the single most
portable idea in the survey.** Only `send_text_message` raises `NotImplementedError`. **Every other send
method has a text-flattening default in the base class**: `send_image_url` posts the URL as a string,
`send_attachment` posts as a string, `send_text_with_buttons` posts buttons as strings, `send_quick_replies`
delegates to `send_text_with_buttons`, `send_elements` formats as text, `send_custom_json` serialises to a
string. `send_response(recipient_id, message: Dict)` dispatches on which keys are present.

**A minimal channel implements one method and everything still delivers, in degraded form.** Combined with a
declared capability set, that gives exactly what requirement (b) needs: declared capability takes the rich
path, everything else falls automatically to lossy text — and email, which declares nothing, gets one final
plain message without a single `if channel == "email"` anywhere.

The cost of not declaring is visible too. Slack's `send_text_with_buttons` logs "Slack API currently allows
only up to 5 buttons" when count > 5 and **falls back to text-only**; Telegram's picks among
inline-horizontal, inline-vertical and reply keyboards. **Same abstract method, three different degradation
policies, none declared** — so an author writing a six-button response gets silently different UX per
channel with only a log line.

Streaming is the one declared capability, and it was bolted on late: the docs say to "override
`supports_streaming` and implement `send_response_chunk()`". *(That pair was not present in the OSS
`channel.py` signature list read; the claim comes from the custom-connectors doc and may describe Rasa Pro —
gap.)*

### 3. Identity

**`sender_id` is per-channel and is not an identity — it is a conversation key.** Confirmed by their own
[issue #10158](https://github.com/RasaHQ/rasa/issues/10158), "Rename `sender_id` in channel connectors to
`conversation_id`", arguing the fields "are actually used as `conversation_id`" — **closed without the
rename**.

Worse, it is configurably *finer* than a person: Slack's `SlackInput.__init__` takes
`conversation_granularity: Optional[Text] = "sender"`, and `_get_conversation_id()` **appends channel and/or
thread ids** under `"channel"` / `"thread"` granularity — so the same human in two Slack channels can be two
conversation ids by configuration. There is no user record and no cross-channel linkage. The core *knows*
which channel a message came from (`UserMessage.input_channel`) but never joins on person.

### 4. Authorization

**Effectively absent at the channel layer.** What exists is transport authentication — JWT
(`decode_jwt`/`decode_bearer_token`) for authenticating a *client*, `@requires_auth(app, auth_token)` on
server routes, Slack signing-secret verification, Telegram's `verify` username check. There is no
`BOT_ADMINS` analogue, no ACL, no admin-only concept, because Rasa's unit of work is an intent→action
dialogue rather than a command. **For a gateway that runs tools on a user's behalf, Rasa is not the model
here; Errbot's `@cmdfilter` chain is.**

### 5. Outbound addressing — the idea to steal

The cleanest addressing in the survey (`rasa/server.py`):

```python
def _get_output_channel(request, tracker) -> OutputChannel:
    requested_output_channel = request.args.get(OUTPUT_CHANNEL_QUERY_KEY)
    if requested_output_channel == USE_LATEST_INPUT_CHANNEL_AS_OUTPUT_CHANNEL and tracker:
        requested_output_channel = tracker.get_latest_input_channel()
    registered_input_channels = getattr(request.app.ctx, "input_channels", None) or []
    matching_channels = [c for c in registered_input_channels if c.name() == requested_output_channel]
    return reduce(
        lambda so_far, input_channel: (input_channel.get_output_channel() or so_far),
        matching_channels,
        CollectingOutputChannel(),
    )
```

```
curl -X POST -d '{"name": "EXTERNAL_dry_plant", "entities": {"plant": "Orchid"}}' \
  "http://localhost:5005/conversations/user123/trigger_intent?output_channel=latest"
```

Four things worth taking:

1. **Addressing is the tuple `(conversation_id, channel_name)`, resolved at send time.** No identifier
   strings to parse — the direct answer to Errbot's five incompatible grammars.
2. **`output_channel=latest` is a first-class named value**, backed by `tracker.get_latest_input_channel()`.
   **"Reply wherever they last spoke to me" is the single most useful outbound primitive for a multi-channel
   gateway, it is what requirement (e) actually wants most of the time, and it costs one column.**
3. **The graceful default is `CollectingOutputChannel()`** — if no channel matches, output is collected and
   returned in the HTTP response rather than dropped or raised. A null sink that is also the test double.
4. **They do have a real send-only distinction — enforced in prose.** The docs state that "External Events
   and Reminders don't work in request-response channels like the `rest` channel or `rasa shell`" and that
   connectors needing proactive delivery "should be built off of the CallbackInput channel…instead of the
   RestInput channel". **A genuine capability, documented instead of declared** — precisely the gap a
   capability record closes.

### 6. Setup UX

All credentials in `credentials.yml`, loaded via `rasa run --credentials <file>`. Slack is **Events-over-HTTP
only — no Socket Mode** — so the user must expose a public HTTPS Request URL (ngrok in development). Telegram
is webhook-based too, with `blueprint()` exposing a `set_webhook` route. Slack is **~8 steps** and, unlike
Errbot, there is **no tunnel-free option**.

### 7. What they got wrong

`sender_id`'s naming and semantics (their own issue, closed unfixed); Sanic welded into the plugin contract;
connector boilerplate (the minimum viable connector is two classes, a Blueprint with health and webhook
routes, request parsing and an `on_new_message` await — their docs call `send_text_message` "The only method
you must implement" on output but say nothing that short about input); proactive messaging working only on
some channels, enforced by documentation; and buttons silently becoming text on Slack past five.

**Third-party assumptions**: `sanic` in the base class (unavoidable), `PyJWT`, `slack_sdk`'s async client,
`aiogram` for Telegram. **Nothing about Rasa's channel layer is transplantable without rewriting
`blueprint()`; the ideas transplant perfectly.**

---

## Botpress

Included for one thing the others lack: **capability as a named, versioned, schema-carrying contract an
adapter opts into.** That is the cleanest answer to requirement (b) found, and it needs no libraries.

**Which Botpress, and the licensing answer up front.** `botpress/botpress` on `master` is **no longer the v12
server** — it is a pnpm/turbo TypeScript monorepo of `integrations/`, `interfaces/`, `plugins/` and devtools,
MIT licensed, last pushed 2026-08-05. Its readme redirects self-hosters: "For any problem related to
on-premise Botpress v12, please see the Botpress v12 repository." `botpress/v12` is AGPL-3.0 and **last
pushed 2025-04-10**. **The integration code is open source; the runtime that executes it is not** —
integrations are deployed with `bp deploy` to Botpress Cloud. I examined the current Integration SDK model,
since that is what is live. *(The "v12 is sunset" characterisation is search-derived; what was verified
directly is the v12 repo's last-push date and the main readme's redirect.)*

### 1. Plugin boundary

**A deployed TypeScript package — effectively a managed serverless function — split across a *definition*
file and an *implementation* file.** That two-file split is the interesting structural idea: the definition
is declarative and statically analysable, the implementation is code.

`integrations/slack/definitions/channels/channels.ts` declares **three channels** — `channel`, `dm`,
`thread` — each declaring the message types it accepts, its **message tags** (`ts`, `userId`, `channelId`,
`mentionsBot`, `forkedToThread`) and its **conversation tags** (`id`, `title`; `thread` adds `thread` and
`isBotReplyThread`). The implementation is a handler table:

```typescript
export default {
  channel: { messages: defaultMessages },
  dm:      { messages: defaultMessages },
  thread:  { messages: defaultMessages },
} satisfies bp.IntegrationProps['channels']
```

with each handler receiving a destructured props object and — importantly — **acknowledging by writing the
provider's ids back**:

```typescript
await ack({ tags: { ts: message.ts, channelId: payload.channel, userId: message?.user } })
```

Inbound is one `handler` given the **raw HTTP request**, which verifies the signature
(`new SlackEventSignatureValidator(signingSecret, req, logger).isEventProperlyAuthenticated()`, throwing
`RuntimeError("Handler received a request with an invalid signature")`) and switches on the event type,
logging and ignoring unsupported ones.

### 2. Capability negotiation — the model to copy

**Two axes, both declarative.**

**Message-type capability, per channel, declared statically** — the channel definition enumerates which of
`text, image, audio, video, file, location, carousel, card, dropdown, choice, bloc` it accepts, so the
builder knows at *design time* what a channel can render. No runtime probing, no `NotImplementedError`.

**Behavioural capability via `interfaces` — named, versioned contracts an integration `.extends()`.** There
are 14: `creatable, deletable, files-readonly, hitl, listable, llm, message-state, proactive-conversation,
proactive-user, readable, speech-to-text, text-to-image, typing-indicator, updatable`. In full:

```typescript
export default new InterfaceDefinition({
  name: 'proactive-conversation',
  version: '0.0.4',
  entities: { conversation: { title: 'Conversation', ... } },
  actions: {
    getOrCreateConversation: {
      title: 'Get or Create a Conversation',
      description: 'Proactively create a conversation from a bot',
      input:  { schema: ({ conversation }) => z.object({ conversation: conversation... }) },
      output: { schema: () => z.object({ conversationId: z.string()... }) },
    },
  },
})
```

with `typing-indicator` declaring `startTypingIndicator({conversationId, messageId, timeout?})` and
`stopTypingIndicator({conversationId, messageId})`.

**The lesson: "can this channel start a conversation unprompted?" and "can it show typing?" are named,
versioned, schema-carrying capabilities an adapter opts into — not exceptions to catch.** This is the direct
fix for Errbot's `if self.mode ==` ladders and for Rasa's prose-documented "doesn't work on `rest`", and in
stdlib Python it is a set of capability-name strings plus a declared input/output shape. Note also that
`proactive-conversation` is precisely the capability that separates "channels an agent can reach out on"
from "channels that can only answer" — which is exactly the axis requirement (e) needs.

*(Could not verify what Botpress does at runtime when a bot sends a message type a channel did not declare —
drop, coerce to text, or error. That code path was not found.)*

### 3. Identity

**Botpress has an explicit user record, and its documentation names the problem the others ignore:** users
are "speakers (person or entity) that can send messages in a conversation", are "associated with specific
integrations", and — the key sentence — **"Multiple user identities can represent the same person across
different platforms."** *(Could not find the actual merge or link mechanism, or whether it is automatic — so
the data model admits the problem; whether it solves it is unverified.)*

Identity attributes ride on **declared, per-integration tags**. Slack's user tags are `id` ("The Slack ID of
the user (U0000XXXXXX)"), `team`, `real_name`, `display_name`, **`email`**, `phone`, `is_bot`, `is_admin`,
`tz`, `dm_conversation_id` ("created via `startDmConversation` action") and avatar URLs at sizes 24→1024.

**`email` being a first-class declared tag is the detail to note** — it is the obvious cross-channel join
key, and capturing it per provider at link time is what makes a later merge possible *(inferred)*. Tags are
"string-based metadata for messages, users, and conversations… defined by the integration or bot" — an
untyped-value, **typed-key** sidecar: better than Errbot's free-form `extras` because the keys are declared
and documented, worse than a real schema.

### 4. Authorization

*(Could not find any per-user command-authorization model comparable to `BOT_ADMINS`/`ACCESS_CONTROLS` in
what was fetched.)* What exists at this layer is transport authorization — webhook signature validation and
OAuth scoping. Workspace and collaborator permissions live in Botpress Cloud's admin plane, which is not in
this repo. **Treat Botpress as no useful prior art for command-level authz.**

### 5. Outbound addressing

**`conversationId` — a Botpress-issued opaque id, never a provider string, never parsed from user input.**
Provider coordinates live in conversation tags (`id` = Slack channel id, `thread`, `title`), and the
integration converts: `_getSlackTarget(conversation)` maps the Botpress conversation to a Slack
channel/thread. Starting a conversation from nothing is the `proactive-conversation` interface's
`getOrCreateConversation({ conversation }) -> { conversationId }`, taking an **entity-shaped input** and
returning the internal id.

**The caller never constructs a provider-specific string.** Contrast Errbot, where "send to X" means knowing
that Telegram wants a negative integer, Slack wants `<@U12345>`, IRC wants `member\nroom` and text wants
`@name`. Botpress puts that knowledge inside the adapter, behind a declared entity schema.

### 6. Setup UX — and the trade it reveals

From the Slack integration's own `hub.md`, two paths:

- **OAuth (default): one step.** "Simply select this option in the wizard and you will be redirected to
  Slack to authorize the app." Botpress owns the Slack app; **no token ever touches the user.**
- **Manual (bring your own Slack app): three steps** — add the redirect URL
  `https://webhook.botpress.cloud/oauth` and **19 bot token scopes** to your Slack app; enter Client ID,
  Client Secret and Signing Secret in the wizard; copy Botpress's webhook URL into Slack's Event
  Subscriptions Request URL.

**This is the best setup UX in the survey and it is bought entirely with a hosted relay
(`webhook.botpress.cloud`) plus a vendor-owned OAuth app.** That is the trade to be explicit about: one-step
onboarding requires somebody to own a public HTTPS endpoint and a registered application. **A local-first,
stdlib-only macOS gateway cannot have the one-step version without operating a relay** — which is a product
decision, not an engineering one, and it is the single largest constraint on requirement (f).

### 7. What they got wrong

The open-source runtime is gone, and for anyone who adopted v12's channel model the migration path is "move
to our cloud". **Vendor lock-in is architectural, not incidental** — the plugin *is* a deployment target;
`@botpress/sdk`, `bp.Integration()`, the injected `client`, and `webhook.botpress.cloud` are all
load-bearing, and nothing about an integration runs standalone. The Slack integration also ships `.vrl`
files (Vector Remap Language) — yet another DSL in the integration surface *(purpose not determined; not
fetched)*. And the capability contracts are themselves unstable: `proactive-conversation` is at
`version: '0.0.4'`.

---

# Patterns worth stealing

Ordered by how much they buy us. Each says who does it and what it costs in stdlib Python.

### 1. Capability is which methods you implement — plus a data record for the rest

**Who:** mautrix (`EditHandlingNetworkAPI`, `ReactionHandlingNetworkAPI`, …), OpenClaw (optional adapter
slots — omit `heartbeat` and you have no typing indicator), Botpress (named `interfaces` an integration
`.extends()`). Three independent systems converged on it.

The minimum adapter receives and sends one message. Everything else is opt-in, and **absence is the
declaration** — no flag to forget to set, no stub that lies. In stdlib Python this is
`typing.Protocol` with `@runtime_checkable` plus `isinstance`, or plain `hasattr`. **Zero dependencies, zero
machinery.**

Then, for the things a method's existence cannot express — limits, degrees, per-destination differences —
a data record. Steal mautrix's shape and Apprise's vocabulary:

```python
class Support(IntEnum):          # mautrix's CapabilitySupportLevel
    REJECTED  = -2   # I will refuse and error
    DROPPED   = -1   # I will accept and silently discard
    UNSUPPORTED = 0
    PARTIAL   = 1
    FULL      = 2
```

**The five-valued enum is the most valuable single idea on this page.** A boolean cannot distinguish
*rejected loudly* from *dropped quietly*, and that distinction is exactly what lets a caller decide whether
to degrade or to fail. Matterbridge's entire failure mode is that everything is implicitly `DROPPED` with no
way to find out — ten years and twenty protocols later its capability documentation is one wiki paragraph.

Alongside the levels, the numeric limits, which is where Apprise is far ahead of everyone: `max_text_length`,
`title_maxlen` (**with `0` as the sentinel for "this channel has no concept of a subject line"** — the SMS
and WhatsApp case), `edit_max_count`, `edit_max_age`, `reaction_count`, `allowed_reactions`,
`request_rate_per_sec`. OpenClaw's `limits` sub-object exists for the same reason, and states the payoff:
they "describe the generic envelope core can adapt before calling the renderer".

**Requirement (b) then stops being a flag and becomes arithmetic.** "Can this channel stream?" is
`edit >= PARTIAL and edit_max_count > n`. Discord DM answers yes and gets live editing; email answers no and
the same core path collapses to one send. **The core owns the degradation; the channel only owns the truth
about itself.**

### 2. One required primitive, with text-flattening defaults for everything else

**Who:** Rasa (only `send_text_message` raises `NotImplementedError`; `send_image_url`, `send_attachment`,
`send_text_with_buttons`, `send_quick_replies`, `send_elements`, `send_custom_json` all have base-class
defaults that project to text). Errbot does the same thing once, for cards, via a markdown template —
"Sends a card, this can be overriden by the backends *without* a super() call."

Combined with (1), this is the whole answer to "a Discord DM wants live streaming, an email wants only the
final message": **declared capability takes the rich path; everything undeclared falls automatically to
lossy text.** Email declares nothing and gets one plain message, with no `if channel == "email"` anywhere in
the codebase.

OpenClaw's presentation-block degradation is the fully-worked version of the same rule, and its governing
sentence should go into our design verbatim: **"Unsupported native controls should degrade rather than fail
the whole send."** Its specific fallbacks are worth copying too — command actions render as
``label: `command` ``, callback actions become label-only *so opaque values stay private*, charts and tables
become deterministic text, an unsupported select lists its options.

### 3. Addressing is a tuple resolved at send time, never a string the caller parses

**Who:** Rasa (`(conversation_id, channel_name)`), Botpress (an opaque `conversationId`, with provider
coordinates in tags), mautrix (`(remote_chat_id, receiver_login_id)`), Matterbridge (`account:channel`).

**And the counter-example is decisive.** Errbot's `build_identifier()` accepts `#channel` on IRC but
`"member\nroom"` — a literal newline separator — for a room occupant; numeric-only on Telegram with `>0`
meaning person and `<0` meaning room; `<@U12345>` or `@user` (both "deprecated for removal") on Slack;
`@user#discriminator` on Discord. Nothing normalizes them, there is no common grammar, and **the bug report
about it has been open since 2017-04-10.**

Where a human-typed address is genuinely needed, take OpenClaw's and Hermes's shape, because they agree:
a **`<channel>:<kind>:<id>` grammar** where the prefix resolves the adapter without a separate flag —
`discord:channel:123`, `discord:user:456`, `slack:channel:C0123`, `telegram:<chatId>:topic:<topicId>`.
OpenClaw states the payoff: "Channel-prefixed targets … resolve the owning plugin without an explicit
`--channel`." **The recurring `channel:` / `user:` / `group:` / `conversation:` kind-word is the useful
invariant** — it separates a room id from a person id without the core knowing the channel.

Two affordances that make an opaque-id scheme usable by a human, both cheap: Hermes's
**`send --list [platform]`** to enumerate configured targets, and its **bare `platform` form** meaning "the
home/default channel for that platform".

### 4. `output_channel=latest` — reply where they last spoke

**Who:** Rasa, backed by `tracker.get_latest_input_channel()`, with `USE_LATEST_INPUT_CHANNEL_AS_OUTPUT_CHANNEL`
as a named constant. Zulip reaches the same place from the other direction with `send_reply(message,
response)`, which **sidesteps addressing entirely by echoing the inbound envelope**.

**The overwhelmingly common case — answer the person who just spoke, wherever they spoke — should require no
address at all and should be impossible to misroute.** It costs one column on the conversation row. It is
also most of what requirement (e) actually wants day to day, and it degrades honestly: "email me the daily
report" needs the person→address resolution in (5), but "reply to me" never does.

### 5. A person table, populated by an explicit link step

**Who:** only mautrix, properly. `UserLogin` is `UserMXID` (the real human) → many `ID`s (one remote
account), with `GetAllForUser()`. Ghosts are separate rows for remote people we do not control. OpenClaw has
the routing half only — `identityLinks: { alice: ["telegram:123456789", "discord:987654321012345678"] }`
substituted into the session key. Everyone else has nothing: Matterbridge relays a display name; Errbot
cannot (one backend per process); Rasa's `sender_id` is a conversation key and can be configured *finer*
than a person; Apprise and Home Assistant's `notify` have no person at all.

The shape to build:

```sql
CREATE TABLE person (id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, is_owner BOOLEAN NOT NULL DEFAULT 0);

CREATE TABLE account (                    -- one row per (channel, remote identity)
    id INTEGER PRIMARY KEY,
    person_id  INTEGER REFERENCES person(id),   -- NULL == a ghost: seen, not linked
    channel    TEXT NOT NULL,
    remote_id  TEXT NOT NULL,                   -- immutable, provider-issued
    handle     TEXT,                            -- mutable display name, never a key
    email      TEXT,                            -- the obvious cross-channel join hint
    linked_at  TEXT,
    UNIQUE (channel, remote_id)
);
```

Three findings force this shape, and each was expensive for somebody:

- **The ACL key must be the immutable provider id, never the display name.** Errbot's `aclattr` is a string
  the adapter chooses, matched with `fnmatch`; its own two first-party backends disagree, with the Discord
  README telling users `BOT_ADMINS = ('@YourDiscordUsername',)` — a mutable display name — while the Slack
  docs correctly require raw `Uxxxxxx`. On IRC `person = nick`, which is attacker-influenced.
- **Ownership cannot be inferred; it must be proven.** Every system with real cross-channel identity gets it
  by the human handing over a credential or running a link command — mautrix's double puppeting, or its
  manual `login-matrix <token>`. **Matterbridge tried the display-name route and the artifact is
  `{NOPINGNICK}`**, a variable that injects a zero-width space so a relayed name will not ping a same-named
  local user. That variable is what name-matching identity looks like at maturity.
- **Capture `email` per account at link time.** Botpress declares it as a first-class Slack user tag. It is
  the one identifier that plausibly appears on several channels, and it is what makes requirement (e) —
  "email me the daily report" — resolvable at all: person → account where `channel='email'` → address.

**Honest calibration on requirement (c):** *nothing surveyed does the full job.* Home Assistant has been
circling it for two years, with a maintainer's objection worth internalising — "The problem with that is that
we don't know all targets before hand in some integrations" — and the answer still only a proposal for
"config subentries… which can function as a contact registry". Botpress's docs name it ("Multiple user
identities can represent the same person across different platforms") without a merge mechanism being
findable. OpenClaw's is a hand-edited config map with no verification, which is why a community
"identity-resolver skill" exists to do it properly. **We have little prior art and will be designing this
ourselves — but the `person`/`account` split above is the one shape that several systems approximate and
none regret.**

### 6. Separate the adapter *type* from one authenticated *session*

**Who:** mautrix, explicitly — `NetworkConnector` is the adapter type (config, login flows, bridge-wide
capabilities); `NetworkAPI` is one user's authenticated login. Matterbridge conflates them, which is exactly
why it cannot model "Tim's Slack account" separately from "the Slack adapter".

**We hit this the first time one agent needs two Discord accounts, or two agents share one token** — and
Hermes shows the second case is real, not hypothetical: adapters holding unique credentials must call
`acquire_scoped_lock()` in `connect()` and `release_scoped_lock()` in `disconnect()` so that "two profiles
[do not use] the same credential". **A bot token is a singleton resource**; two processes on one Discord
token fight over the same gateway session. With one launchd job per agent, that is our default topology.

OpenClaw makes the same split at the config layer with a stated rule worth copying: **"Account
resolution/inspection belongs on `config`, not `setup`"** — `setup` covers onboarding *writes* only, so
reading which accounts exist never risks mutating them.

### 7. A durable message-id map, not a cache

Matterbridge maps a canonical origin id to each protocol's native id in an **LRU of 5000 entries**, with the
sentinel `"msg-parent-not-found"` — so edits and thread replies **silently stop working once the parent ages
out**. mautrix persists the same thing: `message.mxid` and `reaction.mxid` are `UNIQUE` columns in real
tables.

**With SQLite per agent this fidelity is free**, and it is the precondition for every edit-based capability
including streaming. Take mautrix's reaction key verbatim, because it is not obvious:
`PRIMARY KEY (channel_id, message_id, sender, emoji)`.

Also make the adapter hand the id back on send. Hermes's `SendResult` is the shape:

```python
@dataclass
class SendResult:
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    error_kind: Optional[str] = None
    retry_after: Optional[float] = None
    continuation_message_ids: tuple = ()
```

`error_kind` + `retry_after` make **rate limiting part of the contract** rather than something each adapter
reinvents; `continuation_message_ids` admits that **one logical reply legally becomes several platform
messages** and keeps all their ids for a later edit. Both are cheap now and painful to retrofit.

Richer still is OpenClaw's four-valued send outcome — `sent`, `suppressed` ("no platform message should be
treated as missing"), `partial_failed`, `failed`. **`suppressed` and `partial_failed` are the two states a
boolean loses, and both change retry behaviour.** Compare Apprise, whose `send()` returns `bool` with no
message id at all — which is precisely why it can never grow edits, reactions, threading or replies.

### 8. Make bookkeeping impossible for an adapter author to skip

Home Assistant wraps the overridable method in a `@final` one:

```python
@final
async def _async_send_message(self, **kwargs: Any) -> None:
    """Send a notification message (from e.g., service call).

    Should not be overridden, handle setting last notification timestamp.
    """
    await self.async_send_message(**kwargs)
    self._async_record_notification()
```

The core writes the delivery row and the id mapping; the adapter only ever implements the inner send. An
author who forgets cannot break the ledger. **This is the antidote to Errbot's problem**, where every backend
must remember to call `super().send_message(msg)` to fire `callback_botmessage`.

Put the shared adaptation there too, as both Apprise and Errbot do: **one `_apply_overflow()` in the base
class returning a list of `{title, body}`**, so every adapter gets title-folding, line-capping, truncation
and splitting for free from declared numbers. Apprise's title-folding is the reference implementation —
when `title_maxlen <= 0` it prepends the title to the body in the channel's own dialect (`<b>` for HTML,
`# ` for Markdown, plain newline otherwise) and clears the title.

### 9. Accept the vendor's own copy-pasteable URL

Apprise's `parse_native_url()` — "The intent of this is to make Apprise a little more userfriendly to people
who aren't familiar with constructing URLs and wish to use the ones that were just provided by their
notification service." Paste `https://discord.com/api/webhooks/…` or `https://hooks.slack.com/services/…`
and it works.

**Cheapest possible setup-UX win, and it removes an entire class of transcription error.** Store it
normalized into rows immediately; keep the URL only as an *import format*.

### 10. A data-driven login flow the core renders

mautrix's `GetLoginFlows() []LoginFlow` + `CreateLogin(...) (LoginProcess, error)`, in **three step types —
user input, cookies/webview, and display-and-wait** (QR codes, "approve on your phone") — makes "connect
Discord" a generic wizard built from adapter-supplied data rather than per-adapter README prose.

In a stdlib Python CLI, *user input* and *display-and-wait* are trivial. **Webview is the one to punt on, and
it is exactly the one that needs the OAuth callback server we cannot have.**

Pair it with OpenClaw's onboarding rule: **verify before persisting.** `openclaw onboard` tests a candidate
with a real call and persists "only the verified model route". A token that has never sent a message should
not be written to config as though it works.

### 11. Pairing codes for the unknown sender

**OpenClaw and Hermes converged on this independently, down to the details**: an unknown DM sender gets a
one-time code; codes **expire after 1 hour**; approval is out-of-band on the CLI
(`openclaw pairing approve <channel> <code>` / `hermes pairing approve telegram XKGH5N7P`), with
`list`/`revoke`/`clear-pending` alongside. OpenClaw additionally caps **pending requests at 3 per channel**,
which is the anti-flood detail worth copying.

Two convergent implementations is the strongest signal in this page that this is the right shape for
requirement (d) — and it is the only setup step that is *ours* to make pleasant rather than the platform's.

Take Hermes's permission floor too: an unprivileged user can always run `/help` and `/whoami`. **Being able
to ask the bot who it thinks you are makes allowlist debugging tractable**, and it is two commands.

### 12. Small structural borrowings

- **Zulip: make send-only a type, not a flag.** Its "incoming webhook" bot is *"limited to only sending
  messages into Zulip"*, enforced server-side by bot type. Email, SMS and notification webhooks should be
  *unable* to be wired for inbound, not merely documented as not supporting it.
- **Zulip: one handler contract, two transports.** The Botserver's HTTP path and the long-polling bot call
  the identical `handle_message(message, bot_handler)`. **Our channels split exactly this way** — some poll,
  some receive webhooks, some only send — so the transport must not be in the handler contract. (This is the
  precise thing Rasa got wrong by putting `sanic.Blueprint` in the base class.)
- **Zulip: authorization is not a parallel system.** The bot is a principal in the permission system that
  already exists. Home Assistant makes the same point from the other side: entity-generation destinations
  can carry `POLICY_CONTROL` because they have ids; legacy service-name destinations cannot, because they do
  not.
- **Errbot: one filter chain every command traverses** (`@cmdfilter`), with the rule that **admin-only
  commands are DM-only unless explicitly overridden**. Keep the chain, replace the key (see 5).
- **Home Assistant: intersect capabilities, union availability** when fanning out to a group. Three lines,
  and obviously right once stated.
- **Home Assistant: per-member default `data` with deep-merge override**, so a fan-out member can carry
  channel-specific defaults the caller may override.
- **Apprise: `optional`, and a tristate return.** A failure on an endpoint marked optional does not fail the
  batch; `notify()` returns True/False/**None**, where None means "nothing matched the filter" — a state a
  boolean loses and a scheduled report needs.
- **Matterbridge: direction as routing-table membership** (`In` / `Out` / `InOut`) rather than a property of
  the address. Send-only falls out for free as an entry that appears only in `Out`.
- **Matrix: transaction ids for at-least-once delivery**, and **ephemeral events as an opt-in stream** so a
  send-only channel is never spammed with typing notifications.
- **Matterbridge: the generic escape-hatch adapter.** Its `api` bridge implements the interface with
  `Connect`/`Disconnect`/`JoinChannel` as no-ops and exposes `GET /api/stream` + `POST /api/message` behind
  a static bearer token. **A third-party channel SDK in about forty lines of `http.server` and
  `urllib.request`** — the answer for anything we do not want in-process.
- **Apprise: fail-closed config parsing.** One malformed line aborts the entire file. Correct for a file
  holding credentials.

---

# Traps

### Transport is the real constraint, and it decides the product

Everything above is data and logic and ports cleanly. What does not port is underneath. **Python's standard
library has no WebSocket client**, and the Discord gateway and Slack Socket Mode are WebSocket-only. This
recurs in every system surveyed and is the single highest-stakes decision in the design.

| Channel | Inbound, stdlib-only |
|---|---|
| Email | **Yes** — `imaplib`, `smtplib`, `email`. The one channel stdlib covers end to end. |
| Telegram | **Yes** — `getUpdates` long-poll over `urllib.request`. Errbot's `serve_once` proves the shape; its SDK is convenience only. |
| Slack | **Yes, Events-over-HTTP only** — `http.server` plus `hmac.compare_digest` for the `v0=` signature. Rasa's connector is HTTP-only too. **But it needs a publicly reachable HTTPS endpoint.** |
| SMS, WhatsApp | **Yes** — HTTP webhook in, REST out, HMAC-signed. Same public-URL requirement. |
| Webhooks | **Yes** — `http.server`. The baseline everything else layers on. |
| Discord | **Problematic.** Either a hand-written RFC 6455 client over `socket`/`ssl`/`base64`/`hashlib`/`struct` — feasible, but we own framing, heartbeat, resume and zlib-stream decompression — or the HTTP-only Interactions endpoint, which is **Ed25519-verified and CPython's stdlib provides no Ed25519**. |

**Read that table as a product statement, not a footnote.** Outbound-only is nearly free everywhere:
`urllib.request` posting JSON to a Discord webhook, `chat.postMessage`, `sendMessage`, or `smtplib` to an
SMTP server needs nothing else — which is exactly why Apprise's two-step setup is achievable and why
Hermes's `standalone_sender_fn` marks the platforms that need no running gateway. **The library dependency
lives entirely on the inbound side, and Discord inbound is where it bites.**

Note also the second-order trap: the two stdlib-friendly inbound options for Slack, SMS and WhatsApp trade
the websocket for **a public URL**, which a local-first macOS gateway does not have. Botpress's one-step
onboarding is bought with `webhook.botpress.cloud` and a vendor-owned OAuth app; that is a product decision
about whether we ever operate a relay, and it should be made deliberately rather than discovered.

### A registry of names and a registry of implementations will drift, and the drift presents as a lie

OpenClaw's `isKnownChannel()` consults a hardcoded `CHANNEL_IDS` list while `getChannelPlugin()` reads the
live registry, so a configured channel reports as known and then fails with `Unknown channel: telegram`.
Repeated registry swaps at runtime lose registrations entirely, with a race "between" resolution and lookup
inside `sendMessage()`. The same confusion surfaces as a UX complaint in a separate issue, where
`Unknown channel`, `Unsupported channel` and `Package not found on npm` were all raised for one situation.

**Keep one registry, and make "known but not installed" a distinct, actionable error.**

### Discovery mechanisms fail silently and look like missing features

Hermes's PyPI v0.15.1 shipped an `entry_points.txt` with only console scripts, omitting the
`hermes_agent.plugins` group — so the loader never called `register(ctx)` and the gateway logged
`WARNING gateway.run: No adapter available for discord` **while the adapter sat installed and intact on
disk**, and the setup wizard did not offer Discord at all. OpenClaw's v2026.2.21/.22 disabled **33 plugins**
against configs that worked two releases earlier, surfacing as
`ENOENT: no such file or directory, access '/.../extensions/stock/telegram/index.ts'`.

**Entry-point and path-based discovery make packaging metadata a load-bearing runtime dependency.** For a
single-binary-ish stdlib tool, prefer an explicit registry the code owns, and make `doctor` prove that every
configured channel actually resolved to an implementation.

### One channel failing must not take the others down

Hermes exited the whole gateway when any configured platform failed to connect —
`Gateway failed to connect any configured messaging platform` — which meant a node with partial credentials
could launch nothing at all. The requested behaviour is obviously right in hindsight: **run with whatever
connected, log and skip the rest.** With one launchd job per agent and several channels inside it, this is
our failure mode exactly.

### An empty recipient set must mean nobody, never everybody

OpenClaw's `isApprovalRecordVisibleToClient` ends with `return true; // ← line 62: default-allow fallback`;
when nothing matched it returned false for every client, `resolveApprovalRequestRecipientConnIds()` yielded
an empty set, and the code fell through to `params.context.broadcast(...)` — "the unfiltered fallback —
which delivers to every connected client". **Approvals are the worst possible payload to get this wrong on**,
and we have approvals.

### Do not fuse the adapter with the dispatcher

Errbot's backends subclass `ErrBot`, not `Backend`, so four of the "abstract" methods are ones backends never
implement. The results: no way to test an adapter against the contract alone, no way to run two, every
backend reaching into the bot's namespace, and a 22 KB test-harness backend that exists because the boundary
is not clean. **Keep the adapter a plain object the core calls, never a base class the core is.**

Its sibling trap: **one adapter per process forecloses cross-channel identity permanently.** Errbot cannot
do requirement (c) at any price because of a single `BACKEND` string. Design many-adapters-one-core from the
first line.

### Do not make optional features mandatory-abstract

Every Errbot backend must implement `rooms` and `query_room`; Telegram's implementation is a raise, and the
core's own `!room list` does not catch it, so a user sees a traceback. **Optional features belong in
declared capabilities, not in the mandatory contract** — otherwise "capability negotiation" is an exception
round-trip that somebody forgets to catch.

### Do not offer an untyped passthrough bag

Errbot's `Message.extras: Mapping` leads to the Slack backend reading `msg.extras["slack_event"]["thread_ts"]`
— **every use makes a plugin non-portable**. Home Assistant's equivalent is `data: dict`, and its own
maintainers name it as the blocker: "I don't think we should add any parameters that allows non typed non
validated values to the new action service", with the consequence that every non-text capability is
stranded. Matterbridge's `Extra map[string][]interface{}` is where its type safety dies.

If provider passthrough is needed, **declare the keys** — Botpress's typed-key tags, or OpenClaw's
`payload.channelData.<channel>` — or do not offer it.

### Do not encode config in a URI

Apprise is the cautionary tale precisely because the URI is otherwise so good. The costs, all verified in its
own source and docs: **three separate redaction mechanisms** (`secure_logging`, `cwe312_url()`,
`privacy=` on every `url()`, `"private": True` per token) to undo one decision, failing silently if one call
site is missed; percent-encoding hell for passwords and `#channels` (`%23ops`), with their own troubleshooting
page warning that `&`, `/` and `%` "can cause quite a troubleshooting mess"; **no place to hang an ACL**,
because a URI is a value and not a key; and inevitable stringly-typed creep — `"3:endpoint:2"` encoding
priority, tag and retry into one token, alongside `?:key=value`, `w:` and Slack's `+`/`#`/`@` sigils. Config
and secrets were never separated, and the standing answer to two open requests remains "chmod the file".

**Accept a URI as an import format; normalize immediately into rows.** Home Assistant's inversion is the
right one — address a registry row with a stable id, and push credential and target into that row.

### Versioning the adapter contract is not optional, and migrating it is worse than you think

Home Assistant's legacy→entity migration has run for over two years with a dedicated `repairs` subsystem, a
`breaks_in_ha_version` field, a phase one covering **nine integrations** against 67+ legacy ones ("As soon as
we have `title` and/or `recipient` support we can migrate more" — `recipient` still is not there), **groups
regressing** so users had to enumerate `notify.telegram_bot_[chatid]_[userid]` ids by hand, and a concrete
breakage closed as "not planned". Botpress's capability interfaces are still at `version: '0.0.4'`.

**If the contract is versioned, version it explicitly from day one** — and expect that the second generation
will initially be unable to express what the first could.

### Attachments quietly assume a public file host

Matterbridge's `handleFiles()` either PUTs to a `MediaServerUpload` or writes to a path and builds
`MediaServerDownload + "/" + sha1sum + "/" + name`; its FAQ states that for Telegram "images/stickers/files
are from non-public url's, you'll need to setup a mediaserver". mautrix has a `mediaproxy` for the same
reason. **A local macOS gateway has no public URL.** Plan for native per-channel upload or explicit
attachment dropping — and surface which it is as a declared capability rather than discovering it in
production.

### Capability is a function of identity, not just of channel

The subtlest finding, and it couples requirements (b) and (c). In mautrix relay mode — the fallback when a
user is not linked — "reactions from relayed users will not be bridged at all, because the bot wouldn't be
able to bridge sender info nor multiple reactions of the same emoji". **A destination's capability set
changes depending on whether we know who the person is.** Model capability as
`f(adapter, destination, identity_state)`, not `f(adapter)`, or this will be retrofitted painfully.

### Vendored SDKs are a slow-motion outage, and vendor auth flows churn underneath you

Errbot pinned `slackclient>=1.0.5,<2.0` against an already-deprecated library, and when Slack changed
`rtm.start`'s response on 2022-09-20 the backend broke with no upgrade path. Its changelog is a list of
removals — GUI, HipChat, both Slack backends — and its core `backends/` directory now contains no Slack, no
Discord and no Mattermost. Matterbridge's Slack setup still walks users through creating a **"classic" app**
with "USE THE LINK AND DON'T CLICK THE 'Create New App' BUTTON" and "Add Legacy Bot User". mautrix removed
shared-secret login, breaking existing double-puppeting setups.

**Writing REST calls against documented HTTP endpoints on `urllib.request` — which stdlib-only forces on us
anyway — is more durable than depending on someone else's wrapper**, provided we treat the auth *flow* as
the volatile part and keep it behind the login-flow abstraction of pattern 10.

### Two entry points into one agent will drift

Hermes loaded `SOUL.md` and `AGENTS.md` correctly in the CLI path and not at all in the Telegram gateway
path, with the reporter's diagnosis being that "gateway handlers use a separate or simplified prompt-building
pipeline that bypasses context-file loading". **A channel-delivered turn and a CLI-delivered turn must share
the assembly code, not merely resemble it.**

### Small ones worth naming

- **Do not put media directives in the message body.** Hermes's `MEDIA:/path` in-band syntax forced two
  defensive maskers — `_mask_protected_spans()` to "mask code blocks and inline code to preserve example
  MEDIA tags" and `_mask_json_string_media()` to "protect JSON string values from media extraction". **Two
  maskers to undo one convenience; a flag would have cost nothing.**
- **Do not use `fnmatch` on a free-form identity string.** `BOT_ADMINS = ('@admin*',)` matches `@adminfoo`.
- **Do not search 27 paths for config.** Apprise's `DEFAULT_CONFIG_PATHS` is 27 candidates. Pick one, plus
  an env override.
- **Splitting is not markup-aware unless you make it so.** Apprise's own docs warn that "HTML formatting can
  break if split/truncate operations cut messages mid-tag", and that SPLIT mode against an SMS channel means
  "be prepared to get hundreds of text messages".
- **Silent-drop is a real answer, but say which you chose.** Home Assistant drops an unsupported `title`
  without error. That is defensible — but it is exactly the `DROPPED` (-1) versus `REJECTED` (-2)
  distinction from pattern 1, and it should be declared rather than discovered.
- **Do not compare secrets with `!=`.** Zulip's Botserver does; stdlib gives us `hmac.compare_digest`.
- **Privileged intents are a silent-failure trap.** Discord's Message Content and Server Members intents
  must be enabled in the developer portal or the bot connects and receives nothing — named as a trap by both
  OpenClaw's and Errbot's Discord setup docs. `doctor` should detect "connected but never received an event"
  and say so.

