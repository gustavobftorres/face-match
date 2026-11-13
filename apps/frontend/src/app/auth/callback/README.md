# Auth Callback Route

## Purpose
Receives Google OAuth redirects containing authorization code query parameters, exchanges them with the backend API, stores admin tokens, and returns cleanly to the Admin route.

## Files
- `page.tsx`: Animated light-theme callback handler extracting the `code` query parameter and redirecting to `/admin`.
