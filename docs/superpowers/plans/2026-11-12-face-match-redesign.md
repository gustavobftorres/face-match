# Face Match Architecture & UI/UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Face Match into a professional, enterprise-grade product with a clean light theme following C155 standards, eliminate login requirements for general face searching, and implement one-time Google Drive folder ingestion with cached embeddings for instant searches.

**Architecture:**
- **Frontend (C155 Standard)**: Light enterprise theme (`#f8fafc` background, `#00578D` / `#2563eb` primary blue, crisp slate borders, calm typography, responsive SaaS layout). Modular architecture with shared UI primitives in `src/components/ui`, layout shells in `src/components/layout`, thin route pages, and route-owned components in `src/app/components`.
- **Public Search**: General users select an indexed folder, upload a selfie, and query precomputed embeddings instantly without logging in.
- **Admin Ingestion**: Google OAuth is reserved strictly for admins/organizers who upload and index Drive folders. Celery extracts face embeddings once and persists them in SQLite/storage.
- **Backend Service**: Extends FastAPI to support listing indexed folders, searching against cached embeddings in memory/database, and incremental background indexing.

**Tech Stack:** React 19, Vite 6, Tailwind CSS 4, Framer Motion, Lucide React, FastAPI, Celery, Redis, SQLite, face_recognition, dlib.

## Global Constraints
- Zero tolerance for in-code comments (inline, block, docstrings).
- High modularity: files under 200 lines where practical, separated into clean layers.
- Mandatory `README.md` in every directory.
- Security: never hardcode secrets, use `.env` / `.env.local`.

---

### Task 1: Design Tokens & Layout Shell (C155 Light Theme)

**Files:**
- Modify: `apps/frontend/src/app/globals.css`
- Create: `apps/frontend/src/components/layout/header.tsx`
- Create: `apps/frontend/src/components/layout/app-shell.tsx`
- Create: `apps/frontend/src/components/layout/README.md`
- Create: `apps/frontend/src/components/ui/badge.tsx`
- Create: `apps/frontend/src/components/ui/panel.tsx`
- Modify: `apps/frontend/src/components/ui/button.tsx`
- Modify: `apps/frontend/src/components/ui/card.tsx`
- Modify: `apps/frontend/src/components/ui/input.tsx`

**Interfaces:**
- `AppShell({ children, adminSlot })`: Main SaaS container layout with light header, logo, search navigation, and optional admin portal link.
- `Panel({ title, description, children, action, className })`: Standard bordered white surface card.
- `Badge({ variant, children })`: Status indicator (success, warning, neutral, info).

- [ ] **Step 1: Update globals.css with C155 design tokens and light palette**
Replace the dark-only styles with CSS variables for surfaces, text, primary colors, borders, and controls.

- [ ] **Step 2: Create design system primitives in `src/components/ui`**
Add `Panel`, `Badge`, and update `Button`, `Input`, `Card` to use light enterprise styles.

- [ ] **Step 3: Create layout shells in `src/components/layout`**
Create `Header` with logo, navigation tabs ("Search Photos", "Manage Folders"), and `AppShell` wrapper.

- [ ] **Step 4: Verify build and visual shell**
Run `npm run build` in `apps/frontend` to verify TypeScript and Tailwind compilation.

---

### Task 2: Public Face Search UI (No Login Required)

**Files:**
- Create: `apps/frontend/src/app/components/folder-picker.tsx`
- Create: `apps/frontend/src/app/components/selfie-uploader.tsx`
- Create: `apps/frontend/src/app/components/search-results-grid.tsx`
- Create: `apps/frontend/src/app/components/image-detail-modal.tsx`
- Create: `apps/frontend/src/app/components/README.md`
- Modify: `apps/frontend/src/app/page.tsx`
- Modify: `apps/frontend/src/lib/types.ts`
- Modify: `apps/frontend/src/lib/api.ts`

**Interfaces:**
- `FolderPicker({ folders, selectedId, onSelect })`: Dropdown or grid selector for pre-indexed albums.
- `SelfieUploader({ onImageSelected, isSearching })`: Drag-and-drop or webcam capture for reference face.
- `SearchResultsGrid({ matches, onSelectImage })`: Responsive gallery of matched photos with match confidence.
- `api.searchFaces(folderId, selfieBase64)`: Public POST request returning matches instantly without requiring `access_token`.

- [ ] **Step 1: Define folder and search types in `src/lib/types.ts`**
Add `IndexedFolder`, `FaceSearchMatch`, `SearchResponse` types.

- [ ] **Step 2: Add public search and folders API client functions in `src/lib/api.ts`**
Add `listPublicFolders()` and `searchFacesInFolder(folderId, selfieBase64)`.

- [ ] **Step 3: Build `FolderPicker` and `SelfieUploader` components**
Create clean, light-themed components for selecting folders and dropping selfies.

- [ ] **Step 4: Refactor `page.tsx` into a thin route orchestrator**
Remove mandatory login barrier from root page. Allow anyone to pick an indexed folder, drop their photo, and search immediately.

- [ ] **Step 5: Verify build**
Run `npm run build` in `apps/frontend`.

---

### Task 3: Admin Google Drive Folder Ingestion Portal

**Files:**
- Create: `apps/frontend/src/app/admin/page.tsx`
- Create: `apps/frontend/src/app/admin/components/folder-indexing-form.tsx`
- Create: `apps/frontend/src/app/admin/components/indexed-folders-table.tsx`
- Create: `apps/frontend/src/app/admin/components/README.md`
- Create: `apps/frontend/src/app/admin/README.md`
- Modify: `apps/frontend/src/main.tsx`
- Modify: `apps/frontend/src/lib/api.ts`

**Interfaces:**
- `/admin` route: Protected view where organizers sign in with Google to paste Drive folder links and monitor indexing progress.
- `api.indexDriveFolder(driveLink, accessToken)`: Starts Celery background task to extract and persist embeddings.

- [ ] **Step 1: Add admin indexing endpoints in `src/lib/api.ts`**
Add `indexDriveFolder(folderLink, accessToken)` and `fetchFolderStatus(folderId)`.

- [ ] **Step 2: Create Admin Ingestion view and components**
Build `FolderIndexingForm` and `IndexedFoldersTable` with clear progress and status indicators.

- [ ] **Step 3: Register `/admin` route in `main.tsx`**
Connect route into React Router.

- [ ] **Step 4: Verify build**
Run `npm run build` in `apps/frontend`.

---

### Task 4: Backend Persistent Embedding Storage & Public Search API

**Files:**
- Create: `apps/backend/app/services/embedding_store.py`
- Create: `apps/backend/app/services/README.md` (update)
- Modify: `apps/backend/app/services/ai_service.py`
- Modify: `apps/backend/app/workers/tasks.py`
- Modify: `apps/backend/app/api/endpoints.py`
- Create: `apps/backend/tests/test_embedding_store.py`

**Interfaces:**
- `EmbeddingStore`: SQLite database saving `folders` (`id`, `name`, `drive_folder_id`, `photo_count`, `indexed_at`) and `photo_faces` (`photo_id`, `drive_file_id`, `file_name`, `thumbnail_url`, `encoding_bytes`).
- `api.get("/api/v1/folders")`: Returns all indexed folders.
- `api.post("/api/v1/folders/{folder_id}/search")`: Takes selfie, computes 1 encoding, and returns matches using fast vector/array comparison without re-scanning Drive.
- `api.post("/api/v1/admin/index-folder")`: Downloads folder photos once, computes embeddings once, and saves to store.

- [ ] **Step 1: Create `embedding_store.py` SQLite service**
Store folder metadata and serialized face encodings (128 floats per face) with query capabilities.

- [ ] **Step 2: Add fast vector matching in `ai_service.py`**
Compare a single reference encoding against all stored encodings for a folder.

- [ ] **Step 3: Update `endpoints.py` with public search and folder listing routes**
Expose `/api/v1/folders` and `/api/v1/folders/{id}/search` without authentication required.

- [ ] **Step 4: Update Celery worker tasks to persist embeddings**
Save all extracted face encodings to `EmbeddingStore` upon processing.

- [ ] **Step 5: Run tests**
Run `pytest apps/backend/tests` and verify all tests pass.

---

### Task 5: End-to-End Integration & Polish

**Files:**
- Modify: `Makefile`
- Modify: `README.md`
- Verify services running cleanly on ports 3000 and 8000.

- [ ] **Step 1: Test end-to-end user experience in browser**
- [ ] **Step 2: Verify zero comments and all directory READMEs are present**
- [ ] **Step 3: Verify clean build and service startup**
