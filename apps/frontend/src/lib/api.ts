import { IndexedFolder, ScanStatusResponse, SearchResponse } from "@/lib/types";

export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}

export type DriveImageVariant = "thumb" | "preview" | "full";

export function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = (error) => reject(error);
  });
}

export async function resizeImageForUpload(
  file: File,
  maxDimension = 1000
): Promise<string> {
  if (typeof document === "undefined" || typeof createImageBitmap === "undefined") {
    return fileToBase64(file);
  }
  try {
    const bitmap = await createImageBitmap(file);
    const maxSide = Math.max(bitmap.width, bitmap.height);
    if (maxSide <= maxDimension && file.size <= 350_000) {
      bitmap.close();
      return fileToBase64(file);
    }
    const scale = maxSide > maxDimension ? maxDimension / maxSide : 1;
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      bitmap.close();
      return fileToBase64(file);
    }
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    return canvas.toDataURL("image/jpeg", 0.88);
  } catch {
    return fileToBase64(file);
  }
}

export function getDriveImageUrl(
  fileId: string,
  variant: DriveImageVariant = "thumb",
  download = false
): string {
  const params = new URLSearchParams({ size: variant });
  if (download) {
    params.set("download", "true");
  }
  return `${API_BASE_URL}/api/v1/drive/image/${fileId}?${params.toString()}`;
}

export async function fetchPublicFolders(): Promise<IndexedFolder[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/folders`);
  if (!response.ok) {
    throw new Error("Failed to load indexed folders");
  }
  return response.json() as Promise<IndexedFolder[]>;
}

export async function searchFacesPublic(
  folderId: string,
  targetFace: File | string
): Promise<SearchResponse> {
  let base64String = "";
  if (typeof targetFace === "string") {
    base64String = targetFace.includes(",") ? targetFace.split(",")[1] : targetFace;
  } else {
    const fullDataUrl = await resizeImageForUpload(targetFace);
    base64String = fullDataUrl.split(",")[1];
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/folders/${folderId}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target_face: base64String,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Search failed: ${response.statusText} - ${errorText}`);
  }

  return response.json() as Promise<SearchResponse>;
}

export async function indexFolderAdmin(
  driveLink: string,
  accessToken?: string | null
): Promise<{ folder_id: string; message: string; total_files?: number }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/folders/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      drive_link: driveLink,
      access_token: accessToken || null,
    }),
  });

  if (response.status === 401) {
    throw new AuthError("Google session expired");
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Indexing failed: ${response.statusText} - ${errorText}`);
  }

  return response.json() as Promise<{ folder_id: string; message: string; total_files?: number }>;
}

export async function fetchAuthUrl(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/google/url`);
  if (!response.ok) {
    throw new Error("Failed to fetch auth URL");
  }
  const data = (await response.json()) as { url: string; code_verifier: string };
  sessionStorage.setItem("oauth_code_verifier", data.code_verifier);
  return data.url;
}

export async function exchangeCode(code: string): Promise<{ access_token: string; email: string }> {
  const code_verifier = sessionStorage.getItem("oauth_code_verifier") ?? "";
  sessionStorage.removeItem("oauth_code_verifier");
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/google/callback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, code_verifier }),
  });
  if (!response.ok) {
    throw new Error("Failed to exchange auth code");
  }
  return response.json() as Promise<{ access_token: string; email: string }>;
}

export async function startScan(
  driveLink: string,
  targetFace: File,
  accessToken: string
): Promise<{ message: string; total_files: number; scan_id: string }> {
  const fullDataUrl = await fileToBase64(targetFace);
  const base64Image = fullDataUrl.split(",")[1];

  const response = await fetch(`${API_BASE_URL}/api/v1/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      drive_link: driveLink,
      target_face: base64Image,
      access_token: accessToken,
    }),
  });

  if (response.status === 401) {
    throw new AuthError("Google token expired");
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API Error: ${response.statusText} - ${errorText}`);
  }

  return response.json() as Promise<{ message: string; total_files: number; scan_id: string }>;
}

export async function fetchScanStatus(scanId: string, signal?: AbortSignal): Promise<ScanStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/scan/${scanId}/status`, { signal });
  if (!response.ok) {
    throw new Error("Failed to fetch scan status");
  }
  return response.json() as Promise<ScanStatusResponse>;
}
