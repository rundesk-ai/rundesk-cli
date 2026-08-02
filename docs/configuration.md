# Install-wide configuration

`~/.rundesk/data/config.json` is the source of every install-wide value. A fresh install
writes the complete configuration, including automatic update and backup times and the
skills every agent must receive:

```json
{
  "backups": {
    "at": "04:00",
    "keep_days": 30
  },
  "updates": {
    "at": "03:00"
  },
  "roles": {
    "quiet_hours": 6
  },
  "skills": {
    "granted": [
      "managing-rundesk",
      "managing-schedules",
      "delegating-to-roles",
      "filing-github-issues",
      "writing-github-pull-requests",
      "writing-plans",
      "organizing-workspaces"
    ]
  }
}
```

Change `updates.at` and run `rundesk update` to reschedule automatic updates.

`roles.quiet_hours` is how long work handed to a role may produce nothing at all before
Rundesk settles the run and tells the agent that handed it over. It measures inactivity
rather than total runtime — a specialist execution legitimately takes hours and keeps
writing records the whole time — so raise it only if a brain here goes genuinely silent
for longer than that while still working.

A skill in `skills.granted` is attached to every new and existing agent and cannot be
revoked until it is removed from this list. Updates and reinstalls restore missing
required grants without removing optional skills an owner added.

Backups are kept outside the program and agent data, so an update, uninstall, or data
purge cannot remove them. The backup directory may also be a symlink to a synced folder:

```sh
rundesk backups on
rundesk backups
```

Use `rundesk backups restore <backup>` to preview and restore a saved installation.
