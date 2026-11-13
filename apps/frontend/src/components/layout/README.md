# Layout Shells

## Purpose
Minimal Portuguese application framing providing a clean sticky header, floating mobile navigation pill dock, and wave horizon footer.

## Components
- `header.tsx`: Single-row navigation bar with `Face Match` wordmark, animated active dot (`layoutId="desktop-nav-dot"`), and pill route action.
- `mobile-nav.tsx`: Floating centered pill dock (`md:hidden`) switching cleanly between `/` and `/admin`.
- `app-shell.tsx`: Full-width outer viewport wrapper terminated by `<WaveHorizon />`.
