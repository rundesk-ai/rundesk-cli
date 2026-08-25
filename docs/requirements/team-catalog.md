---
id: TEAM
name: Versioned agent teams, and what an install owes their declaration
last_verified: 2026-08-25
---

## What this is

A team catalog is a version-controlled skill catalog that also declares named agents. Installing one
creates those agents and gives the catalog ownership of their durable instructions, memory policy,
delegation scope, and skill allowlists. Provider accounts, channels, schedules, projects,
credentials, and models stay local to each install. What a team is and how it reconciles is
[../teams.md](../teams.md); this page holds what that must guarantee.

## Why it exists

- A team is worth version-controlling only if every install of it is the same team. An agent that
  drifts from its declaration is a different agent wearing the name.
- Reconciliation touches real agents with real memory, so a failure part-way through must leave the
  install exactly as it was rather than half-converted.
- An install holds agents no team declares. A team must never take one over, and must never leave
  one damaged.

## Requirements

**These rows were authored on 2026-08-25 from the acceptance list this document previously carried,
and have not been reviewed by the product owner.** They restate conditions that were already
written down; the wording is new. A ✅ names test methods observed to pass on 2026-08-25 in
`test_team_catalogs.py` (11 tests) and `test_teams_command.py` (32 tests). A ❌ is not a claim the
behavior is absent, only that nothing here proves it.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-TEAM-1 | A preview changes nothing and names the effect on every member before a confirmation is possible | `test_preview_changes_nothing_and_names_member_effects` |
| ✅ | R-TEAM-2 | A confirmed install creates every declared member, reconciles it, and leaves every gateway stopped | `test_confirm_creates_and_reconciles_every_member_with_gateways_stopped` |
| ✅ | R-TEAM-3 | Installation refuses a declared name already held by an existing agent, and names the command that would remove it | `test_install_refuses_an_existing_agent_and_names_its_removal_command` |
| ✅ | R-TEAM-4 | An agent no team manages is never taken over, repaired, or changed by an install, update, or refresh | `test_confirm_does_not_repair_or_change_an_unmanaged_agent`, `test_update_refuses_to_take_over_an_agent_no_team_manages` |
| ✅ | R-TEAM-5 | Each member holds exactly its declared allowlist; an unlisted grant is removed on reconciliation whichever catalog gave it, and an empty list removes every optional skill | `test_the_positive_allowed_list_removes_an_unlisted_catalog_grant`, `test_an_empty_allowed_list_removes_every_optional_skill` |
| ✅ | R-TEAM-6 | A team may not replace a product-owned operating skill, and only Rundesk's exact conditional delegation skill is protected | `test_a_team_cannot_replace_product_owned_operating_skills`, `test_only_rundesks_exact_conditional_delegation_skill_is_product_protected` |
| ✅ | R-TEAM-7 | Weekly upkeep is explicitly on or off per member, and a changed setting is applied on update | `test_weekly_upkeep_must_be_explicitly_on_or_off`, `test_update_applies_a_changed_weekly_upkeep_setting` |
| ✅ | R-TEAM-8 | A member may delegate only inside its declared team, and may hold no optional skills at all | `test_members_may_delegate_only_inside_the_declared_team`, `test_a_member_may_have_no_optional_skills` |
| ✅ | R-TEAM-9 | Unknown fields, unsafe instruction paths, an empty canonical workflow, a missing provider, and a second team owner are refused before anything is written | `test_unknown_fields_and_unsafe_instruction_paths_are_refused`, `test_an_empty_canonical_agent_workflow_is_refused`, `test_a_missing_provider_and_a_second_team_owner_are_refused` |
| ✅ | R-TEAM-10 | A changed catalog version moves instructions, grants, and delegation scope together | `test_changed_catalog_moves_instructions_skills_and_scope_together` |
| ✅ | R-TEAM-11 | Local drift is repaired even when the catalog tree is unchanged | `test_update_repairs_drift_even_when_the_catalog_tree_is_unchanged` |
| ✅ | R-TEAM-12 | Member reconciliation holds the install lock, and turn-admission reconciliation repairs installed state without fetching | `test_update_reconciles_members_with_the_install_lock_still_held`, `test_turn_admission_reconciliation_repairs_installed_state_without_fetching` |
| ✅ | R-TEAM-13 | A failure part-way through an update puts the team and every member back, and a member created before the failure is not an agent afterwards | `test_a_failure_part_way_through_an_update_puts_the_team_and_its_members_back`, `test_a_member_created_before_the_failure_is_not_an_agent_afterwards` |
| ✅ | R-TEAM-14 | A failed install leaves no catalog and no agent it created while keeping its dependencies, and a failed promotion leaves the promoted catalog as it was | `test_a_failed_install_leaves_no_catalog_and_no_agents_but_keeps_its_dependency`, `test_a_failed_promotion_leaves_the_catalog_it_promoted_as_it_was` |
| ✅ | R-TEAM-15 | A restore that cannot finish names the state that remains and a retry that would be valid, rather than reporting success | `test_a_failed_install_restore_names_the_state_that_remains_and_a_valid_retry`, `test_the_hold_itself_refuses_a_page_it_could_not_put_back` |
| ✅ | R-TEAM-16 | A member's page that was a symlink is put back as that symlink, and a directory standing where a managed page belongs refuses before anything moves | `test_a_members_symlinked_page_goes_back_as_that_symlink`, `test_a_directory_where_a_managed_page_belongs_refuses_before_anything_moves` |
| ✅ | R-TEAM-17 | A schema 2 team installs a missing declared dependency and reuses a matching installed one | `test_schema_two_installs_a_missing_shared_catalog_and_grants_its_skill`, `test_schema_two_reuses_a_matching_installed_catalog` |
| ✅ | R-TEAM-18 | A same-named dependency from another source, a dependency missing a referenced skill, and a skill from an undeclared catalog are each refused before the team changes | `test_schema_two_refuses_a_same_named_catalog_from_another_source`, `test_schema_two_refuses_a_dependency_missing_a_required_skill`, `test_schema_two_refuses_a_skill_from_an_undeclared_catalog` |
| ✅ | R-TEAM-19 | A dependency cannot replace a product skill, and an installed team protects its dependencies from removal and from a replacement that retires a referenced skill | `test_schema_two_cannot_replace_a_product_skill_from_a_dependency`, `test_an_installed_team_protects_its_dependency_from_removal_and_retirement` |
| ✅ | R-TEAM-20 | A failure after a dependency installs reports the partial result honestly rather than as success | `test_a_failure_after_dependency_install_reports_the_partial_safe_result` |
| ✅ | R-TEAM-21 | The same repository installs as skills only without creating agents or team ownership, is promoted in place later, and cannot then be moved by skill commands | `test_skill_commands_install_a_team_catalog_without_installing_the_team`, `test_skill_commands_cannot_move_a_catalog_installed_as_a_team`, `test_an_ordinary_catalog_may_carry_an_unrelated_team_json` |
| ✅ | R-TEAM-22 | A turn with command access can apply a confirmed team catalog operation exactly as a terminal caller can | `test_an_agent_turn_with_command_access_can_apply_a_confirmed_team_catalog` |
| ✅ | R-TEAM-23 | Only the team envelope is recognized as a declaration, and a complete team is read from catalog data | `test_only_the_team_envelope_is_recognized_as_a_declaration`, `test_a_complete_team_is_read_from_catalog_data` |
| ❌ | R-TEAM-24 | Each member's `AGENTS.md` and `CLAUDE.md` match the catalog byte for byte and no `MEMORY.md` remains | not proven — reconciliation is covered, but no test names the byte-for-byte page comparison or the absent memory page |
| ❌ | R-TEAM-25 | An unreadable member's records refuse that team before any dependency, gateway, catalog, or member changes, and the teams after it still refresh | not proven — no test names this ordering |
| ❌ | R-TEAM-26 | An agent holding a grant from the team's catalog but declared by no team has that grant put back, and its own pages and records left alone | not proven — no test names this case |

## Open questions

- Whether these rows say what the owner means. They were written from an acceptance list rather than
  from a product decision, and the three unproven ones may be requirements, may be implementation
  detail, or may already be covered by a test that does not name them.
- Whether schema 1 self-contained teams have an expiry. They remain accepted, and nothing here
  states for how long.
- Team reconciliation creates declared members and never retires an undeclared one, so renaming a
  member in a catalog leaves an orphaned agent on every existing install with its memory and grants
  intact and no removal step. Whether that orphan should be reported, adopted, or removed is
  undecided, and no requirement above covers it.
