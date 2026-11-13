# hooks

Custom React hooks for administrator Google Drive authentication state and persistence.

## Files

### `use-auth.ts`
Manages admin OAuth state via `localStorage`:
- Loads stored credentials on mount and automatically expires stale tokens after 1 hour.
- Exposes `{ authState, login, logout, handleCallback }` for `/admin` and `/auth/callback`.
