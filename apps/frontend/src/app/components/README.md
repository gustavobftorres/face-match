# Home Route Components

## Purpose
Route-owned Portuguese (`pt-BR`) UI components powering the public photo discovery workspace.

## Components
- `hero-banner.tsx`: Full-width hero stage pairing interactive confetti particles with direct selfie upload/camera actions.
- `folder-picker.tsx`: Horizontal scrollable pill bar allowing quick event album selection.
- `selfie-uploader.tsx`: Minimal dropzone with mobile camera (`capture="user"`) and gallery upload buttons.
- `selfie-preview-card.tsx`: Uploaded portrait preview featuring a smooth warm scan sweep during search.
- `search-results-panel.tsx`: Transitions smoothly across idle, loading skeleton, and match results states.
- `search-results-grid.tsx`: Responsive photo match grid rendering cached `thumb` images with progressive loading and full-resolution download links.
- `image-detail-modal.tsx`: `AnimatePresence` modal lightbox displaying instant thumbnail placeholder transitions into sharp `preview` resolution with original download triggers.
