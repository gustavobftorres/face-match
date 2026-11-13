# lib

Central frontend utilities, API clients, shared TypeScript contracts, and centralized Framer Motion choreography presets.

## Files

### `api.ts`
Centralized HTTP API client reading `VITE_API_URL`. Exposes `fetchPublicFolders`, `searchFacesPublic` (with automatic `resizeImageForUpload` downscaling for large selfies), `indexFolderAdmin`, `getDriveImageUrl` (supporting `thumb`, `preview`, and `full` variants), `fetchAuthUrl`, `exchangeCode`, and `fileToBase64`.

### `types.ts`
Shared domain contracts including `IndexedFolder`, `FaceSearchMatch`, `SearchResponse`, and `AuthState`.

### `animations.ts`
Spring physics presets (`springs`), smooth cubic-bezier timings (`easings`), and reusable GPU-accelerated Framer Motion variants (`fadeInUp`, `scaleInPop`, `staggerContainer`, `staggerFastContainer`, `staggerItem`, `modalBackdrop`, `modalSheet`).

### `utils.ts`
Class name merging helper (`cn`) using `clsx` and `tailwind-merge`.

## Usage Example

```tsx
import { motion } from "framer-motion";
import { staggerContainer, staggerItem, springs } from "@/lib/animations";

export function ExampleGrid({ items }: { items: string[] }) {
  return (
    <motion.div variants={staggerContainer} initial="hidden" animate="visible">
      {items.map((item) => (
        <motion.div key={item} variants={staggerItem} transition={springs.snappy}>
          {item}
        </motion.div>
      ))}
    </motion.div>
  );
}
```
