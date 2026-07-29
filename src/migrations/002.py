"""Somewhere to put tokens written into a cache, which used to be counted as fresh input.

A brain that caches reports four differently-billed quantities and the run had three columns
for them, so cache writes were added to fresh input and stored as `tokens_in`. That is the
most expensive kind of input recorded under the cheapest label: a cache write bills above
standard input, a cache read bills at a fraction of it.

**Rows written before this step keep their folded value and are left alone.** The two
quantities cannot be separated after the fact — nothing kept the split, not the run row and
not the transcript — so `tokens_written` stays NULL on them. NULL is the honest answer and
the one the rest of this schema already uses for it: a run whose usage never arrived is
absent rather than zero, because an unknown amount and no amount are different facts. Filling
these with 0 would say the split *is* known and was nil, which is the one thing it is not.

Additive and idempotent in effect: one nullable column, no default, nothing read differently,
no existing value rewritten. A copy of rundesk from before this step reads every row it wrote
exactly as it did.
"""


def up(conn, home):
    conn.execute("ALTER TABLE run ADD COLUMN tokens_written INTEGER")
    return []
