# Debugging Vue and Nuxt

Most Vue bugs are one of three things: **state that is not reactive**, **an effect that runs at an
unexpected time**, or **the server and client disagreeing**. Establish which before reading any
component code.

## See what actually happened

**Vue DevTools is the primary instrument**, and each tab answers a different question:

| Tab | Question it answers |
|---|---|
| Components | What is the tree, and what is this component's actual state right now? |
| Timeline | What happened in what order — events, renders, performance |
| Pinia | What is in the store, and does editing it move the UI? |
| Router | Which route matched, with what params? |
| Inspector (Vite) | Which component rendered *this* DOM node? |
| Graph | How are modules related — useful for an unexpected import |

Two more switches:

```js
app.config.performance = true              // component render timings in the browser profiler
app.config.errorHandler = (err, instance, info) => { /* every uncaught error, with context */ }
```

`errorCaptured` on a parent gives you the same for a subtree, and is how you find which child throws
when the stack is all framework frames.

## Is it state, or is it render?

This is the first bisection, and it takes ten seconds:

1. **Open DevTools → Components and read the value.**
2. **Is the value correct there?** Then the state is fine and the render or the template binding is
   wrong.
3. **Is the value stale there?** Then reactivity is broken upstream — the state never changed, or the
   change was not tracked.
4. **Is the value correct in DevTools but wrong on screen?** Edit it in DevTools. If the UI updates,
   you have a reactivity connection that works and a render path that ran at the wrong time.

Then log the ref itself, not its value at that instant:

```js
console.log(myRef)            // the ref object — inspect .value live in the console
console.log(toRaw(state))     // the plain object, without proxy noise
watchEffect(() => console.log('changed:', myRef.value))   // logs every change, with the trigger
```

A bare `console.log(myRef.value)` prints a snapshot from setup and tells you nothing about whether it
ever changes afterwards. This is the single most common reason a Vue developer concludes "the value
never updates" when it does.

## Find what triggered a render

When a component renders too often, or does not render when it should, Vue has purpose-built hooks:

```js
onRenderTracked((e) => { debugger })     // a dependency was read during render
onRenderTriggered((e) => { debugger })   // a dependency changed and caused a re-render
```

Vue's guidance is to put a `debugger` statement in the callback and inspect the event, which names
the target and the key. `onRenderTracked` answers *"is Vue tracking the thing I think it is?"* —
often the answer is no, and that is the bug.

Watchers and computeds take the same debugging hooks via `onTrack` / `onTrigger` options.

## Symptom to first place to look

| Symptom | Look first |
|---|---|
| Component does not update | Reactivity lost. Destructured a `reactive()` or a store without `storeToRefs`; reassigned a `reactive()`; the value is a plain variable, not a ref |
| Store value never changes in the template | `const { x } = useStore()` — needs `storeToRefs` |
| Prop-derived value is stale | Captured at setup instead of `computed(() => props.x)` |
| Watcher never fires | `watch(obj.count, …)` — a reactive property is not a valid source. Use a getter |
| Value updates but DOM does not | Assert after `await nextTick()`; updates are batched |
| List items keep the wrong state after reorder | Missing or index-based `:key` |
| Infinite render loop | State mutated during render, or in a `computed`. Use `onRenderTriggered` to see what keeps changing |
| Renders far more than expected | An unstable prop — a fresh object/array literal each render |
| Memory grows as you navigate | An effect with no teardown: listener, interval, observer, or a watcher created asynchronously |
| Works in dev, breaks in production | Build-time difference: env vars, tree-shaking, minification, or SSR only running in the built app |
| Hydration warning in the console | See below — this one is worth fixing, not silencing |
| Nuxt data fetched twice | Bare `$fetch` in `setup` instead of `useFetch`/`useAsyncData` |

## Debugging hydration

Vue "will attempt to automatically recover and adjust the pre-rendered DOM," so the app usually still
works — which is why these warnings get ignored. The cost is real: discarded nodes and re-mounted
ones, on every page load, forever.

Work the three documented causes in order, because they are cheap to check:

1. **Invalid HTML nesting** — a `<div>` inside a `<p>`, a block inside an inline element. The
   browser's parser silently repairs it, so the client tree differs from the server's. Validate the
   rendered markup.
2. **Non-deterministic values** — `Math.random()`, `Date.now()`, `crypto.randomUUID()`. Use `useId()`
   for ids; render the rest client-only.
3. **Timezone and locale** — the server's zone is not the user's. Format in `onMounted`.

Then the two the docs do not list but everyone hits: reading `window`/`localStorage` during setup,
and branching on `navigator.userAgent`.

To localize it, comment out half the template and reload — binary search works well here because the
warning names a DOM position, not a component.

**In Nuxt, do not reach for `<ClientOnly>` until you know the cause.** It makes the warning go away by
not server-rendering that subtree, which is a different behaviour, not a fix.

## Traps that send you the wrong way

- **DevTools reactivity is lazy.** The docs note DevTools "could read some component data but Vue
  might not trigger updates on it as you would expect" — use the **force refresh** button before
  concluding a value is stale.
- **`console.log` of a proxy** shows the reactive wrapper. `toRaw()` for the plain object.
- **A synchronous assertion after a state change reads the previous render.** `await nextTick()`.
- **SSR failures fall back to client rendering silently.** Your page works and no user is getting
  server-rendered HTML. Enable `throw_on_error` in test environments.
- **Source maps** — if the stack points into a vendor bundle, source maps are off or wrong. Fix that
  before reading the stack.
- **A component that only breaks in the built app** is a build problem, not a component problem.
  Reproduce with `vite build && vite preview`, not `vite dev`.
- **Vue only tracks what the render function actually reads.** State that is never referenced in a
  template or a computed is not tracked, so it will not trigger anything.

## Don't

- Don't add `:key="Math.random()"` to force re-renders. It destroys and recreates the subtree every
  render, discards child state, and hides the real reactivity bug.
- Don't `nextTick` in production code to make a race go away. It reorders the symptom.
- Don't reach for `watch` when a `computed` was wanted — a watcher that assigns to another ref is
  usually a derived value written the hard way, and it introduces an extra tick.
- Don't wrap in `<ClientOnly>` or `v-if="mounted"` to silence a hydration warning you have not
  diagnosed.
- Don't leave `debugger`, `onRenderTracked`, or `app.config.performance` in the committed fix.
