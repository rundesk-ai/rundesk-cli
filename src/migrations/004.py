"""Keep the name an owner sees separately from the directory identity rundesk uses.

Older records named an agent only through its directory. Those directories are deliberately
not renamed here: a running gateway, its launchd job, logs, provider homes, channel homes and
every command all use that exact identifier. Moving only the directory would strand the rest,
and two legacy directories may normalize to the same slug on a case-sensitive filesystem.

Existing agents receive their exact directory spelling as the display fallback. That preserves
the identity their templates and turns already used. New agents overwrite the fallback with the
exact human name supplied during creation.
"""


def up(conn, home):
    conn.execute("ALTER TABLE agent ADD COLUMN display_name TEXT NOT NULL DEFAULT ''")
    conn.execute("UPDATE agent SET display_name = ? WHERE id = 1", (home.name,))
    return []
