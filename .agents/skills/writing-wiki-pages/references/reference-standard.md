# Reference standard

Two reference pages, each written to the standard and then written badly. Read both before writing a
reference page. [Reference pages](reference-pages.md) holds the rules; this shows what following them
looks like, and what a page that ignores them costs the person trying to call the thing.

The subjects — a notes program's export command and an invoicing endpoint — are invented. Your surface
will be something else. Nothing about the shape changes.

---

## Command, done well

~~~markdown
+++
title = "notes export"
subtitle = "write every note to a folder, one markdown file each"
status = "approved"
intent = """
notes export exists so that a person can take their notes anywhere, as plain files, in one command. It
should never overwrite a file it did not write.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Command", value = "notes export", cite = "usage" },
  { label = "Argument", value = "FOLDER", cite = "usage" },
  { label = "Options", value = "--since, --overwrite", cite = "usage" },
]

[[infobox]]
group = "Exit codes"
rows = [
  { label = "Success", value = "0", cite = "exit" },
  { label = "Refused", value = "1", cite = "exit" },
  { label = "Misuse", value = "2", cite = "exit" },
]
+++

`notes export` writes each note to `FOLDER` as one markdown file named after the note, and writes
nothing outside it.[^export] How notes are stored is described on [Storage](storage.md).

## Usage

The folder is required.[^usage]
```sh
notes export [--since DATE] [--overwrite] FOLDER
notes export --since 2026-01-01 ~/backup
```

## Options

| Option | Meaning | Default |
|---|---|---|
| `--since DATE` | export only notes changed on or after `DATE`, written `YYYY-MM-DD`[^usage] | every note |
| `--overwrite` | replace a file of the same name that an earlier export wrote | refuse |

## Output

It prints one line per file it writes, then a count.[^output]
```text
wrote ~/backup/groceries.md
exported 42 notes to ~/backup
```

## Exit codes

| Code | Condition | Message |
|---|---|---|
| `0` | every note was written[^exit] | `exported 42 notes to ~/backup` |
| `1` | a file of that name exists and `--overwrite` was not given | `~/backup/groceries.md exists; pass --overwrite to replace it` |
| `2` | `FOLDER` is missing, or `DATE` is not written `YYYY-MM-DD` | `--since must be a date written YYYY-MM-DD` |

[^export]: `src/export.py` — `export_all()` writes only under the folder it is given.
[^usage]: `src/cli.py` — `export_parser()` declares `FOLDER`, `--since` and `--overwrite`.
[^output]: `src/export.py` — `export_all()` prints each path and the final count.
[^exit]: `src/cli.py` — `main()` returns 1 for `FileExists` and 2 for a parser error.
~~~

## Command, done badly

~~~markdown
# Exporting Notes

The export command is a powerful way to back up your notes. Simply run it with the folder you want:

```
notes export [options] <folder>
```

## Options

- since: only exports recent notes
- overwrite: overwrites files

## What happens if something goes wrong?

If there's a problem, the command will display an error and exit with a non-zero status.
~~~

**The title is the command.** A reader looking for `notes export` finds `notes export`. "Exporting Notes"
is a task in title case, and a reader who knows the command's name has to guess that this is its page.

**The usage line is the help, exactly, and a real call sits under it.** `[options] <folder>` names
neither the options nor the form of the folder, and nothing shows what a working call looks like.

**Every option has a meaning, a format and a default.** "Only exports recent notes" leaves every question
open: how recent, written how, and what happens without it. The standard answers all three in one row.

**The names are the software's own.** `--since`, as a reader types it — not "since", which is not what the
program accepts.

**The failures are named.** Each exit code, the condition behind it, and the message word for word. "An
error and a non-zero status" is the half of the contract the reader needed, left out, and the `1` — a file
already there — is the code they will meet on their second export.

**The side effect is bounded.** "Writes nothing outside it" is a promise a reader relies on before
pointing the command at a folder, and the standard makes it only because the code keeps it, cited.

**Headings name the contract.** **Exit codes**, not a question.

**Nothing is sold.** "Powerful" and "simply" carry no fact; the standard has neither.

---

## Endpoint, done well

~~~markdown
+++
title = "POST /invoices/{id}/archive"
subtitle = "archive an invoice so it can no longer be changed"
status = "approved"
intent = """
Archiving exists so that an invoice that should no longer change, such as a duplicate, is locked without
being deleted from any report. It should be safe to retry, and impossible while money is still moving.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Method", value = "POST", cite = "request" },
  { label = "Path", value = "/invoices/{id}/archive", cite = "request" },
  { label = "Authentication", value = "bearer token", cite = "auth" },
]

[[infobox]]
group = "Limits"
rows = [
  { label = "Rate limit", value = "60 requests a minute", note = "per token", cite = "limits" },
  { label = "Note length", value = "500 characters", cite = "request" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Repeated call", value = "safe, changes nothing", cite = "response" },
  { label = "Pending payment", value = "refused", cite = "errors" },
]
+++

`POST /invoices/{id}/archive` archives one invoice. An archived invoice cannot be changed, and stays in
every report.[^archive] What archiving means for payments is described on [Invoices](../invoices.md).

## Request

The invoice is named in the path, and the reason in the body.[^request]
```http
POST /invoices/4127/archive
Authorization: Bearer TOKEN
Content-Type: application/json

{"reason": "duplicate"}
```

## Authentication

Every request carries a bearer token. A missing, expired or revoked token returns `401` and archives
nothing.[^auth]

## Parameters

| Name | In | Type | Required | Meaning |
|---|---|---|---|---|
| `id` | path | integer | yes | the invoice to archive[^request] |
| `reason` | body | string | yes | one of `duplicate`, `void` or `paid_elsewhere` |
| `note` | body | string | no | free text, at most 500 characters; absent and `null` both mean no note |

## Responses

| Status | When | Body |
|---|---|---|
| `200` | the invoice was archived, or was already archived[^response] | the invoice, with `status` set to `archived` and `archived_at` to the time of the first archive |

## Errors

| Status | Code | Condition | Message |
|---|---|---|---|
| `401` | `TOKEN_INVALID` | the token is missing, expired or revoked[^errors] | `The access token is not valid.` |
| `404` | `INVOICE_NOT_FOUND` | no invoice has that `id`, or it belongs to another account | `No invoice with id 4127.` |
| `409` | `INVOICE_HAS_PENDING_PAYMENT` | a payment on the invoice has not settled | `Invoice 4127 has 1 pending payment; settle or cancel it first.` |
| `422` | `REASON_INVALID` | `reason` is missing, or is not one of its three values | `reason must be one of: duplicate, void, paid_elsewhere.` |

## Limits

At most 60 requests a minute for each token. The 61st returns `429`, with a `Retry-After` header giving
the seconds to wait.[^limits] Archiving an invoice twice is safe: the second call returns `200` and changes
nothing.[^response]

## Example

The response to the request above. Its `archived_at` is the time of your own call.[^response]
```json
{"id": 4127, "status": "archived", "archived_at": "2026-03-02T14:05:00Z", "reason": "duplicate"}
```

[^archive]: `app/invoices/archive.py` — `archive_invoice()` sets the status and locks the record.
[^request]: `app/routes.py` — the `archive` route and `ArchiveRequest`.
[^auth]: `app/auth.py` — `require_token()`.
[^response]: `app/invoices/archive.py` — `archive_invoice()` returns early for an archived invoice.
[^errors]: `app/invoices/errors.py` — the four error classes and their messages.
[^limits]: `app/limits.py` — `RATE_PER_MINUTE`, read by `throttle()`.
~~~

## Endpoint, done badly

~~~markdown
# Archive Invoice

Use this endpoint to archive invoices.

**URL:** `/invoices/:id/archive`

### Parameters

- id (required) - The invoice ID
- reason - The reason

### Response

Returns the invoice object.

### Errors

Returns standard error responses.
~~~

**The request line is the first fact.** The failure never says `POST`. A caller cannot guess the method,
and the path's `:id` is a second spelling of `{id}` that the router does not accept.

**Authentication is stated, with its failure.** The failure never mentions a token, so the first call
returns `401` and the page has nothing to say about why.

**Every parameter answers four questions.** "reason — The reason" gives no type, does not say whether it
is required, and hides its three accepted values. A caller discovers them by collecting `422`s.

**The response says what changed.** "Returns the invoice object" does not say which fields move, so a
client cannot tell whether the call worked without fetching the invoice again.

**Every error is listed, with its condition and its message.** "Standard error responses" hides four
failures, each with a different recovery. The `409` is the error an integrator meets in production, and
nothing in the failure tells them it exists.

**Repeating a call is answered.** A client whose request timed out needs to know whether retrying is safe.
The standard says so, and cites the code that makes it true; the failure leaves the client to find out.

**Headings and titles follow one convention.** The failure's title is a verb phrase in title case and its
sections drop to a third level. The standard titles the page with the request line and names each section
for its part of the contract.

**Nothing restates the name.** "The invoice ID" beside `id` adds nothing. "The invoice to archive" says
which invoice matters.

---

## Shared qualities

**A reader could make the call from the page alone** — and recognize a failure, and know its cause.

**Every infobox row cites.** Each names the footnote the prose cites for the same fact, and each footnote
names the code that does the thing.

**Examples were run.** The output is what the program printed, trimmed only of what changes between runs,
and the page says so where it does.
