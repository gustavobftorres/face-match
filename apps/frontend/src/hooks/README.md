# hooks

Custom React hooks for authentication, WebSocket scan sessions, and locale/i18n.

## Files

### `use-auth.ts`
Manages auth state via `localStorage`. Key behaviours:
- Loads stored auth on mount; if `expiresAt` is in the past, clears the stored state automatically.
- `login()` redirects to Google OAuth.
- `handleCallback(code)` exchanges the auth code for a token and stores `expiresAt = now + 1h`.
- `logout()` clears storage and resets state.

### `use-scan-socket.ts`
Maintains a WebSocket connection to the backend scan service. Exposes `connect`, `disconnect`, and an `error` state.

### `use-locale.ts`
Detects the browser language via `navigator.language` and returns a `t(key)` translation function.
- Maps `pt-*` locales to `"pt-BR"`, everything else to `"en"`.

## Usage Example

```ts
const { t } = useLocale();
console.log(t("signInWithGoogle")); // "Sign in with Google" or "Entrar com Google"
```
