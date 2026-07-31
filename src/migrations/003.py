"""Somewhere to put *why* a turn stopped, in a word rather than in prose.

A run that failed kept `why` — one free-text line an adapter scraped from stderr or from a
brain's own result. Nothing can branch on it, count it, or phrase it well, so a turn stopped
by a rate limit was indistinguishable from a crash, a bad flag, or a brain that simply died.

`because` is the closed word beside that sentence, not a replacement for it: `why` stays
exactly as it was and keeps saying what the brain said. A run that has one without the other
is normal in both directions — an adapter that cannot classify a failure leaves `because`
absent, which is every run written before this step and every adapter that never learns to.

**Rows written before this step stay NULL, and nothing tries to infer one from `why`.**
Reading a word out of prose after the fact is guessing, and a guessed reason counted in a
total is worse than an absent one: absent can be seen.

Additive and idempotent in effect: one nullable column, no default, nothing read differently,
no existing value rewritten.
"""


def up(conn, home):
    conn.execute("ALTER TABLE run ADD COLUMN because TEXT")
    return []
