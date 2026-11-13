# Admin Route

## Purpose
Portuguese (`pt-BR`) administration interface for connecting Google Drive via OAuth and indexing event albums.

## Internal Architecture
- `page.tsx`: Coordinates KPI summary counters, Drive folder indexing form, and live polling while indexing runs.
- `components/`: Route-owned components (`admin-stats-bar.tsx`, `folder-indexing-form.tsx`, `indexed-folders-table.tsx`).
