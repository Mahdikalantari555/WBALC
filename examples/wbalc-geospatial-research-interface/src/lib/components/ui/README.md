# `ui/` — local primitives, shadcn conventions

This folder follows shadcn-svelte's *conventions*, not its registry output:

| Convention | Here |
| --- | --- |
| `components.json` at the app root | ✅ `style: new-york`, `cssVariables: true`, aliases |
| `$lib/utils` exporting `cn()` | ✅ `clsx` + `tailwind-merge` |
| one folder per primitive, `index.ts` barrel | ✅ `button/`, `badge/`, `card/`, `field/`, `input/`, `select/`, `alert/`, `table/`, `empty-state/` |
| variants as a record, not a colour per call site | ✅ `*-variants.ts` (`badgeVariants`, `alertVariants`, `buttonVariants`) |
| semantic tokens (`--background`, `--card`, `--ring`, …) | ✅ `src/index.css`, oklch |

## Why not the upstream registry

`components.json` points at `shadcn-svelte.com/registry`, but the components are
written here rather than copied because the upstream versions target
`tailwind-variants` + `bits-ui` and Tailwind utility classes, while this
workspace's ~4k lines of existing CSS are hand-written against CSS custom
properties. Pulling the registry in would have meant rewriting every page to
utility classes in the same change that is supposed to make the app more
consistent — a large, unverifiable diff.

The consequence is stated plainly: **this is not a shadcn codebase**, it is a
codebase that shares shadcn's structure and naming so that a future `npx
shadcn-svelte add` is a local, additive change rather than an archaeology
exercise.

## What each primitive is for

- `Button` — one button. `primary` is reserved for the action that advances the
  workflow; `ghost`/`secondary` for everything else. No `danger`-coloured button
  without a confirmation.
- `Badge` — status semantics, not decoration. `muted` means *not established*;
  it is the honest default for a value the engine did not measure.
- `Alert` — a statement about the evidence (warning/destructive/success), always
  with text; the colour never carries the meaning alone.
- `Card` — panel shell: title, optional description, actions, body.
- `Field` / `Input` / `Select` — labelled controls. A control without a label is
  a reproducibility hazard in this app: the user cannot say which knob they
  turned.
- `Table` — scrollable shell with a mandatory caption, because the unit
  (samples? classes? scenes?) *is* the claim.
- `EmptyState` — a missing record is a result here ("no reference area, so areas
  are estimates"), so it requires a hint.
