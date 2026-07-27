"""Let the channel's activity choice settle Discord's legacy default.

Discord once wrote its own default, ``off``, into platform settings even when the owner left
Rundesk's channel activity on. The two records then disagreed, and the adapter's stale value
won forever. The channel activity field is the owner's choice under R-CH-6, so remove only
that contradictory adapter override. A channel whose owner used ``--no-activity`` keeps both
its core choice and its platform setting untouched.
"""

import json


def up(conn, home):
    """Remove the legacy Discord default inside the runner's transaction."""
    rows = conn.execute(
        "SELECT name, settings FROM channel"
        " WHERE kind = 'discord' AND activity = 1"
        " ORDER BY name"
    ).fetchall()
    for row in rows:
        settings = json.loads(row["settings"])
        if not isinstance(settings, dict):
            raise ValueError(f"channel {row['name']} settings are not an object")
        if settings.get("activity") != "off":
            continue
        del settings["activity"]
        conn.execute(
            "UPDATE channel SET settings = ? WHERE name = ?",
            (json.dumps(settings, sort_keys=True), row["name"]),
        )
    return []
