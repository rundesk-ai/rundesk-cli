```bash

# rundesk ask <agent> <prompt>
rundesk messages <agent> [--adapter <adapter>] [--limit <n>] [--search <query>]

# managing the channels
rundesk channels <agent> add <adapter> --owner <user> [--allow <user>] [--token-stdin]
rundesk channels <agent> update <adapter> [--owner <user>] [--allow <user>]
rundesk channels <agent> show <adapter>
rundesk channels <agent> remove <adapter>

# MANAGING THE SCHEDULES
# --------------------------------------------
# list all the schedules for an agent
rundesk schedules list <agent> 
# add a new schedule for an agent
rundesk schedules add <agent> <schedule> [--when <cron>] [--at <moment>] [--ask <prompt>] [--provider <provider>]
# update an existing schedule for an agent
rundesk schedules update <agent> <schedule> [--when <cron>] [--at <moment>] [--ask <prompt>] [--provider <provider>]
# run a schedule for an agent
rundesk schedules run <agent> <schedule>
# show details of a schedule for an agent
rundesk schedules show <agent> <schedule>
# remove a schedule for an agent
rundesk schedules remove <agent> <schedule>

# MANAGING THE SKILLS
# --------------------------------------------
# lists all the skills available (filtering by agent)
rundesk skills list [<agent>]
# list all the skill catalogs repos
rundesk skills catalogs
# install a skill from a catalog repository
rundesk skills install <repository> [--confirm]
# remove a skill catelog repo
rundesk skills remove <catalog> [--confirm]
# update a skill catelog repo
rundesk skills update <catalog> [--confirm]
# grant an individual skill to an agent
rundesk skills grant <agent> <skill>
# revoke an individual skill from an agent
rundesk skills revoke <agent> <skill>

# MANAGING THE GATEWAYS
# --------------------------------------------
# displays a list of all the gateways, their status of online/offline
rundesk gateways
rundesk gateways list
# start a gateway that is offline
# returns error if gateway is already online
rundesk gateways start <agent>
# stop a gateway that is online
# returns error if gateway is already offline
# <agent> or --all, one of the two is required and never both
# force kills it where it stands instead of waiting for it to finish
rundesk gateways stop [<agent>] [--all] [--force]
# restart a gateway that is online or offline
# returns error if gateway is already offline
# all does all gateways at once 
# force restarts the gateway without waiting for it to turn off
rundesk gateways restart [<agent>] [--all] [--force]
# view the logs of that specific gateway (from newest to oldest)
rundesk gateways logs <agent> [-n <lines>]
# be the gateway for this agent here, in this terminal — what the launchd job runs
rundesk gateways run <agent>

# MANAGING THE AGENTS
# --------------------------------------------
# listing all the agents alpha by their name
rundesk agents list
# adding a new agent with the specified provider
rundesk agents add <agent> --provider <provider>
# configuring an existing agent with the specified provider
rundesk agents configure <agent> --provider <provider>
# removing an agent
# confirm is required — without it, it says what it would take and takes none of it
rundesk agents remove <agent> --confirm

# MANAGING THE ENV
# --------------------------------------------
# displays a list of all the env variables (does not show full values, just first 3 characters and last 3 with x's between)
# the list should show in table format and grouped by their name (alpha)
rundesk env list
# checks if env variable is set
rundesk env check <key>
# sets an env variable, requires it to be inputted interactively
# values are encrypted with a salt hash preventing plain text values
rundesk env set <key>
# unsets an env variable to null
rundesk env unset <key>

# MANAGING BACKUPS
# --------------------------------------------
# displays a list of available backups newest to oldest (names of each backup in location)
rundesk backups
# create a new on-demand back up and returns the backup name
rundesk backups save
# restores the data from a given back up and it must have a hook that runs after
# the hook later will be used for things like running migrations if the data is older. 
# confirm is required — without it, it says what it would do and does none of it
rundesk backups restore <backup> --confirm
# moves the backups to a new location and symlinks it back to the original location
rundesk backups set-location <path>

# MANAGING RUNDESK
# --------------------------------------------
# displays the current version, the rundesk location, config values
rundesk status
# displays the current version and auto-checks if out of date
rundesk version
# updates the rundesk install otherwise says up to date with version
rundesk update
# uninstalls rundesk (confim is required, and purge deletes all data, otherwise data remains)
rundesk uninstall --confirm [--purge]
# configures the rundesk config.json
# the flags are generated from the configuration, so a new setting is settable the day it lands
rundesk configure [--backup-enabled <yes|no>] [--backup-retention <n>] [--update-enabled <yes|no>] [--update-time <HH:MM>]
# what install.sh runs; both are optional and both default under RUNDESK_HOME
rundesk install [--source <dir>] [--bin-dir <dir>]

```

Database `state.db`

config
- agent_name  (string)
- agent_provider (string)
- agent_model (string | nullable | unused)
- agent_instructions (string | nullable | unused)
- agent_settings (json)
- owner_name (string)
- last_seen_at (datetime | nullable)

migrations
- key (string | PK)
- completed_at (datetime)

schedules
- id (int)
- name (string | Unique)
- enabled (boolean)
- cron (string | nullable)
- run_at (datetime | nullable)
- expire_at (datetime | nullable)
- agent_provider (string | nullable)
- agent_model (string | nullable | unused)
- agent_prompt (text | nullable)
- command (text | nullable)
- channel (string | nullable)
- channel_place_id (string | nullable)
- last_outcome (string | nullable) -> 'stopped' | 'failed' | 'completed'
- last_run_at (datetime | nullable)
- created_at (datetime)

channels
- key (string | PK)
- owner_id (string)
- allowed (json)
- settings (json)
- secrets (json)
- agent_provider (string | nullable)
- agent_model (string | nullable | unused)
- agent_instructions (string | nullable | unused)
- created_at (datetime)

conversations
- id (int | PK)
- source (string) -> 'channel' | 'schedule' | 'terminal' | 'agent' | 'role'
- source_id (string)
- channel (string | nullable)
- created_at (datetime)
- last_at (datetime)

conversation_messages
- id (int | PK)
- conversation_id (string | FK)
- turn_id (int | FK)
- author (string) -> 'agent' | 'user' | 'rundesk'
- author_id (string)
- body (text)
- created_at (datetime)

Indexed message tables: 
- conversation_messages_fts
- conversation_messages_fts_config
- conversation_messages_fts_data
- conversation_messages_fts_docsize
- conversation_messages_fts_idx

delegations
- id (int | PK)
- label (string)
- parent_turn_id (int | FK)
- report_message_id (int | FK)
- turn_id (int | FK)
- type (string) -> 'role' | 'agent'
- target (string) -> 'development' | 'research' | 'planning' etc or agent 'cole" etc
- brief (text)
- state (string) -> 'queued' | 'running' | 'reporting' | 'delivered' | 'failed'
- outcome (string) -> 'stopped' | 'failed' | 'completed'
- attempts (int)
- claimed_at (datetime | nullable)
- delivered_at (datetime | nullable)
- created_at (datetime)
- latest_at (datetime)

turns
- id (int | PK)
- conversation_id (int | FK)
- message_id (int | FK)
- provider (string | nullable)
- model (string | nullable | unused)
- session_resumed (boolean)
- started_at (datetime)
- ended_at (datetime | nullable)
- outcome (string) -> 'stopped' | 'failed' | 'completed'
- exit_code (int | nullable)
- tokens_in (int)
- tokens_out (int)
- tokens_cached (int)

turn_records
- id (int | PK)
- turn_id (int | FK)
- seq (int)
- received_at (datetime)
- type (string) -> 'think' | 'tool' | 'result' | 'done' | 'usage' etc
- event_data (json)

provider_sessions
- conversation_id (string | FK)
- provider (string)
- session_id (string)


Rundesk local:

/.rundesk/~  everything is stored here
/.rundesk/app/~ the installed app that is replaced on updates (does not hold state/data), this is the full repo download.
/.rundesk/data/~ all agent/user data is stored here
/.rundesk/data/README.md - tells an agent what this folder is briefly.
/.rundesk/backups/~ the backups of 'data' and symlinked if moved
/.rundesk/backups/README.md - tells an agent what this folder is briefly. 
/.rundesk/projects/~ a empty/shared directory for agents to install repos into 
/.rundesk/projects/README.md - tells the agent what this directory can be used for if they enter it. a simple message about using it for shared projects, like git repos.

/.rundesk/.rundesk.lock - held while one command at a time changes this install

/.rundesk/data/agents/~ houses each of the agents that are added
/.rundesk/data/logs/~ all rundesk level logs like updates, backups etc
/.rundesk/data/catalog/~ the catalog of skills installed
/.rundesk/data/skills/~ all individual skills get stored here (and symlinked to the catalog if installed)

/.rundesk/data/config.json - the configuration for all of rundesk (backup_enabled, backup_retention, update_enabled, update_time).

/.rundesk/data/agents/alan/~ the specific agent directory
/.rundesk/data/agents/alan/logs/~ all logs related to alan's gateway, starts, failures etc
/.rundesk/data/agents/alan/state.db - the state database for alan's gateway (all his presistent state, messages, history etc)

/.rundesk/data/agents/alan/home/~ the lander of where the agent starts

/.rundesk/data/agents/alan/sessions/<id>/~ each individual session goes into an isolated home directory 

Each sesison has:
- AGENTS.md
- CLAUDE.md

All the symlinked skills are here for CLI agents to auto load.
- /.grok/skills/~
- /.claude/skills/~
- /.codex/skills/~
- /.agents/skills/~
- /skills/~

/.rundesk/data/agents/alan/home/MEMORY.md
/.rundesk/data/agents/alan/home/SOUL.md
