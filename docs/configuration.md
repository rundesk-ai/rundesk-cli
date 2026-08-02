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
