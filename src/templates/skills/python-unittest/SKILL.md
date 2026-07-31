---
name: python-unittest
description: Python standard-library unittest patterns for TestCase, discovery, cleanup, subtests, mocking, and async tests. Use when a project uses unittest or when writing, reviewing, debugging, or organizing unittest-based tests.
---

# Python unittest

Follow the repository's existing test layout, naming, and command. Use `unittest` without
adding a test dependency when the project has chosen the standard-library runner.

## Start with observable behavior

Write a failing case that proves the requested behavior or reproduces the defect, run that
case, make the smallest implementation change, then run its containing class and the full
suite. Read the final `Ran N tests` count: a green command that discovered zero tests proves
nothing.

```python
import unittest

from calculator import Calculator


class TestCalculator(unittest.TestCase):
    def setUp(self):
        self.calculator = Calculator()
        self.addCleanup(self.calculator.close)

    def test_dividing_by_zero_is_refused(self):
        with self.assertRaisesRegex(ValueError, "zero"):
            self.calculator.divide(10, 0)


if __name__ == "__main__":
    unittest.main()
```

Keep the `unittest.main()` block last. A `TestCase` defined after it is not discovered when
the file runs directly.

## Choose the assertion that explains the failure

Prefer the specific `TestCase` assertion over a bare `assert`:

```python
self.assertEqual(actual, expected)
self.assertIs(actual, expected)
self.assertIsNone(actual)
self.assertTrue(condition)
self.assertIn(member, collection)
self.assertCountEqual(actual, expected)
self.assertAlmostEqual(actual, expected, places=3)
self.assertRegex(message, r"invalid \w+")

with self.assertRaises(ExpectedError) as raised:
    operation()
self.assertEqual(raised.exception.code, "invalid")

with self.assertLogs("package.module", level="WARNING") as captured:
    operation()
self.assertIn("retrying", captured.output[0])
```

Assert on the public result and meaningful side effects. Avoid reproducing the implementation
inside the test or pinning incidental call order.

## Clean up at acquisition time

`tearDown()` does not run when `setUp()` itself fails. Register cleanup immediately after a
resource is acquired; cleanups run even after a later setup failure and run in last-in,
first-out order.

```python
def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)

    self.server = Server()
    self.server.start()
    self.addCleanup(self.server.stop)
```

Use `setUpClass()` only for expensive read-only state that can safely be shared. Pair class
resources with `addClassCleanup()` as soon as they are acquired. Keep mutable state per test
so execution order cannot matter.

## Use subtests for small data tables

Subtests preserve one test method while identifying the input that failed:

```python
def test_normalizes_supported_names(self):
    cases = [
        ("Ada", "ada"),
        (" Grace ", "grace"),
        ("ALAN", "alan"),
    ]
    for given, expected in cases:
        with self.subTest(given=given):
            self.assertEqual(normalize(given), expected)
```

Use separate test methods when cases need different setup, failure explanations, or behavior.
A failed `self.subTest(...)` does not stop the loop, so do not let one case mutate state needed
by the next.

## Patch the lookup, not the definition

Patch where the code under test looks up the object. If `billing.service` imports
`send_receipt`, patch `billing.service.send_receipt`, not the module that originally defines
the function.

```python
from unittest.mock import create_autospec, patch


class TestCheckout(unittest.TestCase):
    @patch("billing.service.send_receipt", autospec=True)
    def test_sends_one_receipt_after_payment(self, send_receipt):
        receipt = checkout(order_id=42)

        send_receipt.assert_called_once_with(receipt)
```

Use `autospec=True`, `create_autospec()`, or `spec_set=` when the real interface is available;
an unrestricted mock accepts misspelled methods and impossible calls. Prefer a small real
object or in-memory implementation when it is clearer than a network of mocks. Restore manual
patchers with `self.addCleanup(patcher.stop)`.

Use `side_effect` for failures or sequences:

```python
client = create_autospec(ApiClient, instance=True, spec_set=True)
client.fetch.side_effect = [TimeoutError, {"status": "ready"}]
```

For async collaborators, use `AsyncMock` and assert with `assert_awaited_once_with()`.

## Test async code in its own event loop

`unittest.IsolatedAsyncioTestCase` gives each test an isolated loop and supports
`asyncSetUp()`, `asyncTearDown()`, and `addAsyncCleanup()`:

```python
from unittest.mock import AsyncMock


class TestFetcher(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncMock(spec=Client)
        self.fetcher = Fetcher(self.client)

    async def test_returns_the_payload(self):
        self.client.get.return_value = {"ready": True}

        result = await self.fetcher.fetch()

        self.assertEqual(result, {"ready": True})
        self.client.get.assert_awaited_once_with("/status")
```

Do not share an event loop, pending task, or async client between cases.

## Isolate process and filesystem state

Use `tempfile.TemporaryDirectory()` or `TemporaryFile()` rather than paths in the checkout.
Patch environment and global state only for the smallest scope:

```python
from unittest.mock import patch

with patch.dict("os.environ", {"MODE": "test"}, clear=True):
    self.assertEqual(read_mode(), "test")
```

Do not call production services from unit tests. At an integration boundary, provision an
explicit test service and make its address part of the test setup.

## Run and select tests deliberately

```bash
python3 -m unittest
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m unittest tests.test_service
python3 -m unittest tests.test_service.TestService.test_retries
python3 -m unittest -v
python3 -m unittest -f
python3 -m unittest -k retry
```

`-k` matches a substring or glob pattern; it does not parse boolean expressions. Repeat `-k`
for multiple patterns, and confirm that the selected command ran at least one test.

## Avoid unittest-specific traps

- Do not name a `TestCase` helper `_outcome`, `_result`, `_subtest`, or `_cleanups`; those
  names belong to runner internals and collisions produce misleading failures.
- Do not catch a broad exception only to call `self.fail()`. Let unexpected exceptions retain
  their traceback; use `assertRaises` only for the expected type.
- Do not make one test depend on another or on alphabetical execution order.
- Do not put substantial logic, loops outside `subTest`, or conditional assertions into a
  test; a test should make its reason for failing obvious.
- Do not invent a coverage percentage. Honor the repository's configured coverage gate and
  prioritize critical paths, error handling, and boundaries.
