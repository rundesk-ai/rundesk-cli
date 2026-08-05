"""The `skills` verb group, driven as somebody typing it.

Every case here goes through `cli.main` and asserts on what a person or a script would see: the exit
code, what landed on stdout, what landed on stderr. Nothing looks at internals — those are held by
the suites for each module — and nothing asserts on a credential's value, because none is ever
printed.

The exit codes are the part worth being careful about. A listing that found nothing exits zero; a
`--confirm` that was left off exits non-zero having done nothing, because a script reading zero would
take it for done; and `doctor` exits non-zero when anything is wrong, so it can be gated on.

Run directly: `python3 tests/test_skills_command.py`
"""

import os
import unittest
from pathlib import Path
from typing import List, Optional
from unittest import mock

from fixtures_skills import a_published_catalog, a_skill

import support
from rundesk.agents import directory
from rundesk.core import secrets
from rundesk.skills import catalogs, grants, library, needs
from rundesk.utils import locking

A_JIRA = {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com",
}


class Skills(support.Isolated):
    """A scratch install with the library made and a catalog published on disk to install from."""

    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True, exist_ok=True)
        self.published = self.home / "published"

    def a_source(self, name: str = "acme", version: str = "1.0.0",
                 skills=("writing-plans", "jira")) -> Path:
        source = a_published_catalog(self.published / name, name=name, version=version, skills=())
        for one in skills:
            a_skill(source / library.INSIDE / one,
                    needs=dict(A_JIRA) if one == "jira" else None)
        return source

    def install(self, name: str = "acme", **how) -> None:
        code, _out, err = self.rundesk("skills", "install", str(self.a_source(name, **how)),
                                       "--confirm")
        self.assertEqual(0, code, err)

    def typing(self, *said: Optional[str]):
        """Answer each prompt in turn, the way somebody at a terminal would."""
        return mock.patch("rundesk.commands.env.typed", side_effect=list(said))

    def a_site(self, profile: str = "", **only: str) -> None:
        wanted = only or {one: f"value for {one}" for one in A_JIRA}
        for env, value in wanted.items():
            secrets.stated(needs.named(env, profile), value)


class WhatAnEmptyInstallSays(Skills):
    def test_a_listing_that_found_nothing_exits_zero_and_says_what_to_type(self):
        code, out, err = self.rundesk("skills")
        self.assertEqual(0, code)
        self.assertIn(str(library.where()), out)
        self.assertIn("rundesk skills install", out)
        self.assertEqual("", err)

    def test_the_bare_verb_and_list_are_the_same_thing(self):
        self.assertEqual(self.rundesk("skills"), self.rundesk("skills", "list"))

    def test_catalogs_says_where_it_looked(self):
        code, out, _err = self.rundesk("skills", "catalogs")
        self.assertEqual(0, code)
        self.assertIn(str(library.where()), out)

    def test_doctor_with_nothing_granted_exits_zero(self):
        code, out, _err = self.rundesk("skills", "doctor")
        self.assertEqual(0, code)
        self.assertIn("nothing", out)


class InstallingACatalog(Skills):
    def test_without_confirm_it_says_what_would_land_and_lands_none_of_it(self):
        code, out, err = self.rundesk("skills", "install", str(self.a_source()))
        self.assertEqual(1, code)
        self.assertEqual("", out, "a preview on stdout is a refusal a script reads as the answer")
        self.assertIn("acme 1.0.0", err)
        self.assertIn("writing-plans", err)
        self.assertIn("--confirm", err)
        self.assertEqual([], library.known())

    def test_the_preview_says_what_each_skill_will_want(self):
        _code, _out, err = self.rundesk("skills", "install", str(self.a_source()))
        self.assertIn("JIRA_API_TOKEN", err)

    def test_with_confirm_it_installs_and_grants_nothing(self):
        code, out, _err = self.rundesk("skills", "install", str(self.a_source()), "--confirm")
        self.assertEqual(0, code)
        self.assertIn("acme 1.0.0 installed", out)
        self.assertIn("granted  none", out)
        self.assertEqual(["acme"], library.known())

    def test_a_source_that_is_neither_a_directory_nor_a_repository_is_refused(self):
        code, out, err = self.rundesk("skills", "install", "git@github.com:a/b", "--confirm")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("github.com", err)

    def test_installing_one_that_is_there_says_to_update_it(self):
        self.install()
        code, _out, err = self.rundesk("skills", "install", str(self.a_source()), "--confirm")
        self.assertEqual(1, code)
        self.assertIn("update", err)


class CheckingACatalog(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()

    def test_without_confirm_on_a_source_holding_the_same_tree_it_says_nothing_would_change(self):
        # Non-zero even so, because the answer to `--confirm` being absent is always "this did not
        # happen", and a script reading zero would take it for done.
        #
        # **The preview has to promise what the confirm will do.** A directory source has no `ETag`
        # and so always hands back a whole tree, which had this reading "would replace acme's tree"
        # while `--confirm` on the very same source answered "up to date" — a preview describing
        # something that does not happen.
        code, out, err = self.rundesk("skills", "update", "acme")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("is up to date", err)
        self.assertIn("nothing would change", err)
        self.assertIn("--confirm", err)
        self.assertNotIn("1.0.0 to 1.0.0", err,
                         "a version movement is named only when there is one")

    def test_the_preview_and_the_confirm_say_the_same_thing_about_the_same_source(self):
        # The two are one decision — `catalogs.brings_a_change` — and this is what holds them to it.
        _code, _out, preview = self.rundesk("skills", "update", "acme")
        _code, said, _err = self.rundesk("skills", "update", "acme", "--confirm")
        self.assertEqual("nothing would change" in preview, "nothing changed" in said)

    def test_without_confirm_a_local_edit_inside_the_catalog_is_still_named_as_drift(self):
        # The one case where an identical source really does mean a replacement: what is standing
        # drifted, so the tree that came back is not the tree on disk. This is how drift is repaired,
        # and the preview has to say the edit will go.
        drifted = library.tree("acme") / library.INSIDE / "writing-plans" / library.DECLARED
        drifted.write_text("---\nname: writing-plans\ndescription: edited by hand.\n---\n",
                           encoding="utf-8")
        code, _out, err = self.rundesk("skills", "update", "acme")
        self.assertEqual(1, code)
        self.assertIn("would replace acme's tree", err)
        self.assertIn("discard any local edit", err)

    def test_a_far_end_that_says_nothing_changed_is_told_apart_from_that(self):
        # The cheap answer the whole `ETag` round trip exists to get. Different words, because it is
        # a different fact: there is nothing to replace at all.
        def nothing_changed(_source, _etag, _into):
            return None

        code, out, err = support.run_with(["skills", "update", "acme"],
                                         refreshing=nothing_changed)
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("is up to date", err)
        self.assertIn("nothing would change", err)

    def test_the_preview_names_a_skill_that_would_be_taken_away(self):
        self.a_source(version="1.1.0", skills=("writing-plans",))
        _code, _out, err = self.rundesk("skills", "update", "acme")
        self.assertIn("1.0.0 to 1.1.0", err)
        self.assertIn("take    jira", err)

    def test_with_confirm_and_nothing_changed_it_says_so_once(self):
        code, out, _err = self.rundesk("skills", "update", "acme", "--confirm")
        self.assertEqual(0, code)
        self.assertIn("up to date", out)
        # **Once.** `catalogs.update` says the outcome through its `saying` seam for the sweep that
        # has no other voice, and this verb renders it out of what came back — handed both, one
        # `rundesk skills update` printed the outcome twice, once indented and once not.
        self.assertEqual(1, out.count("up to date"))

    def test_with_confirm_it_never_claims_nothing_was_fetched_of_a_tree_that_arrived(self):
        # A local directory hands back a whole tree every time. Saying "nothing was fetched" of that
        # is false; saying "nothing changed" is true of it and of a `304` alike.
        code, out, _err = self.rundesk("skills", "update", "acme", "--confirm")
        self.assertEqual(0, code)
        self.assertNotIn("nothing was fetched", out)

    def test_with_confirm_on_content_that_moved_under_one_version_it_says_the_tree_was_replaced(self):
        # The defect this pair of tests exists for: reading the answer off the versions, this
        # replaced the entire tree and reported "up to date, and nothing was fetched".
        self.a_source(version="1.0.0", skills=("writing-plans", "jira", "filing-issues"))
        code, out, _err = self.rundesk("skills", "update", "acme", "--confirm")
        self.assertEqual(0, code)
        self.assertIn("its tree was replaced, at the same version", out)
        self.assertNotIn("up to date", out)
        self.assertNotIn("1.0.0 -> 1.0.0", out, "a version movement is named only when there is one")
        self.assertIn("filing-issues", [one.name for one in library.held("acme")],
                      "the tree it reported replacing really was replaced")

    def test_with_confirm_on_a_real_version_move_it_names_the_move_once(self):
        self.a_source(version="1.1.0", skills=("writing-plans",))
        code, out, _err = self.rundesk("skills", "update", "acme", "--confirm")
        self.assertEqual(0, code)
        self.assertEqual(1, out.count("1.0.0 -> 1.1.0"))
        self.assertIn("jira is no longer in this catalog", out)

    def test_a_copy_of_a_skill_in_it_is_made_again(self):
        # `skills update` has to keep alias copies current too, not only `rundesk update`. A copy is
        # the one grant that can silently drift, so every path that moves a catalog has to remake it.
        directory.made("alan", "claude")
        self.install("other")
        self.rundesk("skills", "grant", "alan", "other/writing-plans")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans", "--as", "acme-plans")
        # Moved where it is *published*, not in the library. Editing the library would be drift, and
        # the update would correctly revert it — which is its own guarantee and a different one.
        published = (self.a_source(version="1.1.0", skills=("writing-plans",))
                     / library.INSIDE / "writing-plans" / library.DECLARED)
        published.write_text("---\nname: writing-plans\ndescription: Moved on. Use when.\n---\n",
                             encoding="utf-8")
        code, _out, err = self.rundesk("skills", "update", "acme", "--confirm")
        self.assertEqual(0, code, err)
        held = grants.holding("alan", "acme-plans")
        self.assertFalse(grants.stale(held))
        self.assertIn("Moved on", (held.at / library.DECLARED).read_text(encoding="utf-8"))

    def test_with_confirm_and_a_newer_catalog_it_moves_and_revokes(self):
        directory.made("alan", "claude")
        self.rundesk("skills", "grant", "alan", "acme/jira")
        self.a_source(version="1.1.0", skills=("writing-plans",))
        code, out, _err = self.rundesk("skills", "update", "acme", "--confirm")
        self.assertEqual(0, code)
        self.assertIn("1.0.0 -> 1.1.0", out)
        self.assertIn("alan no longer holds jira", out)

    def test_a_catalog_that_is_not_there_is_refused(self):
        code, _out, err = self.rundesk("skills", "update", "nope", "--confirm")
        self.assertEqual(1, code)
        self.assertIn("no catalog", err)

    def test_the_catalog_your_own_skills_stand_in_has_nothing_to_check(self):
        catalogs.place_mine()
        code, _out, err = self.rundesk("skills", "update", library.MINE)
        self.assertEqual(1, code)
        self.assertIn("nothing to check", err)


class RemovingACatalog(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()

    def test_without_confirm_it_names_everything_that_would_go(self):
        code, out, err = self.rundesk("skills", "remove", "acme")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("writing-plans", err)
        self.assertIn("jira", err)
        self.assertIn("--confirm", err)
        self.assertEqual(["acme"], library.known())

    def test_the_preview_names_who_would_lose_a_grant(self):
        directory.made("alan", "claude")
        self.rundesk("skills", "grant", "alan", "acme/jira")
        _code, _out, err = self.rundesk("skills", "remove", "acme")
        self.assertIn("held by alan", err)

    def test_with_confirm_it_goes_and_revokes_every_grant_of_it(self):
        directory.made("alan", "claude")
        self.rundesk("skills", "grant", "alan", "acme/jira")
        code, out, _err = self.rundesk("skills", "remove", "acme", "--confirm")
        self.assertEqual(0, code)
        self.assertIn("acme removed", out)
        self.assertIn("alan no longer holds jira", out)
        self.assertEqual([], library.known())

    def test_the_catalog_rundesk_ships_is_refused_before_confirm_is_even_looked_at(self):
        # Asking somebody to confirm something that will then be refused is a worse answer than
        # refusing now.
        if not catalogs.SHIPPED.is_dir():
            self.skipTest("this release ships no catalog")
        catalogs.place_bundled()
        for argv in (("skills", "remove", library.BUNDLED),
                     ("skills", "remove", library.BUNDLED, "--confirm")):
            with self.subTest(argv=argv):
                code, out, err = self.rundesk(*argv)
                self.assertEqual(1, code)
                self.assertEqual("", out)
                self.assertIn("depends on", err)
        self.assertIn(library.BUNDLED, library.known())

    def test_the_catalog_your_own_skills_stand_in_is_refused(self):
        catalogs.place_mine()
        code, _out, err = self.rundesk("skills", "remove", library.MINE, "--confirm")
        self.assertEqual(1, code)
        self.assertIn("did not write", err)


class GrantingAndRevoking(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()
        directory.made("alan", "claude")

    def test_a_grant_says_where_it_came_from_and_where_it_stands(self):
        code, out, _err = self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.assertEqual(0, code)
        self.assertIn("alan holds writing-plans", out)
        self.assertIn("acme/writing-plans", out)

    def test_a_grant_of_something_needing_credentials_says_so_without_refusing(self):
        # A skill whose credential arrives tomorrow is ordinary.
        code, out, _err = self.rundesk("skills", "grant", "alan", "acme/jira")
        self.assertEqual(0, code)
        self.assertIn("JIRA_API_TOKEN", out)
        self.assertIn("rundesk skills configure acme/jira", out)

    def test_a_bare_skill_name_is_refused_and_says_the_whole_address(self):
        code, _out, err = self.rundesk("skills", "grant", "alan", "writing-plans")
        self.assertEqual(1, code)
        self.assertIn("acme/writing-plans", err)

    def test_an_unknown_agent_and_an_unknown_skill_are_told_apart(self):
        _code, _out, no_agent = self.rundesk("skills", "grant", "nobody", "acme/writing-plans")
        self.assertIn("no agent", no_agent)
        _code, _out, no_skill = self.rundesk("skills", "grant", "alan", "acme/nope")
        self.assertIn("no skill", no_skill)

    def test_a_second_skill_of_one_name_is_refused_and_the_line_it_prints_works(self):
        # The refusal has to be copy-pasteable, so the line it offers is run verbatim here. A
        # suggestion nobody can follow is worse than none.
        self.install("other")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        code, _out, err = self.rundesk("skills", "grant", "alan", "other/writing-plans")
        self.assertEqual(1, code)
        self.assertIn("directory name", err)
        offered = [one for one in err.splitlines() if "--as <name>" in one]
        self.assertEqual(1, len(offered), err)
        argv = offered[0].split("rundesk ")[1].replace("<name>", "other-plans").split()
        code, out, err = self.rundesk(*argv)
        self.assertEqual(0, code, err)
        self.assertIn("alan holds other-plans", out)

    def test_an_alias_that_collides_too_is_told_to_pick_another(self):
        # The same useful advice either way. An earlier draft suppressed the line on a second
        # attempt, which only withheld the answer from somebody who had worked out half of it.
        self.install("other")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.rundesk("skills", "grant", "alan", "other/writing-plans", "--as", "other-plans")
        code, _out, err = self.rundesk("skills", "grant", "alan", "other/jira",
                                       "--as", "other-plans")
        self.assertEqual(1, code)
        self.assertIn("--as <name>", err)

    def test_a_refusal_about_something_else_offers_no_alias(self):
        # A suggestion that does not follow from the failure is one somebody follows and is refused
        # again. **Every one of these leaves a trailing name the agent really does hold**, which is
        # exactly how an earlier version came to offer an alias for all three: it worked the answer
        # out from the address instead of from what actually went wrong. Found by running the
        # commands rather than by a case, so each shape is here now.
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        for argv in (("skills", "grant", "alan", "writing-plans"),
                     ("skills", "grant", "alan", "nope/writing-plans"),
                     ("skills", "grant", "nobody", "acme/writing-plans")):
            with self.subTest(argv=argv):
                code, _out, err = self.rundesk(*argv)
                self.assertEqual(1, code)
                self.assertNotIn("--as", err)

    def test_a_collision_offers_both_ways_out(self):
        self.install("other")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        _code, _out, err = self.rundesk("skills", "grant", "alan", "other/writing-plans")
        self.assertIn("rundesk skills revoke alan writing-plans", err)
        self.assertIn("--as <name>", err)

    def test_a_catalog_calling_itself_a_name_rundesk_keeps_is_refused(self):
        for name in (library.MINE, library.BUNDLED):
            with self.subTest(catalog=name):
                source = self.a_source(name=name, skills=("writing-plans",))
                code, out, err = self.rundesk("skills", "install", str(source), "--confirm")
                self.assertEqual(1, code)
                self.assertEqual("", out)
                self.assertIn(name, err)
                self.assertNotIn(name, library.known())

    def test_revoking_says_the_skill_itself_is_still_there(self):
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        code, out, _err = self.rundesk("skills", "revoke", "alan", "writing-plans")
        self.assertEqual(0, code)
        self.assertIn("no longer holds writing-plans", out)
        self.assertIn("still in the library", out)

    def test_revoking_twice_is_refused_the_second_time(self):
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.rundesk("skills", "revoke", "alan", "writing-plans")
        code, _out, err = self.rundesk("skills", "revoke", "alan", "writing-plans")
        self.assertEqual(1, code)
        self.assertIn("does not hold", err)


class ListingWhatAnAgentHolds(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()
        directory.made("alan", "claude")

    def test_an_agent_holding_nothing_says_what_to_type(self):
        code, out, _err = self.rundesk("skills", "list", "alan")
        self.assertEqual(0, code)
        self.assertIn("rundesk skills grant alan", out)

    def test_a_listing_shows_where_each_came_from_and_how_it_stands(self):
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.rundesk("skills", "grant", "alan", "acme/jira")
        code, out, _err = self.rundesk("skills", "list", "alan")
        self.assertEqual(0, code)
        self.assertIn("writing-plans", out)
        self.assertIn("needs nothing", out)
        self.assertIn("BLOCKED", out)

    def test_the_whole_library_says_which_agents_hold_what(self):
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        code, out, _err = self.rundesk("skills")
        self.assertEqual(0, code)
        self.assertIn("alan", out)

    def test_an_agent_holding_it_under_an_alias_is_still_listed_against_it(self):
        # `_agents_holding` matches on where a grant points, not on the name it stands under — which
        # is what makes an aliased holder appear in the AGENTS column and in a removal's preview.
        # Every other listing case grants under the skill's own name, so none of them proved it.
        directory.made("ben", "grok")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.rundesk("skills", "grant", "ben", "acme/writing-plans", "--as", "wp")
        _code, out, _err = self.rundesk("skills")
        row = next(one for one in out.splitlines() if "writing-plans" in one and "acme" in one)
        self.assertIn("alan", row)
        self.assertIn("ben", row)
        _code, _out, err = self.rundesk("skills", "remove", "acme")
        self.assertIn("held by alan, ben", err)

    def test_an_agent_that_is_not_there_is_refused(self):
        code, _out, err = self.rundesk("skills", "list", "nobody")
        self.assertEqual(1, code)
        self.assertIn("no agent", err)


class ConfiguringAnAccount(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()

    def test_it_asks_for_every_value_and_never_takes_one_as_an_argument(self):
        with self.typing("https://acme.atlassian.net", "ops@acme.example", "a token"):
            code, out, _err = self.rundesk("skills", "configure", "acme/jira")
        self.assertEqual(0, code)
        self.assertIn("needs 3 values", out)
        self.assertIn("complete", out)
        # And what was typed is never echoed back, not even the part that is not a secret.
        self.assertNotIn("a token", out)

    def test_the_reason_a_value_is_needed_is_shown_beside_its_name(self):
        with self.typing(None, None, None):
            _code, out, _err = self.rundesk("skills", "configure", "acme/jira")
        self.assertIn("id.atlassian.com", out)

    def test_an_account_left_incomplete_exits_non_zero_and_says_what_is_missing(self):
        with self.typing("https://acme.atlassian.net", None, None):
            code, _out, err = self.rundesk("skills", "configure", "acme/jira")
        self.assertEqual(1, code)
        self.assertIn("JIRA_EMAIL", err)
        self.assertIn("JIRA_API_TOKEN", err)

    def test_a_named_account_writes_the_suffixed_names(self):
        with self.typing("https://acme.atlassian.net", "ops@acme.example", "a token"):
            code, _out, _err = self.rundesk("skills", "configure", "acme/jira",
                                            "--profile", "acme")
        self.assertEqual(0, code)
        self.assertTrue(secrets.placed("JIRA_API_TOKEN__ACME"))
        self.assertFalse(secrets.placed("JIRA_API_TOKEN"))

    def test_typing_nothing_over_a_value_that_is_set_keeps_it(self):
        # Finishing a half-configured account must not mean re-typing the parts that were right.
        self.a_site("acme", JIRA_BASE_URL="https://acme.atlassian.net")
        with self.typing(None, "ops@acme.example", "a token"):
            code, out, _err = self.rundesk("skills", "configure", "acme/jira",
                                            "--profile", "acme")
        self.assertEqual(0, code)
        self.assertIn("type nothing to keep it", out)
        self.assertIn("kept 2 values", out)

    def test_a_profile_no_program_could_be_given_is_refused(self):
        code, _out, err = self.rundesk("skills", "configure", "acme/jira", "--profile", "one two")
        self.assertEqual(1, code)
        self.assertIn("profile", err)

    def test_a_skill_needing_nothing_has_nothing_to_configure(self):
        code, _out, err = self.rundesk("skills", "configure", "acme/writing-plans")
        self.assertEqual(1, code)
        self.assertIn("needs no credentials", err)


class TheAccountsOneSkillHas(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()

    def test_three_sites_with_one_half_done_are_each_reported(self):
        self.a_site("acme")
        self.a_site("beta")
        secrets.stated("JIRA_BASE_URL__GAMMA", "https://gamma.atlassian.net")
        code, out, _err = self.rundesk("skills", "profiles", "acme/jira")
        self.assertEqual(0, code)
        for said in ("acme", "beta", "gamma", "complete", "INCOMPLETE",
                     "JIRA_API_TOKEN__GAMMA"):
            with self.subTest(said=said):
                self.assertIn(said, out)
        self.assertIn("--profile gamma", out)

    def test_a_skill_nobody_has_configured_says_how_to_start(self):
        code, out, _err = self.rundesk("skills", "profiles", "acme/jira")
        self.assertEqual(0, code)
        self.assertIn("rundesk skills configure acme/jira", out)

    def test_a_skill_needing_nothing_has_no_profiles(self):
        code, out, _err = self.rundesk("skills", "profiles", "acme/writing-plans")
        self.assertEqual(0, code)
        self.assertIn("no profiles", out)


class ForgettingAnAccount(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()
        self.a_site("gamma")

    def test_without_confirm_it_names_what_would_be_emptied(self):
        code, out, err = self.rundesk("skills", "forget", "acme/jira", "--profile", "gamma")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("JIRA_API_TOKEN__GAMMA", err)
        self.assertIn("--confirm", err)
        self.assertTrue(secrets.placed("JIRA_API_TOKEN__GAMMA"))

    def test_with_confirm_every_value_of_that_account_goes(self):
        code, out, _err = self.rundesk("skills", "forget", "acme/jira", "--profile", "gamma",
                                       "--confirm")
        self.assertEqual(0, code)
        self.assertIn("emptied", out)
        self.assertFalse(secrets.placed("JIRA_API_TOKEN__GAMMA"))

    def test_an_account_with_nothing_set_is_refused(self):
        code, _out, err = self.rundesk("skills", "forget", "acme/jira", "--profile", "delta",
                                       "--confirm")
        self.assertEqual(1, code)
        self.assertIn("nothing is set", err)


class TheDoctor(Skills):
    def setUp(self) -> None:
        super().setUp()
        self.install()
        directory.made("alan", "claude")
        self.rundesk("skills", "grant", "alan", "acme/jira")

    def test_the_findings_come_before_the_summary_of_them(self):
        # Both streams merged into one pipe, which is what `rundesk skills doctor | less` does. The
        # findings are on stdout so a script can read them and the summary is on stderr so a script
        # can ignore it — but stdout is block-buffered into a pipe and stderr is not, so without a
        # flush the summary appeared above the findings it summarises.
        import subprocess
        done = subprocess.run(
            [str(support.CHECKOUT / "rundesk"), "skills", "doctor"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env={**os.environ, "RUNDESK_HOME": str(self.home)})
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertLess(done.stdout.index("BLOCKED"), done.stdout.index("cannot be used"),
                        f"the summary came before what it summarises:\n{done.stdout}")

    def test_it_exits_non_zero_when_something_cannot_be_used_and_says_what_to_type(self):
        code, out, err = self.rundesk("skills", "doctor")
        self.assertEqual(1, code)
        self.assertIn("BLOCKED", out)
        self.assertIn("id.atlassian.com", out)
        self.assertIn("rundesk skills configure acme/jira", err)

    def test_it_exits_zero_once_everything_is_ready(self):
        self.a_site()
        code, out, err = self.rundesk("skills", "doctor")
        self.assertEqual(0, code, err)
        self.assertIn("ready", out)

    def test_a_half_configured_account_is_still_something_to_fix(self):
        # Two working sites and one half-done exits non-zero: a check that passed on that is a check
        # nobody can gate on.
        self.a_site("acme")
        self.a_site("beta")
        secrets.stated("JIRA_BASE_URL__GAMMA", "https://gamma.atlassian.net")
        code, out, err = self.rundesk("skills", "doctor")
        self.assertEqual(1, code)
        self.assertIn("PARTIAL", out)
        self.assertIn("--profile gamma", err)

    def test_one_agent_may_be_named(self):
        directory.made("ben", "grok")
        code, out, _err = self.rundesk("skills", "doctor", "alan")
        self.assertEqual(1, code)
        self.assertIn("alan", out)
        self.assertNotIn("ben", out)

    def test_an_agent_that_is_not_there_is_refused(self):
        code, _out, err = self.rundesk("skills", "doctor", "nobody")
        self.assertEqual(1, code)
        self.assertIn("no agent", err)

    def test_a_grant_pointing_at_nothing_says_to_revoke_it(self):
        catalogs.remove("acme")
        code, out, err = self.rundesk("skills", "doctor")
        self.assertEqual(1, code)
        self.assertIn("DANGLING", out)
        self.assertIn("rundesk skills revoke alan jira", err)

    def test_a_verdict_whose_whole_story_is_its_own_line_says_it_once(self):
        # The summary row already carries the sentence. An earlier version had `readable` return it
        # as a detail line too, so it appeared twice — once as the row and once indented beneath
        # itself. Counted, because `assertIn` cannot see a duplicate.
        catalogs.remove("acme")
        _code, out, _err = self.rundesk("skills", "doctor")
        self.assertEqual(1, out.count("the grant points at nothing"), out)

    def test_a_verdict_with_a_breakdown_still_gets_its_detail_lines(self):
        # The other half of that fix: `PARTIAL` and `BLOCKED` detail is genuinely additional, and
        # suppressing it along with the rest would have been the same bug in reverse.
        _code, out, _err = self.rundesk("skills", "doctor")
        self.assertIn("BLOCKED", out)
        self.assertIn("id.atlassian.com", out)


class WhatARemovalOfAnAgentSays(Skills):
    def test_it_names_the_grants_and_says_the_skills_themselves_stay(self):
        # Otherwise a line about "where the agent started" is the only warning that the skills
        # somebody granted are inside it, and it reads as though a removal could cost a catalog.
        self.install()
        directory.made("alan", "claude")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        code, _out, err = self.rundesk("agents", "remove", "alan")
        self.assertEqual(1, code)
        self.assertIn("1 skill grant(s) — writing-plans", err)
        self.assertIn("stay in the library", err)

    def test_an_agent_holding_nothing_says_nothing_about_grants(self):
        directory.made("alan", "claude")
        _code, _out, err = self.rundesk("agents", "remove", "alan")
        self.assertNotIn("skill grant", err)


class WhatAnInstallAndAnUpdateDoToCatalogs(Skills):
    """The refresh, which runs after each of those has already earned its success.

    Driven through a real `install` against a real copy of the program, because the whole point of
    this seam is where it sits in the order — after the release has landed and the data has been
    carried. A case that called the refresh directly would prove nothing about that.
    """

    def setUp(self) -> None:
        super().setUp()
        self.source = self.home / "source"
        self.bin = self.home / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        support.a_real_tree(self.source)

    def a_dead_repository(self) -> catalogs.Fetching:
        """What a repository somebody deleted last week answers."""
        def refreshing(source: str, _etag: str, _into: Path) -> None:
            raise OSError(f"{source} could not be reached")
        return refreshing

    def installed(self, **collaborators):
        return support.run_with(
            ["install", "--source", str(self.source), "--bin-dir", str(self.bin)], **collaborators)

    def updated(self, **collaborators):
        return support.run_with(["update"], asking=lambda: ("v0.0.1", None), **collaborators)

    def test_an_install_places_the_version_coupled_catalog_with_no_network_at_all(self):
        code, out, _err = self.installed(refreshing=self.a_dead_repository())
        self.assertEqual(0, code, out)
        self.assertIn(library.BUNDLED, library.known())
        self.assertTrue(library.held(library.BUNDLED))

    def test_an_install_makes_the_catalog_your_own_skills_stand_in(self):
        self.installed(refreshing=self.a_dead_repository())
        self.assertIn(library.MINE, library.known())

    def test_a_catalog_that_cannot_be_reached_does_not_fail_the_install(self):
        # What `install` reports is whether *it* worked, and it did: the release landed, the data was
        # carried, the command answers. A repository somebody deleted is a false reason to tell
        # `install.sh` the machine is broken.
        code, _out, err = self.installed(refreshing=self.a_dead_repository())
        self.assertEqual(0, code)
        self.assertIn(f"{library.DEPENDED} could not be checked", err)

    def test_a_catalog_that_cannot_be_reached_does_not_fail_an_update_either(self):
        self.installed(refreshing=self.a_dead_repository())
        self.install()
        code, _out, err = self.updated(refreshing=self.a_dead_repository())
        self.assertEqual(0, code)
        self.assertIn("acme could not be checked", err)
        self.assertIn("rundesk skills update acme", err)

    def test_a_version_move_is_said_once_and_not_twice(self):
        # Two code paths rendered one fact: `catalogs.update` says it through the callback it was
        # handed, and an earlier version said it again from the outcome — so a real update printed
        # `acme 1.0.0 -> 1.1.0` twice with the retirements between the copies. Counted rather than
        # `assertIn`, because `assertIn` is exactly what let it through.
        self.installed(refreshing=self.a_dead_repository())
        self.install()
        moved = self.a_source(version="1.1.0", skills=("writing-plans",))

        def refreshing(source: str, _etag: str, _into: Path):
            if source != str(moved):
                raise OSError(f"{source} could not be reached")
            return catalogs.Brought(moved, "")

        _code, out, _err = self.updated(refreshing=refreshing)
        self.assertEqual(1, out.count("acme 1.0.0 -> 1.1.0"), out)

    def test_an_update_that_found_nothing_newer_still_checks_the_catalogs(self):
        # What makes them current daily rather than only when rundesk itself moves: a catalog is
        # somebody else's repository and it changes on its own schedule.
        self.installed(refreshing=self.a_dead_repository())
        self.install()
        moved = self.a_source(version="1.1.0", skills=("writing-plans",))

        def refreshing(source: str, _etag: str, _into: Path):
            if source != str(moved):
                raise OSError(f"{source} could not be reached")
            return catalogs.Brought(moved, "")

        code, out, _err = self.updated(refreshing=refreshing)
        self.assertEqual(0, code)
        self.assertIn("1.0.0 -> 1.1.0", out)
        self.assertEqual("1.1.0", library.read("acme").manifest.version)

    def test_a_failure_remaking_a_grant_does_not_crash_an_update_that_had_succeeded(self):
        # An ordinary `OSError` while remaking one stale copy ran outside the guard, so it came out
        # of `rundesk update` as a traceback with no exit code at all — turning a release that had
        # landed and settled into a hard crash. Sharper than any catalog being unreachable.
        self.installed(refreshing=self.a_dead_repository())
        self.install()
        directory.made("alan", "claude")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")

        with mock.patch("rundesk.skills.grants.refreshed",
                        side_effect=OSError("the disk is full")):
            code, _out, err = self.updated(refreshing=self.a_dead_repository())
        self.assertEqual(0, code)
        self.assertIn("the grants could not all be brought up to date", err)
        self.assertIn("rundesk skills doctor", err)

    def test_the_catalog_your_own_skills_stand_in_failing_does_not_hide_the_others(self):
        # It was the one step in the refresh with no guard of its own, so a failure here escaped and
        # the caller reported one coarse sentence for the whole install — throwing away the
        # per-catalog granularity every other step preserves.
        self.installed(refreshing=self.a_dead_repository())
        self.install()
        with mock.patch("rundesk.skills.catalogs.place_mine",
                        side_effect=OSError("the disk is full")):
            code, _out, err = self.updated(refreshing=self.a_dead_repository())
        self.assertEqual(0, code)
        self.assertIn(f"{library.MINE} could not be checked", err)
        self.assertIn("acme could not be checked", err)

    def test_a_copy_left_behind_its_catalog_is_made_again_by_an_update(self):
        self.installed(refreshing=self.a_dead_repository())
        self.install()
        self.install("other")
        directory.made("alan", "claude")
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.rundesk("skills", "grant", "alan", "other/writing-plans", "--as", "other-plans")
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Moved on. Use when.\n---\n",
                          encoding="utf-8")

        self.updated(refreshing=self.a_dead_repository())
        held = grants.holding("alan", "other-plans")
        self.assertFalse(grants.stale(held))
        self.assertIn("Moved on", (held.at / library.DECLARED).read_text(encoding="utf-8"))

    def test_the_version_coupled_catalog_is_replaced_by_an_update(self):
        # An install that moved forward and kept the previous release's copy would be handing every
        # agent instructions for a rundesk it is no longer running.
        self.installed(refreshing=self.a_dead_repository())
        drifted = (library.tree(library.BUNDLED) / library.INSIDE / "managing-rundesk"
                   / library.DECLARED)
        was = drifted.read_text(encoding="utf-8")
        drifted.write_text("---\nname: managing-rundesk\ndescription: edited\n---\n",
                           encoding="utf-8")
        self.updated(refreshing=self.a_dead_repository())
        self.assertEqual(was, drifted.read_text(encoding="utf-8"))


class WhenSomethingElseHoldsTheInstallLock(Skills):
    """Lock contention is a refusal, not a traceback.

    `locking.Stuck` is a bare `Exception` rather than an `OSError`, so it has to be named in the
    caught set explicitly — it was not, and a concurrent `backups save` or a second `skills` command
    still holding the install lock reached a person as an unhandled traceback. `commands/agents.py`
    has always named it; this group had not.
    """

    def setUp(self) -> None:
        super().setUp()
        self.install()
        directory.made("alan", "claude")

    def held_by_something_else(self):
        return mock.patch("rundesk.skills.catalogs.locking.only_one",
                          side_effect=locking.Stuck("something else is changing this install"))

    def test_every_verb_that_writes_refuses_rather_than_raising(self):
        for argv in (("skills", "install", str(self.a_source("more")), "--confirm"),
                     ("skills", "update", "acme", "--confirm"),
                     ("skills", "remove", "acme", "--confirm")):
            with self.subTest(argv=argv):
                with self.held_by_something_else():
                    code, out, err = self.rundesk(*argv)
                self.assertEqual(1, code)
                self.assertEqual("", out)
                self.assertIn("skills: FAILED", err)

    def test_every_verb_that_changes_a_grant_answers_a_linking_failure(self):
        # `NotPresented` is deliberately outside `TROUBLE`, so a verb that does not name it does not
        # catch it *at all*. `revoke` did not, and an ordinary revoke under lock contention came out
        # of `cli.main` as a traceback. Both verbs reach the raiser, so both are checked here — and
        # the wording has to fit each: after a grant the skill is held, after a revoke it is gone.
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        for argv, landed in ((("skills", "grant", "alan", "acme/jira"), "does hold it"),
                             (("skills", "revoke", "alan", "writing-plans"), "no longer holds it")):
            with self.subTest(argv=argv):
                with mock.patch("rundesk.skills.grants.presented",
                                side_effect=locking.Stuck("something else has the lock")):
                    code, out, err = self.rundesk(*argv)
                self.assertEqual(1, code)
                self.assertEqual("", out)
                self.assertIn("skills: FAILED", err)
                self.assertIn(landed, err)
                self.assertIn("rundesk skills doctor", err)

    def test_a_grant_that_landed_but_could_not_be_linked_says_which_it_was(self):
        # The write and the linking are two lock acquisitions, so the second can be refused for
        # contention alone while the grant itself is on disk and correct. Told this had failed, an
        # operator retries and meets "already holds it" — having been given no reason to think the
        # first one worked. `AGENTS.md` forbids claiming a success nobody earned; claiming a failure
        # nobody earned sends them to undo work that is fine.
        with mock.patch("rundesk.skills.grants.presented",
                        side_effect=locking.Stuck("something else is changing this install")):
            code, out, err = self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("does hold it", err)
        self.assertIn("rundesk skills doctor", err)
        # And it really is there, which is the whole reason the wording has to differ.
        self.assertIsNotNone(grants.holding("alan", "writing-plans"))

    def test_a_grant_refuses_rather_than_raising_too(self):
        with mock.patch("rundesk.skills.grants.locking.only_one",
                        side_effect=locking.Stuck("something else is changing this install")):
            code, _out, err = self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        self.assertEqual(1, code)
        self.assertIn("skills: FAILED", err)


class WhenASkillsDeclarationCannotBeRead(Skills):
    """A catalog author ships a broken `rundesk.json`, which is an ordinary field scenario.

    Four verbs read it, each wording its own refusal, and none of them was ever driven with one that
    will not parse — so nothing proved they refuse gracefully rather than crashing.
    """

    def setUp(self) -> None:
        super().setUp()
        self.install()
        directory.made("alan", "claude")
        (library.tree("acme") / library.INSIDE / "jira" / needs.WANTS).write_text(
            "{not json", encoding="utf-8")

    def test_every_verb_that_reads_it_refuses_rather_than_raising(self):
        for argv in (("skills", "profiles", "acme/jira"),
                     ("skills", "configure", "acme/jira"),
                     ("skills", "forget", "acme/jira", "--confirm")):
            with self.subTest(argv=argv):
                code, out, err = self.rundesk(*argv)
                self.assertEqual(1, code)
                self.assertEqual("", out)
                self.assertIn("skills: FAILED", err)

    def test_a_grant_still_lands_and_says_the_declaration_cannot_be_read(self):
        # The one verb that must *not* refuse: the link is on disk by the time the declaration is
        # read, so failing here would report nothing about work that had already succeeded — and
        # crashing, which is what it did, reports less than nothing.
        code, out, _err = self.rundesk("skills", "grant", "alan", "acme/jira")
        self.assertEqual(0, code)
        self.assertIn("alan holds jira", out)
        self.assertIn("cannot be read", out)
        self.assertIsNotNone(grants.holding("alan", "jira"))

    def test_a_listing_still_answers_about_everything_else(self):
        # A listing that refused to say anything about a healthy catalog on account of one broken
        # declaration would be worse than one that shows what it can.
        code, out, _err = self.rundesk("skills")
        self.assertEqual(0, code)
        self.assertIn("writing-plans", out)

    def test_doctor_reports_it_broken_rather_than_ready(self):
        self.rundesk("skills", "grant", "alan", "acme/writing-plans")
        code, out, _err = self.rundesk("skills", "doctor")
        self.assertEqual(0, code, "the granted skill is fine; the broken one is not granted")
        self.assertIn("writing-plans", out)


class WhatIsOfferedAtAll(Skills):
    def test_the_help_names_the_group(self):
        _code, out, _err = self.rundesk("--help")
        self.assertIn("skills", out)

    def test_every_sub_verb_is_wired_to_something(self):
        # The `AssertionError` at the bottom of `cmd_skills` is what catches one registered on the
        # parser and answered by nothing, and this is what makes sure it never has to.
        from rundesk import cli
        registered: List[str] = []
        for action in cli.build_parser()._actions:
            if isinstance(action, cli.Subcommands) and "skills" in action.choices:
                for one in action.choices["skills"]._actions:
                    if isinstance(one, cli.Subcommands):
                        registered.extend(one.choices)
        self.assertTrue(registered)
        for verb in sorted(set(registered)):
            with self.subTest(verb=verb):
                # Driven with nothing else, so most of these refuse — what is being checked is that
                # none of them reaches the `AssertionError`, which would come out as a traceback.
                code, _out, _err = self.rundesk("skills", verb, "x", "y")
                self.assertIn(code, (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
