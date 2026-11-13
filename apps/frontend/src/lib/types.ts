export interface IndexedFolder {
  id: string;
  name: string;
  drive_folder_id: string;
  photo_count: number;
  faces_count: number;
  status: "indexing" | "ready" | "failed";
  indexed_at: string;
}

export interface FaceSearchMatch {
  file_id: string;
  file_name: string;
  confidence: number;
  download_url?: string;
  thumbnail_url?: string;
}

export interface SearchResponse {
  folder_id: string;
  total_photos: number;
  matches: FaceSearchMatch[];
  elapsed_ms: number;
}

export interface ScanProgress {
  type: "progress";
  scan_id: string;
  sequence: number;
  file_id: string;
  file_name: string;
  status: "no_face_found" | "no_match" | "error";
}

export interface ScanMatch {
  type: "match";
  scan_id: string;
  sequence: number;
  file_id: string;
  file_name: string;
  status: "match";
  download_url: string;
}

export interface ScanFileError {
  type: "error";
  scan_id: string;
  sequence: number;
  status?: never;
  file_id: string;
  file_name: string;
  error: string;
}

export interface ScanFailed {
  type: "error";
  scan_id: string;
  sequence: number;
  status: "failed";
  error: string;
}

export type ScanError = ScanFileError | ScanFailed;

export interface ScanStarted {
  type: "started";
  scan_id: string;
  sequence: number;
  total_files: number;
}

export interface ScanTokenExpired {
  type: "token_expired";
  scan_id: string;
  sequence: number;
  message: string;
}

export interface ScanCompleted {
  type: "completed";
  scan_id: string;
  sequence: number;
}

export type WebSocketMessage =
  | ScanStarted
  | ScanProgress
  | ScanMatch
  | ScanError
  | ScanTokenExpired
  | ScanCompleted;

export type ScanStatusResponse =
  | { scan_id: string; status: "running"; remaining: number; last_sequence: number }
  | { scan_id: string; status: "completed"; remaining: number; last_sequence: number }
  | { scan_id: string; status: "token_expired"; remaining?: number; last_sequence: number }
  | { scan_id: string; status: "failed"; remaining: number; last_sequence: number }
  | { scan_id: string; status: "unknown"; last_sequence: number };

export interface AuthState {
  accessToken: string | null;
  isAuthenticated: boolean;
  userEmail: string | null;
  expiresAt: number | null;
}
