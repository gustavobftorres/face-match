export class ApiError extends Error {
  constructor(public status: number) { super(`API error ${status}`); }
}
export type Tenant = { name: string; slug: string; branding: { logo_url: string | null; colors: Record<string, string>; theme_version: number } };
export type EventInfo = { id: string; name: string; slug: string; status: string };
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...options, credentials: "same-origin", cache: "no-store" });
  if (!response.ok) throw new ApiError(response.status);
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}
export const getTenant = () => request<Tenant>("/tenant/context");
export const getSession = () => request<{ user_id: string }>("/session");
export const getEvent = (id: string) => request<EventInfo>(`/events/${encodeURIComponent(id)}`);
export const createChallenge = () => request<{ nonce: string }>("/session/challenge", { method: "POST" });
export const loginWithGoogle = (credential: string) => request("/session/google", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id_token: credential }) });
export function logout() {
  const cookie = document.cookie.split("; ").find((value) => value.startsWith("__Host-fm_csrf="));
  if (!cookie) throw new Error("CSRF cookie missing");
  return request<void>("/session", { method: "DELETE", headers: { "X-CSRF-Token": decodeURIComponent(cookie.slice(cookie.indexOf("=") + 1)) } });
}

export type GalleryJob = { id: string; status: "queued" | "processing" | "ready" | "failed" };
export type GallerySearch = { id: string; photos: string[] };
function csrfHeaders(): Record<string, string> {
  const cookie = document.cookie.split("; ").find(value => value.startsWith("__Host-fm_csrf="));
  if (!cookie) throw new Error("CSRF cookie missing");
  return { "X-CSRF-Token": decodeURIComponent(cookie.slice(cookie.indexOf("=") + 1)) };
}
const galleryPath = (id: string) => `/events/${encodeURIComponent(id)}/gallery`;
export const latestGalleryJob = (id: string) => request<{ job: GalleryJob | null }>(`${galleryPath(id)}/jobs/latest`);
export const startGalleryIndex = (id: string, folder: string) => request<GalleryJob>(`${galleryPath(id)}/index`, { method: "POST", headers: { ...csrfHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ folder }) });
export function searchGallery(id: string, selfie: File) {
  const data = new FormData(); data.append("selfie", selfie);
  return request<GallerySearch>(`${galleryPath(id)}/search`, { method: "POST", headers: csrfHeaders(), body: data });
}
export const galleryPhotoUrl = (eventId: string, searchId: string, photoId: string) => `/api/v1${galleryPath(eventId)}/searches/${encodeURIComponent(searchId)}/photos/${encodeURIComponent(photoId)}`;
