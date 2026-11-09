# lib

Central library for API calls, type definitions, utility functions, and i18n translations.

## Files

### `api.ts`
API functions: `fetchAuthUrl`, `exchangeCode`, `startScan`. All endpoints read from `NEXT_PUBLIC_API_URL`.

### `types.ts`
Shared TypeScript interfaces: `AuthState` (with `expiresAt`), `WebSocketMessage` union, `ScanMatch`, etc.

### `i18n.ts`
Translation dictionaries for `en` and `pt-BR`. Exports `Locale`, `TranslationKey`, and `getTranslations(locale)`.

### `utils.ts`
`cn()` helper for merging class names.

## Usage Example

```ts
import { getTranslations } from "@/lib/i18n";
const t = getTranslations("pt-BR");
console.log(t.signInWithGoogle); // "Entrar com Google"
```
