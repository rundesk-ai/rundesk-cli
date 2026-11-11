# Page standard

The page below is the standard every page is written to. Read both versions
before writing a page. **The contrast teaches more than either version alone**, and more than the rules
do: rules tell you what not to do, an example tells you what good looks like.

The subject here is a session in a web application, chosen because every reader has one. Your subject
will be something else. Nothing about the shape changes.

---

## Done well

> **Sessions** are how the application remembers who you are between requests. They live in
> [storage](../storage.md), which is where eviction and replication are described — this page covers what
> a session is for and what it does.
>
> ## Expiry
>
> A session ends thirty minutes after its last request. Each one carries its own clock, so a hundred
> people signing in together do not all expire together.
>
> A session that expires while you are typing **does not lose the work**. The draft is held for another
> day and reattached when you sign in again. That is deliberate — expiry is meant to make a stolen
> session useless, not to punish a user who went to lunch.
>
> ## Size
>
> A session holds at most 4 kB. Past that the write is refused and the request fails loudly rather than
> silently dropping what would not fit.
>
> Nothing is compressed. A 4 kB limit on what you actually wrote is easier to reason about than a larger
> limit on what happens to compress well.
>
> ## Signing out
>
> Signing out ends that session and no others, so **a second device stays signed in**.

## Done badly

> Sessions are an important part of the authentication subsystem. They are a core concept in the
> application and have a number of interesting properties worth understanding.
>
> ## Expiry and timeouts
>
> Sessions have a timeout. The timeout is configurable per deployment and defaults to a reasonable value.
> When a session's timeout elapses it will be invalidated and the user will be required to
> re-authenticate. Draft persistence behavior may vary depending on configuration.
>
> ## Storage and limits
>
> Session data is stored in a backing store with a size cap. Writes exceeding the cap are handled
> according to the configured overflow policy. Compression is not currently enabled.

Everything in the failed version is *true*. That is what makes it worth studying — **it fails without
lying**. Correct, complete, flat, and unread.

## Differences

Go through these against your own draft, one at a time.

**The lead says what the page is not about.** "They live in storage, which is where eviction and
replication are described — this page covers what a session is for and what it does." One sentence stops
a reader looking here for the wrong thing, and stops this page growing into that one.

**It says the consequence, never the mechanism.** "A session that expires while you are typing does not
lose the work" is what a person needs. "Draft persistence behavior may vary depending on configuration"
describes machinery and leaves the reader arithmetic they have no numbers for.

**The numbers are there, and both halves of a comparison sit together.** "Thirty minutes." "At most
4 kB." Not "a reasonable value" and not "a size cap" — a figure a reader can check by watching, in a unit
they would notice being wrong.

**The surprising thing gets its one clause of reason.** "Expiry is meant to make a stolen session
useless, not to punish a user who went to lunch." A rule that looks wrong gets reported as a bug; one
clause ends the question and saves a round trip with whoever has to answer it.

**A consequence a reader would not expect is stated where they would look for it.** "A second device
stays signed in." It says what signing out does today, at the point the reader would reach for it — not a
section called "Not built yet", and no promise about what comes next.

**Headings name their contents.** Expiry. Size. Signing out. Not "Expiry and timeouts", which says the
same thing twice, and not "How sessions work", which is the writer wondering what to put there.

## Infobox

The same page's infobox, to the standard:

```toml
[[infobox]]
group = "Identity"
rows = [
  { label = "Cookie", value = "session_id", cite = "cookie" },
  { label = "Setting", value = "session.timeout", cite = "timeout" },
]

[[infobox]]
group = "Limits"
rows = [
  { label = "Expiry", value = "30 minutes", note = "after the last request", cite = "expiry" },
  { label = "Size limit", value = "4 kB", cite = "size" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Overflow", value = "refused, never truncated", cite = "size" },
  { label = "Signing out", value = "this device only", cite = "signout" },
]
```

And the failure:

```toml
[[infobox]]
group = "Info"
rows = [
  { label = "What it is", value = "Sessions remember who you are between requests." },
  { label = "Timeout", value = "configurable" },
  { label = "Expires", value = "yes" },
  { label = "Class", value = "SessionStore" },
  { label = "Compression", value = "not currently enabled" },
]
```

**Identity comes first, and it holds names a person uses.** The cookie a user finds in their browser, the
setting an operator changes. Not the class, which only the code knows and a reader never types.

**Every label is a noun, and the value completes it.** "Expiry · 30 minutes" reads as a statement. "What
it is" is a question with a sentence for an answer, which is the lead's job, and "Expires · yes" is a verb
with nothing a reader can check.

**The values are figures.** Thirty minutes and 4 kB, not "configurable", which is a fact the writer never chased.

**Each group is named for what it holds.** Identity, Limits, Rules. "Info" names nothing; every row is
information.

**What is absent stays out.** Compression is not something sessions do, and a row for it is a gap list in
the most visible place on the page.

**Every row cites.** Each row names the footnote the prose cites for the same fact, so it carries the
same number and a reader can follow it to the code. The failure's rows cite nothing: five claims a reader
cannot trace, in the most visible place on the page. The extract above shows no footnotes only because it is
an extract; a real page defines each one the infobox names.

## Self-edit

Before you call a page done, read it once for each of these. They are quick and they are not optional.

1. **Cut every sentence that does not serve the intent.** Not shorten — cut. If that empties a section,
   the section was the problem.
2. **Find every hedge and either get the number or say it is unknown.** "Reasonable", "may vary",
   "generally", "a number of" — each one is a fact you did not chase.
3. **Read only the first line of each section.** A reader who stopped there should still be right.
4. **Check every claim against the code again**, not against the draft. A page derived from another page
   inherits its errors.
5. **Say what is uncertain.** Emergent, untested, or you could not determine it — say so. A confident
   sentence covering a gap is the worst thing you can leave here, because the reader is using this
   *instead of* the code and has no way to catch it.
6. **Read the headings alone, in order.** They are the page's table of contents and most readers will
   read nothing else.
7. **Read the infobox alone.** Each row should read as a statement a reader could check, and each should
   already be said on the page.
8. **Read the page once as each reader.** The stakeholder reads the intent and the lead and knows what the
   thing is for; the product owner reads the headings and the infobox and knows its rules and limits; an
   engineer follows any sentence to its code. Rewrite each part that leaves its reader without those facts.

## Conventions

**A sibling page is linked as `name.md`.** The tool turns it into a clean address. Writing the address by
hand looks right, and works in only one of the places a site is read: off disk or published.

**A reference names code, never a project document.** The extract above carries none only because it is
an extract; a real page ends with references, and every one points at a file and a function — or, for how
an outside service behaves, at that service's own documentation. The gate
refuses a reference that cites a `.md`, because a page of prose is not an answer to "where does this
happen" — it is another claim that can be wrong in the same way.

**A page that never surprised its writer probably was not read carefully enough.** Writing a page from
the code routinely turns up assumptions in the stated requirements that are not true. If yours turned up
nothing, you summarized another document instead of reading what runs.
