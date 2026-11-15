# Sources

Verified 16 August 2026. This package is an original Rundesk synthesis of the public guidance below;
rules are narrowed to the audience and ecosystem each source supports.

## Terminology and interface writing

- [Microsoft, Style and tone](https://learn.microsoft.com/en-us/windows/win32/uxguide/text-style-tone)
  explains that consistent terminology reduces the need to decide whether different words mean the
  same action, and recommends parallel syntax for parallel interface elements. This supports one
  canonical product term without requiring identical spelling at every technical boundary.
- [Microsoft Style Guide, Top 10 tips](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice)
  uses sentence-style capitalization as Microsoft's default and omits terminal punctuation from
  headings and UI titles. This package treats those as useful English UI defaults, not universal law.
- [Apple Human Interface Guidelines, Writing](https://developer.apple.com/design/human-interface-guidelines/writing)
  recommends verbs for buttons and links and consistent formatting for each interface element type.
  Its platform-specific examples are why this skill defers to the owning design system.
- [GOV.UK Design System, Error message](https://design-system.service.gov.uk/components/error-message/)
  requires specific, concise recovery text and reuse of field-label language in errors. It also
  separates examples and hints from the error slot.
- [Microsoft Research, language choices](https://www.microsoft.com/en-us/research/?p=689796)
  reports findings from surveys, moderated and unmoderated studies, and practitioner roundtables
  across Microsoft admin products; the authors conclude that consistent terminology and content
  patterns improve predictability and scanning. The evidence concerns those products, not every
  audience.

## Accessibility

- [W3C WAI, Labeling controls](https://www.w3.org/WAI/tutorials/forms/labels/) requires labels that
  describe control purpose and recommends programmatic association, preferably with native HTML.
- [W3C WAI, Providing accessible names and descriptions](https://www.w3.org/WAI/ARIA/apg/practices/names-and-descriptions/)
  explains that interactive elements need short, distinguishing accessible names and that visible,
  native text reduces maintenance and accessibility failures.
- [WCAG technique G211](https://www.w3.org/WAI/WCAG21/Techniques/general/G211) explains why the
  accessible name should match the visible label for speech input. WCAG 2.5.3 requires the visible
  text to be contained in the accessible name; it does not require exact equality.
- [W3C WAI, Form instructions](https://www.w3.org/WAI/tutorials/forms/instructions/) explains that
  placeholders disappear and must not replace labels or required instructions.
- [W3C WAI, User notifications](https://www.w3.org/WAI/tutorials/forms/notifications/) recommends
  concise errors that reference the field and explain correction, plus success feedback when needed.

## Code, data, and contracts

- [PEP 8](https://peps.python.org/pep-0008/) documents Python-specific naming forms and explicitly
  prioritizes internal consistency. It supports deferring casing and prefixes to the language and
  repository instead of presenting one naming convention as a cross-language rule.
- [Google AIP-140, Field names](https://google.aip.dev/140) requires the same name for the same
  concept and different names for different concepts within Google-style protobuf APIs. It also
  makes scalar fields singular, repeated fields plural, field names nouns, and measurable quantities
  carry unit suffixes. This package uses those as scoped examples for values and contracts, not as
  universal rules for every language or protocol.
- [Google AIP-180, Backwards compatibility](https://google.aip.dev/180) treats renaming a public API
  element as removal plus addition and therefore a breaking change in the same major version. This
  supports staged contract renames rather than synchronized copy edits.
- [Simon Holywell, SQL style guide](https://www.sqlstyle.guide/) is a practitioner convention for
  consistent, descriptive SQL identifiers and avoiding cryptic abbreviations. Its table plurality
  and casing choices are examples, not SQL requirements.
- [Laravel 13.x, Eloquent model conventions](https://laravel.com/docs/13.x/eloquent#eloquent-model-conventions)
  documents the singular model to plural `snake_case` table derivation, the default `id` primary
  key, and managed `created_at` / `updated_at` timestamps. [Eloquent relationships](https://laravel.com/docs/13.x/eloquent-relationships)
  documents inferred foreign keys and relationship methods. These support the Laravel profile only;
  they do not establish universal SQL naming.
- [PostgreSQL lexical structure](https://www.postgresql.org/docs/current/sql-syntax-lexical.html)
  explains that unquoted identifiers fold to lower case and quoted identifiers remain case
  sensitive. This supports deferring engine identifier mechanics to the active database skill.
- [AlSuhaibani et al., method naming practices](https://arxiv.org/abs/2102.13555) surveys more than
  1,100 professional developers and reports broad agreement that method-naming standards matter and
  are applied. It supports treating naming as a reviewable engineering concern; it does not establish
  one universal naming form across languages or ecosystems.

## Catalog conclusions

The sources do not establish one universal vocabulary workflow. This package therefore labels and
scopes the following synthesis instead of attributing it to a source:

Any retained do/don't pair not mapped directly to a citation above is a catalog conclusion, not a
claim that a source mandates that exact wording. Its adjacent `Why`, failure-prevented column, or
failure prose is the scoped rationale and boundary for applying it; keep the contrast so an agent
can distinguish the rejected form from its replacement, but do not generalize it beyond that named
failure.

- Prefer a precise concept name over placeholders such as `data` or `item`; the stated failure is
  that a reader must reconstruct the value's meaning from assignments and callers.
- Name an operation for its observable outcome; the stated failure is that a generic verb such as
  `process` or `handle` makes the reader reconstruct the outcome from the implementation.
- Put regulated wording, published compatibility, and established ecosystem conventions ahead of a
  catalog default; those are authority constraints, while the default is only a preference.
- Preserve stored data, dashboards, alerts, and other consumers during non-API renames; AIP-180
  directly supports only published API compatibility, while these rows are conservative catalog
  workflow conclusions with the affected consumer named.
- Preserve immutable third-party names at an adapter boundary and document the canonical mapping;
  this is a catalog workflow conclusion, not a claim that AIP-180 governs vendor schemas.
- Prefer positive predicates only when they preserve the same fact. Negative domain facts,
  regulated wording, and fixed contracts are scoped exceptions; silently inverting them can change
  behavior rather than improve a name.
- Recommend an exact name, architecture, interaction, owner, or risk severity only when the supplied
  evidence establishes it. Otherwise state the assumption or decision needed. This is an execution
  guardrail against false precision, not a sourced universal naming rule.
- Comment non-obvious workflow sequencing, state handoffs, side-effect boundaries, and the reason a
  future maintainer must preserve them; avoid narrating self-evident statements. This is a catalog
  maintainability conclusion whose named failure is stale prose becoming a second, conflicting
  description of the program.
- Treat missing meaning as unresolved rather than completing the scenario with plausible domain
  behavior. This restraint applies to names and to example comments; otherwise illustrative text
  is easily mistaken for a verified contract.
- Write confirmation consequences with the specific entity, availability change, affected existing
  relationships, and truthful recovery path. Vague pronouns and generic permanence language hide
  the decision a user is authorizing; this is a catalog interface-writing conclusion bounded by the
  product behavior actually established.

## Forward-test evidence

Neo ran first-hand CLI trials on 16 August 2026 against Codex, Claude, Antigravity, and Grok provider
adapters. Tasks covered cross-layer subscription vocabulary, published and vendor contracts,
orthogonal states, nullable inheritance, accessibility labels, regulated wording, retry and event
semantics, acronym casing, absence states, localization, lexicon scope, and code-flow comments.

- Fresh blind Codex and Antigravity sessions discovered the installed skill without the task naming
  it, then read the applicable references. This verifies provider-native discovery for those two
  adapters in that Rundesk installation; it does not prove discovery for every provider or setup.
- Claude and Grok applied the skill correctly in initial tasks. Their later adversarial passes reused
  those sessions, so those passes test continued application rather than isolated discovery.
- Fresh Codex and Antigravity sessions then loaded the revised branch artifact directly. Codex kept
  the response bounded and left unknown operation names unresolved. Antigravity preserved contracts
  but still invented internal identifiers, event targets, workflow precedence, and transaction
  behavior, and it ignored the requested concise scope.
- A later fresh Codex Laravel/PostgreSQL pass preserved framework defaults, explicit ORM mappings,
  vendor fields, and the public API while refusing to name or comment an unknown operation. It still
  promoted one model's configured table, primary key, and relationship exceptions into the project
  lexicon; the lexicon reference now keeps such local ORM configuration with its model unless the
  exception recurs or changes product vocabulary.
- The matching fresh Antigravity pass preserved the same convention boundaries and correctly refused
  an unsupported operation name and flow comment. It remained substantially longer than requested,
  restated supplied facts as verification, and added unneeded framework configuration and migration
  decisions. Proportional-output and evidence guardrails therefore remain explicit requirements,
  not merely style preferences.
- Fresh Codex and Antigravity confirmation-copy passes both named the record, exact availability
  change, existing-use effect, and recovery or irreversibility, and both refused exact copy when
  those material facts were absent. Codex stayed bounded and read only the product-interface
  reference; Antigravity loaded the whole package and returned redundant status scaffolding. The
  passes exposed ambiguity around title/button objects, role-gated recovery, deadline wording, and
  whether missing material facts block the modal; the product-interface and lexicon references now
  state those decisions directly.
- In the final fresh regression pass, both Codex and Antigravity stayed below a 120-word limit, read
  only the core skill and product-interface reference, rejected reassuring filler, withheld the
  unknown title and confirm action, supplied only the verified availability sentence and `Cancel`,
  and requested the material existing-use, deletion, recovery, permission, deadline, and action-verb
  facts. This pass verifies the revised restraint and reference-routing behavior for that prompt on
  those two adapters.
- The reproduced failures led to explicit meaning, constraint, evidence, proportional-reporting,
  comment-factuality, boundary-mapping, orthogonal-state, nullable-override, localization, and
  high-level-lexicon guardrails in this package.

These are qualitative forward tests, not a controlled benchmark or proof that wording alone governs
every model. Retest fresh sessions after material instruction changes, keep prompts free of expected
answers, and record whether a session was fresh, resumed, blind to the skill name, or given the
artifact path.
