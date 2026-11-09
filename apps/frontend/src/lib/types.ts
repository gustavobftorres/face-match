export interface ScanProgress {
  type: "progress";
  file_id: string;
  file_name: string;
  status: "no_face_found" | "no_match" | "error";
}

export interface ScanMatch {
  type: "match";
  file_id: string;
  file_name: string;
  status: "match";
  download_url: string;
}

export interface ScanError {
  type: "error";
  file_id?: string;
  error: string;
}

export interface ScanStarted {
  type: "started";
  total_files: number;
}

export interface ScanTokenExpired {
  type: "token_expired";
  message: string;
}

export interface ScanCompleted {
  type: "completed";
  scan_id: string;
}

export type WebSocketMessage = ScanStarted | ScanProgress | ScanMatch | ScanError | ScanTokenExpired | ScanCompleted;

export interface ScanStatusResponse {
  scan_id: string;
  status: "running" | "completed";
  remaining: number;
}

export interface AuthState {
  accessToken: string | null;
  isAuthenticated: boolean;
  userEmail: string | null;
  expiresAt: number | null;
}
