---
field: Frontend
owners: beta_fe
---
## Accessible by default
tags: accessibility, a11y, wcag, keyboard, screen reader, contrast
when: page, form, button, modal, menu, ui, screen, dashboard
decide: Use real buttons, links and labels; keep 4.5:1 text contrast; make everything reachable by keyboard with a visible focus.
WCAG 2.1 AA is the floor. Test with Tab and a screen reader, not only a linter.

## Design every state
tags: loading, empty, error, state, ux
when: list, fetch, load, dashboard, search, upload
decide: Design the loading, empty, error and success states for each view, not just the happy path.
An empty state should say what to do next; an error should say what happened and how to recover.

## Mobile first, fluid layouts
tags: responsive, mobile, layout, css
when: page, layout, responsive, mobile, dashboard
decide: Lay out for a 375 px screen first, then add space; avoid fixed widths and horizontal scrolling.

## Keep forms forgiving
tags: form, validation, input, ux
when: form, sign up, login, checkout, settings, invite
decide: Label every field, validate inline after the user leaves a field, keep their input on errors, and name the fix.

## Watch the performance budget
tags: performance, bundle, images, web vitals
when: page, landing, dashboard, image, slow
decide: Keep the first load small: lazy-load heavy parts, size images, and measure LCP, INP and CLS.
