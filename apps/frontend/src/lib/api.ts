const API_URL = process.env.NEXT_PUBLIC_API_URL;

export class AuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthError";
  }
}

export async function fetchAuthUrl(): Promise<string> {
  const response = await fetch(`${API_URL}/api/v1/auth/google/url`);
  if (!response.ok) {
    throw new Error("Failed to fetch auth URL");
  }
  const data = await response.json() as { url: string; code_verifier: string };
  sessionStorage.setItem("oauth_code_verifier", data.code_verifier);
  return data.url;
}

export async function exchangeCode(code: string): Promise<{ access_token: string; email: string }> {
  const code_verifier = sessionStorage.getItem("oauth_code_verifier") ?? "";
  sessionStorage.removeItem("oauth_code_verifier");
  const response = await fetch(`${API_URL}/api/v1/auth/google/callback`, {
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
  const toBase64 = (file: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = (error) => reject(error);
    });

  const base64Image = await toBase64(targetFace);

  const response = await fetch(`${API_URL}/api/v1/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      drive_link: driveLink,
      target_face: base64Image.split(",")[1],
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

export async function fetchScanStatus(scanId: string): Promise<{ status: "running" | "completed"; remaining: number }> {
  const response = await fetch(`${API_URL}/api/v1/scan/${scanId}/status`);
  if (!response.ok) {
    throw new Error("Failed to fetch scan status");
  }
  return response.json();
}
