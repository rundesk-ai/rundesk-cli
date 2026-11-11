# Debugging Laravel

The hypothesis loop does not change; this is where to look and what already recorded the answer.

If Laravel is served by Herd, load `herd.md` first to prove the site mapping and PHP runtime. Return
here after the request is known to enter the intended application.

## Establish which install you are debugging

Before forming a hypothesis, confirm what is actually running. A config cache, stale worker, or
different environment can make the observed code disagree with the checkout.

```sh
php artisan about                 # version, environment, cached config/routes/views, drivers
php artisan config:show database  # the resolved value, not what .env says
php artisan route:list --path=orders
```

`about` reports whether config, routes, events, and views are **cached**. Check it before treating
"my change did nothing" as an application-logic failure.

## See what actually happened

| Question | Where it is already recorded |
|---|---|
| What was the exception, and where | `storage/logs/laravel.log`, or your log channel |
| What queries ran for this request | Telescope, Debugbar, or `DB::listen` |
| What the request looked like end to end | Telescope (local) — requests, queries, jobs, mail, cache, dumps |
| What is slow across the whole app | Pulse (production-safe) |
| Which jobs failed and why | `php artisan queue:failed`, the `failed_jobs` table |
| What a query actually compiles to | `->toSql()`, `->dd()`, `->explain()` |

**Telescope is a development tool** — Laravel's own docs say it "is not recommended for production
environments." **Pulse is designed for production monitoring**; it answers "what is slow" rather
than "what happened in this request."

To log every query on demand, without installing anything:

```php
DB::listen(fn ($q) => logger($q->sql, ['bindings' => $q->bindings, 'ms' => $q->time]));
```

Turn N+1 from a slow page into an exception so the failing access is identified:

```php
Model::preventLazyLoading(! app()->isProduction());   // AppServiceProvider::boot()
```

## Narrow to the layer

A Laravel request passes through a fixed sequence. Bisect it rather than reading code top to bottom.

1. **Did it route?** `route:list --path=…`. A 404 on a route you can see in the file usually means a
   stale route cache or a failed model binding, not a missing route.
2. **Did middleware let it through?** A 419 is CSRF/session; a 403 is authorization; a redirect to
   login is the `auth` middleware. Check `bootstrap/app.php` for the group's contents.
3. **Did validation pass?** A 422 with an empty-looking response is a form request rejecting input.
   Check the form request's `authorize()` too — returning `false` produces a 403 before the
   controller runs.
4. **Did the controller get the data it expected?** `dd($request->validated())` and stop.
5. **Did the query return what you assumed?** `->toSql()` and run it by hand. Global scopes and soft
   deletes silently change results, and they are invisible at the call site.
6. **Did the write commit?** A transaction that rolled back, or a job that ran before the commit.
7. **Did the side effect run?** Mass updates and deletes fire **no model events**, so observers and
   audit logs do not run.

`php artisan tinker` is the cheapest boundary probe — it boots the real application with real
config, so you can call the action or the query directly with no HTTP layer in the way.

## Symptom to first place to look

| Symptom | Look first |
|---|---|
| Works locally, 500 in production | `APP_DEBUG=false` is hiding the message — read `storage/logs`. Then check `config:cache` and `env()` called outside `config/` |
| A code change had no effect | Cached config, routes, or views. `php artisan optimize:clear`, then re-cache |
| A queued job runs old code | The worker was not restarted. `queue:restart` on every deploy |
| Job fails with "model not found" intermittently | Dispatched inside a transaction without `afterCommit()` |
| Job never runs at all | No worker on that queue/connection, or maintenance mode |
| Job fails silently | Nothing implements `failed()`; check `queue:failed` |
| 419 on a form | Session or CSRF — `PreventRequestForgery`, cookie domain, session driver |
| 404 on an existing route | Stale route cache, or route-model binding found nothing |
| Page slow, no obvious query | N+1. Turn on `preventLazyLoading` and re-run |
| Works in tinker, fails over HTTP | Different environment, or an authenticated user with different authorization |
| Config value is `null` in production only | `env()` called outside `config/` after `config:cache` |
| Test passes, production fails | The test uses the `sync` queue and `array` cache, so the transaction and lock bugs cannot appear |

## Traps that send you the wrong way

- **`config:cache` makes `.env` unreadable.** After it runs, `env()` returns only real system
  variables — so `env()` outside `config/` returns `null` **in production and nowhere else**. This
  presents as a feature that works everywhere except the one place that matters.
- **`dd()` inside a queued job** writes to the worker's output, not the browser. Log instead, or run
  one known disposable local job in the foreground with `php artisan queue:work --once`. This still
  consumes and executes a real queued job; it is not a read-only or synchronous probe.
- **The local `sync` queue hides the transaction race.** A job that runs inline always sees committed
  data. Reproduce with a real driver before concluding the code is correct.
- **`APP_DEBUG=true` in production is not a debugging step**, it is an information disclosure. Read
  the log.
- **A restart that clears the symptom** implicates state — worker memory, OPcache, a container
  singleton under Octane. It is evidence, not a cause.
- **Telescope records a lot and slows things down.** A performance measurement taken with Telescope
  enabled is measuring Telescope too.
- **Mass update/delete fires no model events**, so an observer you are relying on genuinely did not
  run. This is documented behaviour, not a bug.
- **`--env` and the queue worker's environment** can differ from your shell's. `php artisan about`
  in the same context as the failure.

## Don't

- Don't wrap the failing call in `try/catch` and return `null` to make the error go away. That moves
  the failure to somewhere with less information.
- Don't raise `tries`, `timeout`, or `retry_after` to stop a job failing. Those change how often you
  see the bug, not whether it exists — and a `timeout` that exceeds `retry_after` creates duplicates.
- Don't leave `dd()`, `dump()`, `ray()`, or `Log::debug` in the fix. `SKILL.md` step 5: remove
  temporary instrumentation and confirm it did not conceal the signal.
- Don't debug against production data or run `migrate:fresh` anywhere you cannot afford to lose.
- Don't conclude from a green test suite. If the suite uses `sync`/`array` drivers, it cannot see the
  class of bug you are chasing.
