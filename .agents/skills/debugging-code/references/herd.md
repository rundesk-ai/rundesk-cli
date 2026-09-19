# Debugging Laravel Herd

Use this reference only when Herd serves the failing application. Herd owns the local DNS, nginx,
PHP-FPM, site mapping, and optionally supporting services; `laravel.md` owns what happens after the
request enters Laravel.

## Prove which site Herd serves

Run these from the checkout you intend to debug:

```sh
herd --version   # prove the installed command and record its version
herd which       # show the Herd driver for this directory
herd sites       # every site Herd currently serves
herd paths       # parked parent directories
herd links       # explicit site-to-directory links
herd parked      # sites discovered below parked paths
herd site-information  # details for the site at this directory
```

A parked path exposes its child directories by name; a link maps an explicit name to one directory.
After a move, rename, or second clone, prove the domain still resolves to the intended checkout.

- **Bad:** edit Laravel routes because `orders.test` shows Herd's 404 page.
- **Good:** verify `orders.test` and its document root in `herd sites` first. A Herd 404 means the
  request has not yet reached Laravel; repair the exact parked path, link, or driver, then retry.

Do not run `herd park` or `herd link` merely to inspect state: they mutate Herd's mapping, and
`herd link` can also change the application's `APP_URL`. Read with `sites`, `paths`, `links`, and
`parked`; change a mapping only after proving it is wrong.

Finally, request the exact registered URL with `curl -I http://orders.test` (or its HTTPS form).
Registration and an HTTP response are separate evidence; neither is implied by a `.test` name.

Do not delete a project from Herd's Site Manager while diagnosing a mapping: Herd documents that
deleting a parked site there deletes its directory and files. Use `herd unlink <name>` only for a
confirmed stale link; it does not delete the project.

## Prove PHP identity on both paths

Per-site isolation changes the PHP used by nginx and by Herd's proxies. It does not prove that the
shell's plain `php` or `composer` resolves to the same installation.

```sh
herd isolated
herd which-php
herd php -v
php -v
herd php --ini
php --ini
herd php -m      # compare loaded modules when an extension differs
php -m
herd php artisan about
```

If the failure appears only in the browser, compare the site's isolated version and Herd PHP
configuration before changing application code. If it appears only in a terminal command, repeat
that command through `herd php` or `herd composer`; these proxies select the site's isolated PHP.

- **Bad:** run `herd use 8.3` or rewrite `PATH` because one isolated site reports a missing
  extension.
- **Good:** use `herd which-php`, `herd php --ini`, and `herd isolated` to prove the mismatch. Use
  `herd isolate <version>` for that site, or repair shell configuration only when the shell is the
  surface that is wrong. `herd use` changes the global default for every non-isolated site.

Use `herd debug <php-command>` when Xdebug-backed CLI debugging is intended: Herd runs the command
with the site's PHP and its `debug.ini`. Do not conclude that Xdebug is broken because plain
`php artisan ...` did not load that configuration.

Start local workers through the same boundary, for example `herd php artisan queue:work`, then use
`laravel.md` to diagnose queue state. A worker launched by another PHP can reproduce a different
extension, ini, or version contract than the served site. Inspect the existing worker's launch
command or process-manager configuration before stopping it; a fresh correct worker does not prove
which runtime launched the failing one.

## Classify the failing boundary

| Symptom | First evidence | Avoid |
|---|---|---|
| Domain does not resolve | Herd helper/DNS state; VPN or another DNS service | Editing routes or the hosts file blindly |
| Herd 404 | `herd sites`, `herd paths`, `herd links` | Clearing Laravel caches |
| TLS or redirect failure | `herd secured`, exact hostname and browser redirect cache | `curl -k` as a fix |
| 502 / Bad Gateway | `herd log nginx`; PHP-FPM status and site nginx config | Changing controller code |
| Laravel exception | `storage/logs`, then `laravel.md` | Reconfiguring Herd first |
| CLI and browser disagree | PHP binary, version, and ini on each path | A global PHP switch before comparison |
| Database or Redis refused | `herd services:list` when Herd Pro manages that service; resolved Laravel host/port | Creating or deleting a service speculatively |

macOS uses dnsmasq for local site resolution; Windows writes Herd-managed entries through its
helper service. Follow the platform-specific Herd troubleshooting page. Do not copy a hosts-file,
service, or process-kill remedy from the other platform.

## Read evidence before restarting

`herd log` lists and tails Herd logs; `herd log nginx` narrows to nginx. Laravel's application logs
remain under its configured log channel, commonly `storage/logs`. Match timestamps across both:
nginx/PHP-FPM explains whether the request reached PHP, while Laravel explains what the application
did with it.

Herd Pro's Dumps window can intercept dumps and record queries, jobs, HTTP calls, and logs. Its PHP
extension injects during early bootstrap, so disable the relevant capture feature and repeat the
case if the symptom appears only while Dumps is enabled. This is a discriminating experiment, not
a reason to remove application code or extensions at random.

`herd restart` restarts all Herd services. Capture the failure and logs first; if restarting clears
it, report that runtime state is implicated and continue to identify which process or configuration
was stale. Do not report a restart as the root cause. Avoid manual edits to Herd's global nginx
configuration: Herd may rewrite it. Never use destructive service deletion, broad process kills, a
Herd reinstall, or certificate-trust bypass as an opening move.

## Prove the correction

1. Re-run the exact failing URL or command through the same runtime path.
2. Confirm the intended checkout, PHP binary/version/ini, and dependent service identity.
3. Check both Herd and Laravel logs for the same attempt.
4. Reproduce once without temporary dumps, debug extensions, or bypasses.
5. Record whether the correction changed site mapping, runtime selection, service state, TLS, or
   application code; do not collapse those into “Herd was broken.”
