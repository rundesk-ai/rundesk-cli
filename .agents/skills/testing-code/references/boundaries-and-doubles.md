# Boundaries and test doubles

`SKILL.md` gives the boundary table; this page is the vocabulary and the decision, because most
bad tests come from replacing the wrong thing rather than from replacing too much or too little.

## Say which double you mean

The words are used loosely and the differences are behavioral. Use them precisely, because "we
mocked it" hides which of these actually happened:

| Double | What it does | Use when |
|---|---|---|
| **Dummy** | Fills a parameter, never used | The signature demands a value the path never touches |
| **Stub** | Returns canned answers to calls | You need the collaborator to supply an input |
| **Spy** | A stub that also records how it was called | You need the input *and* the call is worth asserting |
| **Mock** | Pre-programmed with expectations; fails if they are not met | The interaction itself is the required behavior |
| **Fake** | A real working implementation, simplified | The collaborator is slow or external but its behavior matters |

The load-bearing distinction is **stub versus mock**: a stub supports state verification — you assert
on the result — while a mock performs behavior verification, asserting that a particular call
happened. Reach for a stub by default. Reach for a mock only when the call is the observable
requirement: an event published, a payment charged, an expensive boundary deliberately not hit.

```python
# Bad: a mock asserting an internal call sequence users cannot observe.
repo = Mock()
service = PriceService(repo)
service.quote(order)
repo.load_rates.assert_called_once()      # breaks on any harmless refactor

# Good: state verification. Fails when the behavior changes, survives restructuring.
rates = StubRates({"GBP": Decimal("1.00")})
self.assertEqual(Decimal("42.00"), PriceService(rates).quote(order))

# Also good, when the interaction IS the requirement.
payments.charge.assert_called_once_with(order.id, Decimal("42.00"))
```

## Prefer a fake to a mock for anything with real behavior

A mock encodes your belief about how a collaborator behaves. A fake encodes the behavior itself, once,
in a place that can be tested. When a collaborator has rules — a store that rejects duplicate keys, a
clock that advances, a queue that preserves order — a fake keeps those rules true across every test
that uses it, and a mock re-states them, slightly differently, in each one.

The failure mode of mocks at scale is that they drift: the real thing changes and every mock keeps
agreeing with the old contract, so the suite stays green while the system is broken. That drift is
what contract tests exist to catch, and it is why a fake maintained beside the real implementation is
usually the better investment.

Prefer, in order: **the real thing**, a **maintained fake**, a **stub**, a **mock**.

## Choose the boundary from where the risk lives

Do not replace a dependency because it is a dependency. Replace it when using the real one makes the
test non-deterministic, slow enough to change behavior, or dependent on something outside the test's
control.

| Dependency | Default |
|---|---|
| Pure logic, value objects, the module under test | Real — never double |
| Local database, filesystem, in-process queue | Real. These are fast, deterministic, and the wiring is usually the risk |
| The clock, randomness, identifiers | Inject and control. Never let ambient values in |
| Third-party network service | Fake or stub in tests, plus a contract test that catches drift |
| Another team's service you own an interface to | Contract test on both sides |

Naming a test after its folder is not a claim about what it exercised. An "integration" test that
doubles the serializer proves nothing about the stored format. **Report which dependencies were
real**, because the label varies between teams and tells the reader nothing.

Prefer the narrowest boundary that contains the risk, and add a wider test only when it answers a
question the narrow one cannot. Broad end-to-end tests are the most flake-prone and slowest to
diagnose, so keep them to a small number of critical journeys rather than replaying every edge case
through the whole system.

## Doubles you own versus doubles you impose

Only double a type you control or an interface you defined. Doubling a third-party class directly
couples your suite to its internals, so a minor upgrade breaks tests that were never about it. Wrap
it in an interface of your own, double that, and keep one narrow test against the real thing.
