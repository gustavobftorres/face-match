# components

UI components for the application. All components accept a `t` prop (translation function from `useLocale`) for i18n support.

## Files

| Component | Description |
|---|---|
| `landing-view.tsx` | Full landing page with hero, sign-in CTA, and "How it works" 3-step section |
| `session-expired-modal.tsx` | Modal overlay shown when the Google session expires mid-scan |
| `hero.tsx` | Face photo upload dropzone with preview and scanning animation |
| `drive-input.tsx` | Drive URL input + scan trigger button with animated glow |
| `auth-button.tsx` | Sign-in / signed-in state toggle chip |
| `progress-dashboard.tsx` | Real-time scan progress bar with status, file counter |
| `results-gallery.tsx` | Grid of matched image cards with click-to-lightbox |
| `image-lightbox.tsx` | Full image viewer with download and Open in Drive actions |
| `header.tsx` | Top navigation bar |
| `animated-background.tsx` | Animated canvas gradient background |
| `cursor-particles.tsx` | Mouse-following particle trail |

## i18n

All visible strings are passed via the `t: (key: TranslationKey) => string` prop originating from `useLocale` in `page.tsx`.
