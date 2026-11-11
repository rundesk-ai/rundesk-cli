# Python unittest patterns

Use this reference for `unittest` mechanics. Follow the repository's test layout, naming, and
commands. Deciding what behavior and risk need tests is a separate, language-neutral concern.

## Start with observable behavior

Write a failing case that proves the requested behavior or reproduces the defect. Run that case,
make the smallest implementation change, then run its containing class and the repository's full
suite. Read the final `Ran N tests` count; a green command that discovers zero tests proves nothing.

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

Keep `unittest.main()` last. A `TestCase` declared after it is not discovered when the file runs
directly.

## Choose useful assertions

Prefer the specific `TestCase` assertion whose failure explains the mismatch:

```python
self.assertEqual(actual, expected)
self.assertIs(actual, expected)
self.assertIsNone(actual)
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

Assert on public results and meaningful side effects. Do not reproduce the implementation inside
the test or pin incidental call order.

## Own cleanup and isolation

`tearDown()` does not run when `setUp()` fails. Register cleanup immediately after acquiring each
resource; cleanups run after later setup failures and in last-in, first-out order:

```python
def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)

    self.server = Server()
    self.server.start()
    self.addCleanup(self.server.stop)
```

Use `setUpClass()` only for expensive, read-only state that is safe to share. Register class
resources with `addClassCleanup()` as they are acquired. Keep mutable state per test so execution
order cannot matter.

Use `TemporaryDirectory()` or `TemporaryFile()` instead of checkout paths. Limit environment and
global-state patches to the smallest scope:

```python
from unittest.mock import patch

with patch.dict("os.environ", {"MODE": "test"}, clear=True):
    self.assertEqual(read_mode(), "test")
```

Unit tests must not call production services. An integration test should provision an explicit
test service and make its address and cleanup part of setup.

On POSIX, never test process-group cleanup by signaling a synthetic group. `killpg(0, ...)` targets
the test runner's own group, and POSIX leaves group values at or below one undefined. Mock the lookup
boundary in unit tests. For an integration test, start the child in a new session, prove
`os.getpgid(child.pid) == child.pid > 1`, then signal that verified group.

```python
# Good: prove the lookup validates the group before signaling.
with patch("package.runner.os.getpgid", return_value=child_pid) as getpgid, \
     patch("package.runner.os.killpg", autospec=True) as killpg:
    terminate_group(child_pid)
getpgid.assert_called_once_with(child_pid)
killpg.assert_called_once_with(child_pid, signal.SIGTERM)

# Also force getpgid() to return 0, 1, and an unrelated group; each case must be refused and
# killpg must remain uncalled.
```

Never use `os.killpg(0, ...)` as the bad-path test; it can terminate the shell or CI worker. Prove the
guard by forcing the lookup result and rejecting zero, one, or any group other than the isolated
child's verified group.

## Use subtests deliberately

Subtests keep a small data table in one method while identifying the failing input:

```python
def test_normalizes_supported_names(self):
    cases = [("Ada", "ada"), (" Grace ", "grace"), ("ALAN", "alan")]

    for given, expected in cases:
        with self.subTest(given=given):
            self.assertEqual(normalize(given), expected)
```

Use separate methods when cases need different setup, behavior, or failure explanations. A failed
subtest does not stop the loop, so one case must not mutate state required by the next.

## Mock the lookup boundary

Patch where the code under test looks up an object. If `billing.service` imported `send_receipt`,
patch `billing.service.send_receipt`, not the module that originally defined it:

```python
from unittest.mock import create_autospec, patch

class TestCheckout(unittest.TestCase):
    @patch("billing.service.send_receipt", autospec=True)
    def test_sends_one_receipt_after_payment(self, send_receipt):
        receipt = checkout(order_id=42)

        send_receipt.assert_called_once_with(receipt)
```

Use `autospec=True`, `create_autospec()`, or `spec_set=` when the real interface is available. An
unrestricted mock accepts misspelled methods and impossible calls. Prefer a small real object or
in-memory implementation when it is clearer than connected mocks. Restore manual patchers through
`addCleanup(patcher.stop)`.

Use `side_effect` for failures or sequences:

```python
client = create_autospec(ApiClient, instance=True, spec_set=True)
client.fetch.side_effect = [TimeoutError, {"status": "ready"}]
```

## Test async code

`IsolatedAsyncioTestCase` gives each test its own event loop and supports `asyncSetUp()`,
`asyncTearDown()`, and `addAsyncCleanup()`:

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

Do not share event loops, pending tasks, or async clients between cases.

A cancellation test must prove the coroutine started before it cancels the task. Cancellation is
delivered at the next scheduling opportunity; if the task never ran, its `finally` block was never
entered, so the test is not exercising cleanup.

```python
started = asyncio.Event()
task = asyncio.create_task(worker(started))  # worker sets started inside its body
await started.wait()
task.cancel()
with self.assertRaises(asyncio.CancelledError):
    await task
self.assertTrue(cleanup_finished())
```

Do not replace the event with timing luck such as `sleep(0)`. Prove the test by removing or breaking
the worker's cleanup and watching the final assertion fail.

## Run and select tests

Use the repository's command first. Standard-library selection supports:

```bash
python3 -m unittest
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m unittest tests.test_service
python3 -m unittest tests.test_service.TestService.test_retries
python3 -m unittest -v
python3 -m unittest -f
python3 -m unittest -k retry
```

`-k` matches substrings or glob patterns, not Boolean expressions. Repeat it for multiple patterns
and confirm every selected command ran at least one test.

## Avoid unittest traps

- Do not wrap the module under test in `except ImportError: raise SkipTest`. A defect or missing
  transitive import then turns the whole suite green-but-skipped. Probe only the optional prerequisite,
  require a matching `ModuleNotFoundError.name`, and import the subject outside the guard:

  ```python
  try:
      import optional_dependency
  except ModuleNotFoundError as exc:
      if exc.name != "optional_dependency":
          raise
      raise unittest.SkipTest("optional dependency is not installed") from exc

  from package import subject
  ```

  Prove the boundary by breaking `package`'s import: the test must error, not skip.
- Do not name a `TestCase` helper `_outcome`, `_result`, `_subtest`, or `_cleanups`; those names are
  runner internals.
- Do not catch a broad exception only to call `self.fail()`. Preserve unexpected tracebacks and use
  `assertRaises` only for the expected type.
- Do not make tests depend on one another or alphabetical order.
- Keep conditional assertions and substantial logic out of a test. Use subtests only for a small,
  explicit case table.
- Do not invent a coverage percentage. Honor the repository's configured gate and prioritize
  critical paths, errors, state changes, and external boundaries.
