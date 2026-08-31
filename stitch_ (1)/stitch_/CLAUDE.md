# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LuminaPortal** — a static HTML educational assessment and testing system. No build tools, no backend, no package manager. Pure HTML5, vanilla JavaScript (inline), and Tailwind CSS (CDN).

## Running the Project

Since this is a static site, open HTML files directly in a browser or serve them locally:

```bash
python -m http.server 8000
# then visit http://localhost:8000
```

No build step, no compilation, no dependencies to install.

## Page Flow & Architecture

The app is a multi-page static site. Pages are standalone HTML files; all JavaScript is inline.

**Student flow:** `index.html` → `start.html` → `test.html` → `results.html` (or `locked.html` on violation)

| File | Role |
|------|------|
| `index.html` | Student dashboard — browse and select tests |
| `start.html` | Pre-test rules and requirements |
| `test.html` | Timed test interface with question answering |
| `results.html` | Score and performance breakdown |
| `locked.html` | Anti-cheat violation lock screen |
| `constructor.html` | Educator test-building interface |
| `admin.html` | Admin analytics and student management |

The `_1/` through `_6/` subdirectories are reference snapshots — each contains `code.html` (a working component) and `screen.png` (its visual target). These serve as design source-of-truth.

## Tailwind Configuration

Each HTML file declares its own inline Tailwind config (in a `<script>` block before the Tailwind CDN script). Key settings shared across pages:

```js
tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: { primary: '#4848e5' },
      borderRadius: { DEFAULT: '0.5rem', ... },
      fontFamily: { sans: ['Inter', ...] }
    }
  }
}
```

Dark mode is toggled via a `dark` class on `<html>` and persisted in `localStorage`.

## State & Persistence

- **Theme:** `localStorage` key for dark/light mode
- **Test progress:** `sessionStorage` (timer state, current question, answers)
- No cookies, no server-side state

## Anti-Cheat System

`test.html` monitors for focus loss (tab switching, window blur). On violation, the user is redirected to `locked.html`. Partial submissions are recorded client-side before the lock occurs.

## Design System Conventions

- **Primary color:** `#4848e5` (purple/indigo) — referenced as `primary` in Tailwind config
- **Backgrounds:** `#f6f6f8` (light), `#111121` (dark)
- **Icons:** Material Symbols Outlined via Google Fonts CDN
- **Font:** Inter via Google Fonts CDN
- **Status colors:** emerald (success), amber (warning), red (error)
- Modal state: toggled via `.hidden` / `.open` CSS classes using JavaScript

## Key Patterns

- All JS is inline in `<script>` tags at the bottom of each `<body>`
- No component system — HTML is duplicated across pages
- Modals are pre-rendered in HTML and shown/hidden via class toggling
- Animations use Tailwind's `transition` utilities + custom keyframes defined inline
