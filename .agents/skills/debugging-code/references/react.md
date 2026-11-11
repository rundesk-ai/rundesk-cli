# Debugging React

This page is mechanics: where the evidence already is, and how to get more. Which rule the symptom
violates belongs to `using-reactjs`.

## See what actually happened

Install React DevTools and read the tree before reading the source. The Components panel shows the
props, state, hooks, and context a component actually received on the last commit — which is
frequently not what the source suggests it received.

Three settings pay for themselves immediately:

- **Highlight updates when components render.** Turns "I think it re-renders" into an observation.
- **Record why each component rendered** in the Profiler. It attributes a render to a prop, state,
  context, or parent change by name.
- **Break on warnings**, so the first warning stops execution while the stack is still intact.

Development builds carry the full warning text. A minified production error is a numeric code plus a
link; decode it rather than guessing, and reproduce in development before drawing conclusions.

## Read a development-only symptom correctly

Strict Mode double-invokes component bodies, state initializers, `useMemo` and `useReducer`
functions, and runs effects setup–cleanup–setup, in development only. This is the single most common
source of false diagnoses in React:

- "It runs twice" is usually Strict Mode working, not a bug — but a component that *breaks* when run
  twice has an impurity Strict Mode just exposed. Do not fix the symptom by removing Strict Mode.
- Counts, analytics events, and appended items doubling in development is the classic signal.
  Reproduce with Strict Mode off to confirm the behavior is development-only, then put it back and
  fix the impurity.

Never ship a fix whose evidence is "it stopped happening after I disabled Strict Mode."

## Is it state, or is it render?

Separate the two before instrumenting anything:

1. In the Components panel, select the component and read its state and props at rest. If the value
   is already wrong there, the render is faithfully displaying bad state — investigate the update
   that produced it, not the JSX.
2. If the value is right in DevTools and wrong on screen, the defect is in the render output or a
   child that ignores the prop.
3. If the value flickers between correct and stale, suspect a stale closure or two sources of truth
   for one value.

A stale closure shows as a handler or effect reading a value from a render that has already been
replaced. Log the value together with a render marker rather than alone:

```jsx
const renderId = useRef(0);
renderId.current += 1;          // debugging only; remove before committing
useEffect(() => {
  console.log('effect', { renderId: renderId.current, query });
}, [query]);
```

If the effect logs an old `query` while the input shows a new one, the dependency array or the
closure is the cause.

## Stop an infinite render loop

The stack trace for "Too many re-renders" points at the render, not the cause. Work through these in
order, because they are ordered by how often they are the answer:

| Signal | Likely cause |
|---|---|
| Loop begins immediately on mount | `setState` called during render rather than in a handler or effect |
| Loop tied to an effect | Effect sets state that is also in its own dependency array |
| Loop with an object or array dependency | A new identity every render, so the dependency never compares equal |
| Loop from a context consumer | Provider value recreated each render |
| `getSnapshot should be cached` error | `useSyncExternalStore`'s `getSnapshot` returns a fresh object per call |

That last one is worth recognizing on sight: React reports it explicitly, and the cause is always the
same — the snapshot must be a cached, immutable value that only changes when the store changes.

To find which dependency changed, log the array against the previous one rather than reasoning about
it:

```jsx
const prev = useRef([]);
useEffect(() => {
  deps.forEach((d, i) => { if (!Object.is(d, prev.current[i])) console.log('changed', i, prev.current[i], d); });
  prev.current = deps;
});
```

## Debugging hydration

A hydration mismatch means the server HTML and the first client render disagree. React reports the
difference; read what it names before theorizing.

The usual causes, in order:

- A value that differs by environment: `Date.now()`, `Math.random()`, a locale or timezone format, or
  a `window` check evaluated during render.
- Content that depends on `localStorage`, a cookie, or a media query — available on the client,
  absent on the server.
- Invalid HTML nesting that the browser silently corrects, so the client tree no longer matches the
  server string.
- A `useSyncExternalStore` without a `getServerSnapshot`, or one returning different data than the
  client's first read.

Confirm by viewing source, not the inspector. The inspector shows the DOM after React has already
corrected it; view-source shows what the server actually sent.

Suppressing a mismatch on a single element is legitimate for a genuinely environment-dependent value.
Suppressing it to make the warning stop hides a real divergence that will render wrong.

## Get errors to surface at all

An error thrown during render no longer propagates to a global handler by default in React 19.
Uncaught errors go to `window.reportError` and errors caught by an error boundary go to
`console.error`. Reporting that hooked the global `error` event will simply stay quiet.

When errors are disappearing, check whether the root registers `onUncaughtError` and `onCaughtError`;
if it does not, an error boundary somewhere may be swallowing the failure into a fallback with no
record. Temporarily rendering the boundary's captured error, or removing the boundary, is a valid
diagnostic step.

Suspense fallbacks hide a different failure: a component that suspends forever shows a spinner and
throws nothing. If a region never resolves, suspect the promise, not the component.

## Symptom to first place to look

| Symptom | Look first |
|---|---|
| Value on screen is stale | Component state in DevTools; then the closure the handler captured |
| Update ignored | Whether state was mutated instead of replaced |
| Component renders far more than expected | Profiler "why did this render"; then parent identity and context value |
| Renders twice, development only | Strict Mode — confirm before treating it as a defect |
| "Too many re-renders" | `setState` during render; then effect dependency identity |
| Works in development, breaks in production | Decode the minified error; check anything relying on development-only warnings |
| Blank screen, no error | An error boundary fallback, or a Suspense boundary that never resolves |
| Hydration mismatch | View-source versus the client's first render; environment-dependent values |
| Test warns "not wrapped in act" | An update landed after the test stopped waiting — find the un-awaited async work |

## Traps that send you the wrong way

- **Treating Strict Mode double-invocation as the bug.** It is the messenger.
- **Reading the inspector for hydration problems.** React has already patched the DOM by then.
- **Adding `useMemo` to fix a loop.** Memoizing a dependency can hide the identity problem while
  leaving the real second source of truth in place. Find why the value is recreated.
- **Trusting a `console.log` in render.** Render may run twice, be discarded, or be replayed;
  attribute every log to a render or a commit.
- **Blaming concurrency first.** Torn or inconsistent values are usually an external store read
  outside `useSyncExternalStore`, not a React scheduling bug.
- **Deleting the dependency array to stop a warning.** That converts a stale-closure defect into a
  render-loop defect.

## Don't

- Do not commit debugging instrumentation — render counters, logs, or temporary boundaries.
- Do not disable Strict Mode, an error boundary, or a lint rule to make a symptom disappear.
- Do not conclude from a development build alone when the report came from production.
- Do not report a cause you have only inferred from the source without observing it in the tree.
