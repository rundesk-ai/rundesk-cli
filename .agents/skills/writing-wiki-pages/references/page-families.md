# Page families

Read this before organizing a set of pages, and before writing a page whose siblings are the same kind of
thing as it. It holds how to find a family, how to design the layout its members share, what the parent
page holds, and a family written well and written badly.

The example is a family of notification channels, chosen because most applications send notices more than
one way. Your family will be something else: the brands under a sites page, the providers under a payments
page, the plans under a pricing page. Nothing about the method changes.

## Families

A **family** is a set of pages about things of one kind: each member is one instance of the same class of
thing, and a reader asks every member the same questions. **Every member of a family shares one layout**:
the same headings in the same order, and the same infobox groups and labels. A reader who has read one
member knows where to look on every other, and can set two members side by side.

- **The test is the parent's title followed by "such as".** "Notification channels, such as email and text
  messages" names a family. "Billing, such as invoices and the refund settings" does not: an invoice and a
  settings file are different kinds of thing, and each page keeps the shape its own subject needs.
- **One kind, one parent.** The members of a family nest under one page, which introduces them. A family
  spread across parents cannot be compared, because no page shows its members together.
- **Two members make a family.** A page written alone keeps its own shape. When a second page of its kind
  arrives, the layout is designed for both, and the first page is rewritten to it.
- **A reference page already has a layout.** Commands, endpoints, functions, settings files, events and
  forms take theirs from [Reference pages](reference-pages.md), and a family of them shares that layout.

## Layout

**The layout is designed once, for the whole family**, before its members are written or rewritten.

1. **List the questions each reader asks of every member**, for each reader the Readers section of
   `SKILL.md` names: the stakeholder, the product owner, the engineering team and, when the family is for
   customers, the customer. Take the questions, not the facts the first page happened to hold.
2. **Name each answer as a heading**, by the naming method in `SKILL.md`: how fast a notice arrives is
   **Delivery**; how many can be sent is **Limits**; what happens when one fails is **Failures**; how a
   person stops them is **Opting out**.
3. **Order the headings as a reader meets the thing**: what it does first, then its limits, then how it
   fails. Every member keeps that order.
4. **Choose the infobox rows the same way**: the names and figures a reader compares across members, in
   the groups [Infobox](infobox.md) describes, with the same label on every member.
5. **Ask for approval of the layout before rewriting any page to it.** The layout decides what every
   member covers, so it needs approval.

Each member then keeps to the layout:

- **The same headings, in the same order.** A heading that does not apply to a member is left out, never
  renamed and never replaced by another. An empty section is never written.
- **The same infobox groups and labels, in the same order**, each filled with the member's own value and
  citation. A value the member does not have is left out; a value a stated requirement
  asks for and nothing provides is marked missing.
- **A section the others lack changes the layout.** Add it to every member it applies to, once the new
  layout is approved, or give that member a child page for it. A member with sections of its own can no longer be
  compared with its siblings section by section.
- **Third-level headings follow the member.** Inside a section of the layout, a member divides its content
  as its own subject needs.
- **A member's title names only what sets it apart**: **Email**, not "Email notification channel".

## Parent page

The parent is the family's front page, and a page like any other: an intent, a cited statement in every
sentence, and a place in the sidebar.

- **Its lead says what every member has in common and names the sections each member covers**, so a
  reader knows the layout before opening a member.
- **It lists every member in one table**: a row for each member and a column for each value the members
  share, so the members compare at a glance and a missing member shows as a missing row. Declare its columns
  as `table`, as [Declaration](#declaration) shows, and the build writes it from each member's infobox, so
  the table always matches the member pages.
- **A fact true of every member is stated once, on the parent**, and each member links to it rather than
  repeating it.

## Declaration

Once a layout is approved, the parent's front matter declares it, and `wiki check` holds every member
to it:

```toml
[family]
headings = ["Delivery", "Limits", "Failures", "Opting out"]
labels = ["Channel", "Setting", "Delivery", "Daily limit", "Retries", "Opting out"]
table = ["Delivery", "Daily limit", "Retries"]
```

- **`headings`** lists the second-level headings, in order. A member may leave any of them out; a heading the
  list does not hold, or one out of its order, is refused.
- **`labels`** lists the infobox labels a member may use, in any group and any order. A label the list does
  not hold is refused.
- **`table`** lists the infobox labels the parent's member table compares, each one a label `labels` holds.
  The parent puts `{family-table}` on its own line where the table goes, and the build writes one row per
  member, linked, with each member's value for each label, and an empty cell where a member states none.
- **The parent links every member**, or the check names the member it does not link. A parent with
  `{family-table}` links every member through the table.
- **Each refusal names both fixes**: rename the heading or label on the member, or add it to the list on the
  parent, for every member.
- **`wiki families`** lists every parent of two or more children that declares no family, with each child's
  headings side by side, and every nested title that repeats a word of its parent's title. It only reports.

---

## Done well

The parent, **Notification channels**:

> **Notification channels** are the ways the application tells a person that something happened to their
> account: an order shipped, a payment failed, a password changed. Each channel's page covers delivery,
> limits, failures and opting out.
>
> | Channel | Delivery | Daily limit | Retries |
> |---|---|---|---|
> | [Email](channels/email.md) | within a minute | 50 a person | 3, over an hour |
> | [Text messages](channels/text-messages.md) | within ten seconds | 10 a person | none |

Two members, **Email** and **Text messages**:

> **Email** sends each notice to the address on a person's account.
>
> ## Delivery
>
> A notice leaves within a minute of the event that caused it.
>
> ## Limits
>
> A person receives at most 50 emails a day. The 51st is dropped, and the account page still shows it.
>
> ## Failures
>
> An email the receiving server refuses is sent again three times over an hour, then dropped.
>
> ## Opting out
>
> Every email ends with a link that stops that kind of notice by email, and no other kind.

> **Text messages** send each notice to the phone number on a person's account.
>
> ## Delivery
>
> A notice leaves within ten seconds of the event that caused it.
>
> ## Limits
>
> A person receives at most 10 text messages a day. The 11th is dropped, and the account page still shows
> it.
>
> ## Failures
>
> A text message that cannot be delivered is not sent again.
>
> ## Opting out
>
> Replying STOP ends every text message to that number.

Both members fill the same infobox:

```toml
[[infobox]]
group = "Identity"
rows = [
  { label = "Channel", value = "email", cite = "channel" },
  { label = "Setting", value = "notify.email", cite = "setting" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Delivery", value = "within a minute", cite = "delivery" },
  { label = "Daily limit", value = "50 a person", cite = "limit" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Retries", value = "3, over an hour", cite = "failures" },
  { label = "Opting out", value = "a link in every email", cite = "optout" },
]
```

## Done badly

> **Email**
>
> ## Overview
>
> ## SMTP configuration
>
> ## Bounces and other problems

> **Text messages**
>
> ## Pricing
>
> ## Sending limits
>
> ## Unsubscribe handling
>
> ## Provider notes

Each page can be true, and each reads well enough alone. **Together they cannot be compared.** The email
page never says how many can be sent, the text message page never says what happens when one fails, and a
reader who found the limits on one page has to hunt for them on the other.

## Differences

**A reader who has read one member knows where everything is on the next.** Limits is the second section
on both pages, under the same word, so a reader goes straight to it.

**Every member states the same facts.** Text messages are never sent again, and the Failures section says
so. In the failed version the same fact is absent, and nothing tells a reader it was ever looked for.

**The parent compares.** One table answers "which channel is faster" and "which one retries" without
opening either page, and a channel with no row is a channel with no page.

**Headings name what a reader came for.** "SMTP configuration" is how email happens to be sent, which an
engineer finds through the references. **Delivery** is what a reader of either page wants to know.

**The same fact has the same name.** "Sending limits" on one page and nothing on the other become
**Limits** on both; "Unsubscribe handling" becomes **Opting out**, the words a person uses.

**A section that does not apply to a member is left out**, never renamed into a section that does.

## Definition of done

1. Every set of pages about things of one kind nests under one parent and shares one layout.
2. Each layout is approved.
3. Every member carries the layout's headings in its order, leaving out only those that do not apply, and
   no second-level heading of its own.
4. Every member's infobox uses the family's groups and labels.
5. The parent's lead names the sections every member covers, and its table lists every member.
6. The parent declares the layout as `[family]`, and `wiki check` passes.
