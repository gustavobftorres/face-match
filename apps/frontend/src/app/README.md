# App Routes & Styles

## Purpose
Contains the application routes, route-owned feature components, and global vibrant light-mode stylesheet.

## Files & Subdirectories
- `page.tsx`: Public zero-login face discovery route (`/`) with `HeroBanner`, `FolderPicker`, `SelfieUploader`, and `SearchResultsGrid`.
- `globals.css`: Tailwind v4 theme variables, light ambient radial gradient washes, and font definitions.
- `components/`: Route-owned components for the `/` public search route.
- `admin/`: Administrator Drive indexing route (`/admin`) and its route-owned components.
- `auth/callback/`: OAuth callback route (`/auth/callback`) handing Drive code exchanges and redirecting to `/admin`.
