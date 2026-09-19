# Proving a test has teeth

A test that cannot fail is worse than no test, because it reports coverage that does not exist and
it silences the next person who wonders whether the behavior is checked.

`SKILL.md` states the rule: observe the failure for the reported reason before the correction. This
page is how to do that without destroying work, and what a false pass looks like.

## The procedure

For a regression, the order is fixed: **break, observe, restore, fix, observe.**

1. Establish the baseline. Run the test and record the exact command, the discovered and executed
   counts, and the result. A test that does not run cannot fail.
2. Break the behavior the test claims to cover, in the smallest way that is genuinely wrong.
3. Run the same command. Confirm it fails, and read the failure message: it must name the behavior
   under test, not a crash, an import error, or a missing fixture.
4. Restore the code exactly.
5. Run again and confirm it passes.

Restore with a copy, never with version control:

```sh
# Good: the working tree is untouched, including anything uncommitted.
cp src/pricing.py /tmp/pricing.py.bak
<edit src/pricing.py to break the behavior>
<run the test; observe the failure>
cp /tmp/pricing.py.bak src/pricing.py

# Bad: discards every uncommitted change in that file, including work you did not make.
git checkout -- src/pricing.py
```

That distinction matters more than it looks. `git checkout` is the reflex, and it silently destroys
uncommitted work — including work done by someone or something else in the same tree.

Restore in a `finally`, or its equivalent, when the probe is scripted. A probe that aborts partway
leaves the codebase broken and the next run's results meaningless.

## What a false pass looks like

The test still passes with the behavior broken. Common causes, in the order they occur:

| Signal | Cause |
|---|---|
| Passes with the function body emptied | The assertion does not reach the behavior — often asserting on the input, a constant, or a mock's own return |
| Passes with the assertion deleted | There was never a meaningful assertion; the test asserts that nothing threw |
| Passes with the module deleted | The test exercises a double all the way down and never touches production code |
| Passes but the count is zero | The case was never discovered — a naming, marker, or path problem |
| Passes because the case was skipped | A dependency was absent and the runner skipped rather than failed |
| Fails, but for the wrong reason | The break caused an import or setup error before the assertion; the test still proves nothing |

That last row is the one people accept too readily. A red result is not evidence on its own — the
failure has to be *about* the behavior.

```python
# Bad: passes with the discount logic replaced by `return 0`, because the mock supplies the answer.
def test_total(self):
    calculator = Mock()
    calculator.discount.return_value = 5
    self.assertEqual(5, calculator.discount(order))

# Good: fails the moment the real rule changes.
def test_discount_applies_to_orders_over_the_threshold(self):
    self.assertEqual(5, discount_for(Order(total=105)))
```

## When you cannot break the code

Sometimes the break is unsafe or impractical — shared infrastructure, generated code, a change that
will not compile in isolation. Say so explicitly rather than claiming the defect was reproduced.

The honest report is: what you intended to break, why you could not, and what the test's coverage
therefore rests on. That is a smaller claim, and it is checkable.

## Scaling the idea beyond one test

Mutation testing automates exactly this probe across a suite: it introduces small changes to
production code and reports which ones no test detected. A mutant that survives is a gap in the
suite's ability to detect a defect — a stronger signal than any coverage percentage, because
coverage records that a line ran, not that anything checked the result.

It is expensive, so it is usually run on the changed surface rather than the whole codebase, and
some surviving mutants are equivalent — the change did not alter behavior at all, so no test could
detect it. Treat surviving mutants as a list to triage, not a score to maximize.

Use it where the cost is justified — a payment calculation, an authorization rule, a migration — and
use the manual probe above everywhere else.
