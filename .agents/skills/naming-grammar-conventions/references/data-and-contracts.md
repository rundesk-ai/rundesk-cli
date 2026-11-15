# Name data and contract fields

Dos and don'ts for anything stored or transmitted: tables, columns, enums, migrations, REST paths, API fields, error codes, webhook events, and structured logs.

These names outlive every screen built on top of them. A column name survives three interface redesigns and four engineers. Name it for the person reading it in 2031 with no context.

## Parity across layers

When compatibility and audience needs permit, use one canonical term for the same concept and express it in each layer's convention:

```
reason          column
reason          API field
reason          form field
Reason          label
Reason          export header
```

**The parity test:** trace each layer back to the same canonical concept. Do not require mechanical spelling parity when a stable public contract, localization, privacy boundary, computed value, or audience-specific label requires a documented mapping.

| Don't | Do |
|---|---|
| New owned column `why`, label `Reason` | Name the new column `reason` |
| New owned column `retry_setting`, label `Retry limit` | Model and name the value as `retry_limit` |
| New owned column `cust_flg`, API `customerType`, UI `Client` | Choose one concept, then apply its layer forms |
| Scattered aliases hiding an owned name with no compatibility constraint | Fix the owned name or stage its migration |

Undocumented display-layer aliasing makes drift permanent: the next engineer reads the column, not
the view mapping, and may invent a third name. A documented adapter mapping is different: use one
for vendor schemas, generated payloads, published legacy fields, privacy-specific presentation, and
other names outside the change's authority. Prefer descriptive names for new work; assess migrations,
reports, integrations, and rollback before renaming stable owned data.

---

## Tables, fields, and cardinality

Use `database-design` and the owning framework to choose table plurality, join-table form, casing,
timestamps, foreign keys, and constraints. Do not turn one ecosystem's convention into a universal
rule. For example, Laravel conventionally pairs a singular model such as `Invoice` with a plural
table such as `invoices`; another stack may choose differently.

Cardinality still belongs in the name at the point of use: a field holding one value is singular,
such as `invoice_id`; a field or API value holding a collection is plural, such as `invoice_ids` or
`invoices`. Table plurality is an ecosystem convention, not evidence that each row holds multiple
values.

Compose a stored name from the concept, property, and representation needed to make `table.column`
read as one precise fact. Omit a repeated concept when the table supplies it unambiguously
(`invoices.name`), but qualify a generic representation when the property would otherwise disappear
(`publication_status`, `sale_amount`). Bare `status`, `type`, or `value` may be precise inside a
tightly bounded model or may collide with framework behavior; inspect the owning model and framework.

| Don't | Do | Failure prevented |
|---|---|---|
| `invoice_ids` holding one identifier | `invoice_id` | The plural falsely promises a collection. |
| `invoice_id` holding several identifiers | `invoice_ids` | The singular hides cardinality. |
| `tbl_invoice`, `invoice_tb` | The framework's established table form | Storage prefixes add no domain meaning. |
| `data`, `records`, `misc_settings` | The actual concept in the framework's form | Generic nouns make unrelated tables indistinguishable. |

---

## Columns

**Common form:** `snake_case`, singular, naming the value. Follow the schema's convention; avoid redundant types, table prefixes, and non-domain abbreviations.

| Don't | Do | Why |
|---|---|---|
| `reason_text`, `name_str`, `count_int` | `reason`, `name`, `count` | The type is in the schema and it changes |
| `invoice_invoice_name` | `name` | The table already says invoice |
| `col1`, `field_2`, `misc` | The meaning | Unnameable means undesigned |
| `qty_rcv`, `dt_crt` | `quantity_received`, `created_at` | Save the keystrokes elsewhere |
| `why`, `who_asked` | `reason`, `requester_id` | Question words are not names |
| `retry_mode_flag` | `retry_limit` | Names the mechanism, not the value |
| `notes2`, `extra_field` | Name the second meaning, or don't add it | A numeric suffix is a missing concept |

**Don't create a column you cannot define in one sentence.** If the definition needs "sometimes it holds X, but if Y then Z," you have two columns.

---

## Booleans in the database

**Recommended form:** use the schema's predicate convention. `is_` / `has_` / `can_` stated positively is a useful default.

| Don't | Do |
|---|---|
| `active` | `is_active` |
| `is_not_active`, `disabled`, `no_email` | `is_active`, `email_enabled` |
| `deleted` (when "when" matters) | `deleted_at` timestamp, null when live |
| `flag`, `status` holding true/false | Name the condition, or make it an enum |
| `is_active` + `is_archived` + `is_draft` | One `status` enum |

**Don't let mutually exclusive booleans multiply into a state machine.** Three booleans express
eight combinations, of which perhaps three are legal. Use an enum when the states cannot coexist.
Keep separate fields when they represent orthogonal facts that may coexist, and document their legal
combinations rather than collapsing meaning for tidiness.

Prefer a positive predicate when it expresses the same fact: `WHERE NOT is_not_active` is harder to
read than `WHERE is_active`. Preserve negative domain facts and fixed contracts, then contain or map
them instead of silently inverting their meaning.

---

## Timestamps and dates

Name the event, then use the database and framework's established suffix. `{event}_at` for an
instant and `{event}_on` for a civil date are useful examples where that convention is already in
force; they are not universal database rules.

| Don't | Do |
|---|---|
| `date_created`, `when_archived`, `crt_dt` | `created_at`, `archived_at` |
| `timestamp`, `date`, `time` | The event it records |
| `effective_date_date` | `effective_on` |
| Undocumented local time in a timestamp | A documented timezone-aware strategy, commonly UTC; preserve domain-local dates or civil times when that is the business fact |

**Do** name for the business event, not the row operation. `received_at` (when the document arrived) and `created_at` (when we inserted the row) are different facts, and conflating them destroys reconciliation.

**Do** document the temporal model. UTC timestamps are a strong default for instants; domain-local dates and civil times remain local when that locality is the fact being stored.

---

## Foreign keys and relations

Use the owning framework's foreign-key form. `{singular_entity}_id` is common, but a role-bearing
name may disable framework inference and require explicit relationship configuration.

| Don't | Do |
|---|---|
| `invoice`, `invoiceid`, `fk_invoice` | `invoice_id` |
| `parent_id` with no indication of parent type | `parent_invoice_id` |
| `user_id` used for two different roles | `created_by_id`, `assigned_to_id` |

**Do** distinguish two references to the same entity, such as `created_by_id` and `approved_by_id`,
instead of `user_id` and `user_id_2`. Configure the relationship explicitly when the role-bearing
name differs from the framework's inferred key.

---

## Enums and stored states

**Form:** stored values are `snake_case` (or `SCREAMING_SNAKE`, chosen once per codebase). Values are **states**, expressed as adjectives or past participles.

| Don't | Do |
|---|---|
| `archive`, `suspend` | `archived`, `suspended` |
| `1`, `2`, `3` in the column | Named values |
| `Active`, `PENDING_REVIEW`, `paused` mixed | One case convention |
| `status` holding `'Archived (see notes)'` | The enum value only |

**Do not store presentation text as a machine state.** Storing `Pending review` as the enum means a
copy change becomes a data migration. This does not prohibit stored user-authored content or
regulated verbatim text whose value is the text itself.

**Do not render machine values directly.** Keep an authoritative stored-to-display mapping in each client or shared presentation layer. Localization and consumer-specific presentation may require separate mappings. A view that merely replaces underscores can turn `awaiting_invoice_confirm` into poor interface text.

**Do** keep the enum's legal values and their display terms together in the lexicon.

---

## Nullability semantics

Decide and document what each absent-value case means. Ambiguity here produces bugs that no amount of good naming fixes.

| State | Meaning | Renders as |
|---|---|---|
| `NULL` | One documented absence meaning for this field | `—` or the product's documented absence marker |
| Explicit state | Unknown and not applicable are different domain meanings | Distinct, localized labels |
| `0` | Known to be zero | `0` |
| `''` | Known to be empty | `—` or blank, chosen once |
| Sentinel (`-1`, `9999`) | Don't | Never use one |

| Don't | Do |
|---|---|
| `-1` meaning "unlimited" | An explicit domain state or separate `is_unlimited` boolean chosen by the model |
| `''` and `NULL` both used in one column | Pick one, add a constraint |
| Rendering `0` as `—` | They are different facts |

Define configured, inherited, and effective values separately. A nullable override may be a stable
contract where `NULL` means inherit; do not call it a simple boolean or migrate it to an enum without
inventorying defaults, queries, clients, and precedence. Exact display labels for unknown, not
applicable, withheld, and redacted are product, locale, accessibility, privacy, and threat-model
decisions. Even revealing that a value was redacted can be sensitive.

---

## Money, units, and precision

| Don't | Do |
|---|---|
| `price` as a float | `price_cents` as an integer |
| `amount` with no currency | `amount_cents` plus `currency_code` |
| `timeout`, `distance`, `size` | `timeout_seconds`, `distance_meters`, `size_bytes` |
| Percentages stored inconsistently (0.15 in one column, 15 in another) | One convention, named: `rate_bps` or `rate_percent` |

**Include the unit when it could be misread.** A number whose unit lives only in a doc comment can be misread, especially when it represents money.

---

## JSON columns

| Don't | Do |
|---|---|
| A `meta` or `data` blob absorbing new fields indefinitely | Promote recurring keys to real columns |
| Mixed key cases inside the document | The same convention as columns |
| Storing display strings or computed values | Store facts |

JSON columns are where naming discipline goes to die, because nothing enforces a schema. Anything queried, filtered, or shown in a table belongs in a column.

---

## Indexes and constraints

**Common explicit form:** `{table}_{columns}_{type}`. Prefer the framework or engine's generated form
when the project relies on it; predictable generated names are part of that stack's convention, not
drift to rewrite manually.

```
invoices_name_unique
documents_invoice_id_received_at_index
line_items_invoice_id_foreign
```

Constraint names appear in raw database errors. A meaningful one lets you map a violation to a domain error and a user-facing message; `idx_4` does not.

### Laravel / Eloquent convention profile

Use this profile only in a Laravel application whose repository has not deliberately configured
another form:

| Element | Conventional form |
|---|---|
| Model | Singular `PascalCase`: `Invoice`, `AirTrafficController` |
| Table | Plural `snake_case`: `invoices`, `air_traffic_controllers` |
| Primary key | `id` |
| Foreign key | Singular related model plus `_id`: `account_id`; configure role-bearing exceptions |
| Relationship method | Singular for one, plural for many, in PHP method casing |
| Managed timestamps | `created_at`, `updated_at` |
| Migration | Framework timestamp plus descriptive schema operation |

These spellings preserve Eloquent's inference and reduce configuration. They are Laravel defaults,
not general SQL rules. Existing explicit table, key, timestamp, pivot, morph, or relationship-key
configuration remains authoritative.

---

## Migrations

**Form:** `{timestamp}_{verb}_{object}`. The verb states the schema change.

| Don't | Do |
|---|---|
| `update_table`, `fix_stuff`, `migration_12` | `rename_why_to_reason_on_archived_records` |
| `add_column` | `add_retry_limit_to_line_items` |

**Do** enumerate the full fanout of a rename: column, index, constraint, API field, validation rule, form field, label, export header, saved filters or reports, and lexicon entry. Change private names atomically; stage stored and published contracts through expand, migrate, deprecate, and contract steps.

---

## REST paths

**Form:** plural nouns for resources; the HTTP method supplies the verb.

| Don't | Do |
|---|---|
| `POST /createInvoice` | `POST /invoices` |
| `GET /getInvoiceById/4` | `GET /invoices/4` |
| `POST /invoices/4/doArchive` | `POST /invoices/4/archive` (a real state transition) |
| `/invoice`, `/Invoices`, `/line-items` | `/invoices`, `/line-items` |

**Do** allow a verb in the path only for genuine actions that are not CRUD on a resource: `/invoices/4/archive`, `/invoices/9/send`. Do not use it as a workaround for a resource you have not modeled.

**Query parameters** are `snake_case` (or the API's single convention) and name the filter field: `?status=active&invoice_id=4`. Pagination parameters are consistent across every endpoint.

---

## API fields and payloads

| Don't | Do |
|---|---|
| Mixing `camelCase` and `snake_case` in one payload | One convention, API-wide |
| Leaking accidental internal names into a public contract | Use the canonical concept term or document an intentional API mapping |
| Returning raw enum plus a display string | Return the enum; the client maps it |
| `id` of ambiguous type across endpoints | Consistent identifier type and format |
| Booleans named negatively | Positive form |

**Do** treat the API contract as a published vocabulary. Renaming a field is a breaking change; preserve existing versions and introduce a replacement through the API's compatibility policy.

Preserve immutable third-party fields exactly at the adapter boundary. Record the canonical mapping,
but do not use a vendor spelling such as `VAT_ID` as precedent for new first-party fields.

---

## Error codes and messages

**Code form:** `SCREAMING_SNAKE_CASE`, `{ENTITY}_{CONDITION}`. Stable forever; clients branch on it.

| Don't | Do |
|---|---|
| `ERR_5`, `BAD_REQUEST` for everything | `INVOICE_NUMBER_TAKEN`, `PAYMENT_WINDOW_EXPIRED` |
| Changing a code's meaning | Add a new code |
| Codes derived from HTTP status alone | The domain condition |

**Message form:** name the entity and condition, then write detail for the audience. UI text needs recovery; logs need safe diagnostics; API clients need a stable code.

| Don't | Do |
|---|---|
| `Something here already goes by that name` | `An invoice with that name already exists.` |
| `Invalid value` | `retry_limit must be between 1 and 8.` |
| `SQLSTATE[23000]: Integrity constraint violation` | Map to a domain error at the boundary |
| `The received_at field must be a valid date.` | Rewrite framework defaults in display language |

**Do** include a reference identifier on unexpected errors so a user's report maps to a log line.

---

## Webhooks and published events

**Common form:** `{entity}.{past-tense verb}`, lowercase and dotted. Follow the published event convention when it differs.

| Don't | Do |
|---|---|
| `invoiceUpdate`, `INVOICE_EVENT`, `invoice.change` | `invoice.archived`, `invoice.payment_terms_updated` |
| `invoice.archive` (imperative) | Past tense. If it has not happened, it is a command, not an event. |
| `row_updated` | The business fact |

**Do** name for the business fact rather than the row write. `invoice.paid` survives a schema redesign; `invoices_updated` forces every consumer to diff payloads to find out what happened.

An event name states the business fact, not transport guarantees. Do not add `once`, `unique`, or
similar promises unless the published contract establishes them. When replacing a published event,
follow the event-versioning policy; dual publication can itself create duplicate processing and is
not an automatic safe default.

---

## Structured logs and metrics

**Log field keys** use the canonical concept term where contracts permit, with documented mappings for deliberate differences. A support engineer should be able to trace `invoice_id` across storage, payloads, and logs.

| Don't | Do |
|---|---|
| `cid`, `invoiceID`, `invoice` used across three services | `invoice_id` everywhere |
| Free-text log lines with values interpolated into prose | Structured fields plus a short factual message |
| `log.info("doing the thing now")` | `log.info("archiving invoice", invoice_id=4)` |

Use `completed`, `succeeded`, or `failed` only when the logged boundary is defined. A handler return,
database commit, queued side effect, and externally visible outcome are different facts. Include
attempt and correlation identifiers when the system already defines them; do not invent an envelope
or idempotency contract as part of a naming review.

**Metric names:** follow the metrics ecosystem. Prometheus commonly uses `{subsystem}_{measure}_{unit}`, such as `invoice_rate_sync_duration_seconds`; other systems differ. Include the unit whenever ambiguity is possible.

---

## Files, exports, reports

| Don't | Do |
|---|---|
| Export headers that drift accidentally from on-screen terms | The same canonical term, with documented locale or format mappings |
| `export(1).csv`, `report_final.xlsx` | `invoices_2026-03-04.csv` |
| Raw enum values in an export | The display terms the user sees on screen |

A user reconciling a spreadsheet against a screen should not have to translate accidental
vocabulary drift. Export headers are a UI slot that happens to live in a file, but locale, machine
readability, published formats, and accessibility may require an intentional documented mapping.
