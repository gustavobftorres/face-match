import React, { useState, useCallback, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { AnimatedBackground } from "@/components/animated-background";
import { CursorParticles } from "@/components/cursor-particles";
import { LandingView } from "@/components/landing-view";
import { DriveInput } from "@/components/drive-input";
import { AuthButton } from "@/components/auth-button";
import { ProgressDashboard } from "@/components/progress-dashboard";
import { ResultsGallery } from "@/components/results-gallery";
import { Hero } from "@/components/hero";
import { SessionExpiredModal } from "@/components/session-expired-modal";
import { useScanSocket } from "@/hooks/use-scan-socket";
import { useAuth } from "@/hooks/use-auth";
import { useLocale } from "@/hooks/use-locale";
import { startScan, AuthError, fetchScanStatus } from "@/lib/api";
import { ScanMatch, WebSocketMessage, AuthState } from "@/lib/types";
import { TranslationKey } from "@/lib/i18n";

export default function Home() {
  const { authState, login, logout } = useAuth();
  const { t } = useLocale();
  const loginRef = useRef(login);
  useEffect(() => { loginRef.current = login; }, [login]);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [driveLink, setDriveLink] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState(t("idle"));
  const [processedCount, setProcessedCount] = useState(0);
  const [totalFiles, setTotalFiles] = useState(0);
  const [currentFile, setCurrentFile] = useState("");
  const [matches, setMatches] = useState<ScanMatch[]>([]);
  const [showSessionExpired, setShowSessionExpired] = useState(false);
  const [currentScanId, setCurrentScanId] = useState<string | null>(null);
  const currentScanIdRef = useRef<string | null>(null);
  const terminalScanIdRef = useRef<string | null>(null);
  const lastSequenceByScanRef = useRef<Map<string, number>>(new Map());
  const consumedFileResultsRef = useRef<Set<string>>(new Set());
  const connectionInFlightRef = useRef(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  const disconnectRef = useRef<() => void>(() => {});

  const completeScan = useCallback((scanId: string) => {
    if (currentScanIdRef.current !== scanId || terminalScanIdRef.current === scanId) return;
    terminalScanIdRef.current = scanId;
    setScanStatus(t("scanComplete"));
    setIsScanning(false);
    disconnectRef.current();
    toast.success(t("scanComplete"), { duration: 3000 });
  }, [t]);

  const expireScan = useCallback((scanId: string) => {
    if (currentScanIdRef.current !== scanId || terminalScanIdRef.current === scanId) return;
    terminalScanIdRef.current = scanId;
    setScanStatus(t("sessionExpiredTitle"));
    setIsScanning(false);
    disconnectRef.current();
    setShowSessionExpired(true);
    toast.error(t("sessionExpiredToast"), { duration: 4000 });
  }, [t]);

  const failScan = useCallback((scanId: string, error?: string) => {
    if (currentScanIdRef.current !== scanId || terminalScanIdRef.current === scanId) return;
    terminalScanIdRef.current = scanId;
    const message = error ?? t("scanFailed");
    setScanStatus(`${t("errorPrefix")} ${message}`);
    setIsScanning(false);
    disconnectRef.current();
    toast.error(message);
  }, [t]);

  const handleSocketMessage = useCallback((message: WebSocketMessage) => {
    if (
      message.scan_id !== currentScanIdRef.current ||
      terminalScanIdRef.current === message.scan_id
    ) return;
    const lastSequence = lastSequenceByScanRef.current.get(message.scan_id) ?? 0;
    if (message.sequence <= lastSequence) return;
    lastSequenceByScanRef.current.set(message.scan_id, message.sequence);

    if (message.type === "started") {
      setTotalFiles(message.total_files);
      setScanStatus(t("connected"));
    } else if (message.type === "progress") {
      const resultKey = `${message.file_id}\u0000${message.status}`;
      if (consumedFileResultsRef.current.has(resultKey)) return;
      consumedFileResultsRef.current.add(resultKey);
      const label = message.status === "no_face_found" ? t("noFace") : t("noMatch");
      setScanStatus(`${label}: ${message.file_name}`);
      setProcessedCount((prev) => prev + 1);
      setCurrentFile(message.file_name);
    } else if (message.type === "match") {
      const resultKey = `${message.file_id}\u0000${message.status}`;
      if (consumedFileResultsRef.current.has(resultKey)) return;
      consumedFileResultsRef.current.add(resultKey);
      setMatches((prev) => [...prev, message]);
      setProcessedCount((prev) => prev + 1);
      setCurrentFile(message.file_name);
      setScanStatus(`${t("matchFoundStatus")} ${message.file_name}`);
      toast.success(`${t("matchFound")} ${message.file_name}`);
    } else if (message.type === "error") {
      if (message.status === "failed") {
        failScan(message.scan_id, message.error);
      } else {
        setScanStatus(`${t("errorPrefix")} ${message.error}`);
        toast.error(message.error);
      }
    } else if (message.type === "token_expired") {
      expireScan(message.scan_id);
    } else if (message.type === "completed") {
      completeScan(message.scan_id);
    }
  }, [completeScan, expireScan, failScan, t]);

  const { isConnected, error: wsError, connect, disconnect } = useScanSocket(
    import.meta.env.VITE_WS_URL,
    handleSocketMessage
  );
  const isConnectedRef = useRef(isConnected);
  useEffect(() => { isConnectedRef.current = isConnected; }, [isConnected]);
  useEffect(() => { disconnectRef.current = disconnect; }, [disconnect]);

  useEffect(() => {
    if (wsError) {
      toast.error(wsError);
      // Once POST has started a scan, polling remains the lifecycle fallback.
      if (!currentScanId) setTimeout(() => setIsScanning(false), 0);
    }
  }, [wsError, currentScanId]);

  const handleStartScan = async () => {
    if (!selectedFile || !driveLink || !authState.accessToken) {
      toast.error(t("missingInputs"));
      return;
    }
    setIsScanning(true);
    setScanStatus(t("connecting"));
    setMatches([]);
    setProcessedCount(0);
    setTotalFiles(0);
    setCurrentFile("");
    setCurrentScanId(null);
    currentScanIdRef.current = null;
    terminalScanIdRef.current = null;
    lastSequenceByScanRef.current.clear();
    consumedFileResultsRef.current.clear();
    connectionInFlightRef.current = false;
    setReconnectAttempt(0);

    try {
      setScanStatus(t("initializing"));
      const response = await startScan(driveLink, selectedFile, authState.accessToken);
      setTotalFiles(response.total_files);
      setCurrentScanId(response.scan_id);
      currentScanIdRef.current = response.scan_id;
      lastSequenceByScanRef.current.set(response.scan_id, 0);
      setScanStatus(t("connected"));
      toast.info(`${t("scanStarted")} ${response.total_files} ${t("filesToProcess")}`);

      // The scan exists only after POST returns its ID. The scoped socket replays
      // from sequence zero, while polling independently reconciles lifecycle state.
      connectionInFlightRef.current = true;
      try {
        await connect(response.scan_id, 0);
      } catch (err) {
        console.error("WebSocket connection error; continuing with status polling", err);
        if (
          currentScanIdRef.current === response.scan_id &&
          terminalScanIdRef.current !== response.scan_id
        ) setScanStatus(t("connecting"));
      } finally {
        connectionInFlightRef.current = false;
        setReconnectAttempt((attempt) => attempt + 1);
      }
    } catch (err) {
      if (err instanceof AuthError) {
        setScanStatus(t("sessionExpiredTitle"));
        toast.error(t("sessionExpiredToast"), { duration: 4000 });
        logout();
        setIsScanning(false);
        disconnect();
        setShowSessionExpired(true);
      } else {
        console.error(err);
        setScanStatus(t("errorPrefix"));
        toast.error(t("scanFailed"));
        setIsScanning(false);
        disconnect();
      }
    }
  };

  useEffect(() => {
    if (
      !isScanning ||
      !currentScanId ||
      isConnected ||
      connectionInFlightRef.current ||
      terminalScanIdRef.current === currentScanId
    ) return;

    const scanId = currentScanId;
    const timeout = setTimeout(() => {
      if (
        currentScanIdRef.current !== scanId ||
        terminalScanIdRef.current === scanId ||
        connectionInFlightRef.current
      ) return;

      connectionInFlightRef.current = true;
      const afterSequence = lastSequenceByScanRef.current.get(scanId) ?? 0;
      void connect(scanId, afterSequence)
        .catch((err) => console.error("WebSocket reconnect error; polling remains active", err))
        .finally(() => {
          connectionInFlightRef.current = false;
          setReconnectAttempt((attempt) => attempt + 1);
        });
    }, 3000);

    return () => clearTimeout(timeout);
  }, [connect, currentScanId, isConnected, isScanning, reconnectAttempt]);

  useEffect(() => {
    if (!isScanning || !currentScanId) return;

    const scanId = currentScanId;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const isCurrent = () =>
      !controller.signal.aborted &&
      currentScanIdRef.current === scanId &&
      terminalScanIdRef.current !== scanId;
    const scheduleNext = () => {
      if (isCurrent()) timeout = setTimeout(() => void poll(), 3000);
    };
    const poll = async () => {
      try {
        const res = await fetchScanStatus(scanId, controller.signal);
        if (!isCurrent()) return;
        if (res.scan_id !== scanId) {
          scheduleNext();
          return;
        }

        if (
          res.status === "completed" ||
          res.status === "token_expired" ||
          res.status === "failed"
        ) {
          const localSequence = lastSequenceByScanRef.current.get(scanId) ?? 0;
          if (localSequence >= res.last_sequence) {
            if (res.status === "completed") completeScan(scanId);
            else if (res.status === "token_expired") expireScan(scanId);
            else failScan(scanId);
          } else {
            // A terminal status is only a replay barrier. Keep the socket alive
            // (or reconnecting) until every persisted event, including the ordered
            // terminal event, has advanced the local cursor to last_sequence.
            if (!isConnectedRef.current && isCurrent()) setScanStatus(t("connecting"));
            scheduleNext();
          }
        } else if (res.status === "unknown") {
          failScan(scanId);
        } else {
          // Polling remains lifecycle-only; file results are recovered by the
          // WebSocket replay cursor without allowing polling to duplicate them.
          if (!isConnectedRef.current && isCurrent()) {
            setScanStatus(`${t("connecting")}... (${res.remaining} ${t("filesToProcess")})`);
          }
          scheduleNext();
        }
      } catch (err) {
        if (controller.signal.aborted || !isCurrent()) return;
        console.error("Polling error", err);
        scheduleNext();
      }
    };

    void poll();
    return () => {
      controller.abort();
      if (timeout) clearTimeout(timeout);
    };
  }, [completeScan, currentScanId, expireScan, failScan, isScanning, t]);

  const handleSessionExpiredLogin = useCallback(() => {
    setShowSessionExpired(false);
    loginRef.current();
  }, []);

  const showDashboard = isScanning || matches.length > 0 || processedCount > 0;

  return (
    <main className="relative min-h-screen text-white overflow-x-hidden selection:bg-primary/30">
      <CursorParticles />
      <AnimatedBackground />

      <div className="relative z-10 flex flex-col items-center min-h-screen px-4">
        <AnimatePresence mode="wait">
          {!authState.isAuthenticated ? (
            <LandingView key="landing" t={t} onLogin={login} />
          ) : (
            <ScanView
              key="scan"
              t={t}
              authState={authState}
              onLogout={logout}
              selectedFile={selectedFile}
              onFileSelect={setSelectedFile}
              driveLink={driveLink}
              onDriveLinkChange={setDriveLink}
              onSubmit={handleStartScan}
              isScanning={isScanning}
              showDashboard={showDashboard}
              wsError={wsError}
              scanStatus={scanStatus}
              processedCount={processedCount}
              totalFiles={totalFiles}
              currentFile={currentFile}
              matches={matches}
            />
          )}
        </AnimatePresence>
      </div>

      {showSessionExpired && (
        <SessionExpiredModal
          t={t}
          onLogin={handleSessionExpiredLogin}
          onClose={() => setShowSessionExpired(false)}
        />
      )}
    </main>
  );
}

interface ScanViewProps {
  t: (key: TranslationKey) => string;
  authState: AuthState;
  onLogout: () => void;
  selectedFile: File | null;
  onFileSelect: (f: File | null) => void;
  driveLink: string;
  onDriveLinkChange: (v: string) => void;
  onSubmit: () => void;
  isScanning: boolean;
  showDashboard: boolean;
  wsError: string | null;
  scanStatus: string;
  processedCount: number;
  totalFiles: number;
  currentFile: string;
  matches: ScanMatch[];
}

function ScanView({
  t, authState, onLogout, selectedFile, onFileSelect,
  driveLink, onDriveLinkChange, onSubmit, isScanning,
  showDashboard, wsError, scanStatus, processedCount,
  totalFiles, currentFile, matches,
}: ScanViewProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="flex flex-col items-center w-full py-10 sm:py-16"
    >
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mb-6 sm:mb-8 text-center"
      >
        <div className="flex justify-center mb-1">
          <img src="/logo.png?v=2" alt="Drive Face Match" width={160} height={160} className="w-28 sm:w-36 h-auto" />
        </div>
        <p className="text-xs text-white/30">
          {t("signedInAs")} <span className="text-white/60">{authState.userEmail}</span>
        </p>
      </motion.div>

      <div className="w-full max-w-md px-3 sm:px-0 space-y-3">
        <StepCard step={1} label={t("selectFacePhoto")} done={!!selectedFile}>
          <Hero selectedFile={selectedFile} onFileSelect={onFileSelect} t={t} />
        </StepCard>

        <StepCard step={2} label={t("pasteDriveUrl")} done={!!driveLink}>
          <DriveInput
            value={driveLink}
            onChange={onDriveLinkChange}
            onSubmit={onSubmit}
            isLoading={isScanning}
            isAuthenticated={authState.isAuthenticated}
            t={t}
          />
        </StepCard>
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="mt-6"
      >
        <AuthButton
          authState={authState}
          onLogin={() => {}}
          onLogout={onLogout}
          t={t}
        />
      </motion.div>

      <AnimatePresence>
        {showDashboard && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 30 }}
            className="w-full max-w-xl mt-8 px-3 sm:px-0"
          >
            <ProgressDashboard
              status={wsError ? t("connectionError") : scanStatus}
              processed={processedCount}
              total={totalFiles}
              currentFile={currentFile}
              t={t}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <ResultsGallery results={matches} t={t} accessToken={authState.accessToken} />
    </motion.div>
  );
}

function StepCard({
  step, label, done, children,
}: {
  step: number;
  label: string;
  done: boolean;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: step * 0.1 }}
      className="relative"
    >
      <div className="flex items-center gap-3 mb-2 px-1">
        <motion.div
          className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors duration-300 ${
            done ? "bg-green-500/20 text-green-400 border border-green-500/30" : "bg-primary/15 text-primary border border-primary/25"
          }`}
          animate={done ? { scale: [1, 1.2, 1] } : {}}
          transition={{ duration: 0.3 }}
        >
          {done ? "✓" : step}
        </motion.div>
        <span className={`text-xs font-medium transition-colors duration-300 ${done ? "text-green-400/80" : "text-white/40"}`}>
          {label}
        </span>
      </div>
      {children}
    </motion.div>
  );
}
