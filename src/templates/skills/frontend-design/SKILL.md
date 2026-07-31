---
name: frontend-design
description: Design, implement, or critique distinctive website and product interfaces with strong visual hierarchy, usable interaction flows, responsive behavior, and accessibility. Use for landing pages, web apps, dashboards, component redesigns, UI polish, UX reviews, design systems, or any frontend task where visual and interaction quality matters.
---

# Frontend design

Treat design as part of the product behavior. Make the interface specific to its subject and
audience while preserving the project's framework, design system, content, and constraints.

## Establish the direction

Before implementation, identify:

- the user, their primary task, and the page or flow's single most important outcome;
- required content, states, actions, devices, and technical constraints;
- existing brand tokens, components, patterns, and reference screens that must remain coherent;
- one visual thesis describing the interface's mood, material, typography, and energy;
- one signature element worth remembering, with everything else supporting rather than competing.

When the brief leaves details open, choose a concrete subject and audience and state the choice.
Derive visual ideas from that subject's real materials, language, artifacts, and environment. Do
not fill missing direction with whatever aesthetic is currently fashionable.

## Design the experience before the surface

Map the shortest clear path through the task. Keep primary actions visually dominant, secondary
actions available, and destructive actions distinct. Design every consequential state:

- initial, loading, empty, partial, success, error, disabled, and permission-limited;
- hover, focus, active, selected, expanded, and validation feedback;
- narrow mobile, common desktop, wide viewport, zoomed text, and long or translated content.

Use interface copy as navigation. Prefer plain, specific verbs; keep the same action name through
controls, confirmation, and results. Errors say what happened and how to recover. Empty states
offer a relevant next action rather than decoration.

## Build a coherent visual system

- Start with hierarchy and composition, not a catalog of components.
- Define reusable tokens for color, type, spacing, radius, borders, elevation, and motion.
- Give typography a deliberate scale, line length, weight, and role. Do not rely on size alone
  to express hierarchy.
- Use color to communicate hierarchy and state, never as the only carrier of meaning.
- Prefer whitespace, alignment, contrast, scale, and imagery before adding containers or chrome.
- Use cards only when grouping or interaction requires a card. Avoid default dashboard mosaics,
  nested rounded panels, decorative gradients, fake metrics, and ornamental icon rows.
- Let structural devices encode real information. Numbering belongs to ordered content, badges
  to meaningful status, and dividers to actual grouping.
- Spend boldness in one place. Remove decoration that does not clarify content, brand, or action.

Make aesthetic choices from the brief rather than from a fixed anti-pattern list. A familiar
style is valid when the subject calls for it; it is weak when it appears only because no decision
was made.

## Make accessibility part of the design

- Use semantic elements and native controls before ARIA substitutes.
- Preserve a logical heading structure, reading order, focus order, and visible focus treatment.
- Give every control an accessible name and every field a persistent label, instructions, and
  programmatically associated error when needed.
- Ensure the whole flow works by keyboard without traps; do not hide required actions behind hover.
- Provide useful text alternatives for meaningful images and empty alternatives for decoration.
- Verify text, control, focus, and status contrast; never encode meaning with color alone.
- Support reflow, text resizing, coarse pointers, and practical target sizes.
- Respect reduced-motion preferences and provide controls for motion that persists or distracts.

Accessibility is a quality floor, not a visual style. Do not trade comprehension, focus, contrast,
or operability for novelty.

## Implement in the project's language

Read the existing UI before changing it. Reuse its framework, routing, components, tokens, data
patterns, and test approach. Extend shared primitives when the new behavior is truly shared;
otherwise keep the change local. Do not add a dependency or replace the design system merely to
recreate something the project already provides.

Use real content or representative content with realistic lengths. Keep semantic HTML separate
from visual styling. Build responsive behavior from content pressure and available space rather
than arbitrary device names. Motion should explain hierarchy, continuity, or state; one composed
transition is usually stronger than many unrelated effects.

## Critique and verify

Render the result whenever tooling permits and inspect it rather than trusting the source. Check:

1. The first viewport makes the purpose, hierarchy, and primary action obvious.
2. Mobile and desktop layouts preserve task order without overflow, clipping, or accidental gaps.
3. Keyboard navigation, focus visibility, form errors, reduced motion, and state announcements work.
4. Loading, empty, error, success, disabled, and long-content states remain usable.
5. Repeated elements share components or tokens instead of drifting through copied styles.
6. The result looks specific to this product and does not introduce claims or content the brief
   cannot support.

Compare the rendering with any approved reference at the same viewport. Keep iterating while the
remaining difference affects hierarchy, usability, responsiveness, accessibility, or the chosen
visual direction.

*Modified from Anthropic's Apache-2.0 `frontend-design` Agent Skill; see `LICENSE.txt` and
the repository's `THIRD_PARTY_NOTICES.md`.*
