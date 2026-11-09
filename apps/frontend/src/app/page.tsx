"use client";

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

  const disconnectRef = useRef<() => void>(() => {});

  const handleSocketMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === "started") {
      setTotalFiles(message.total_files);
      setScanStatus(t("connected"));
    } else if (message.type === "progress") {
      const label = message.status === "no_face_found" ? t("noFace") : t("noMatch");
      setScanStatus(`${label}: ${message.file_name}`);
      setProcessedCount((prev) => prev + 1);
      setCurrentFile(message.file_name);
    } else if (message.type === "match") {
      setMatches((prev) => [...prev, message]);
      setProcessedCount((prev) => prev + 1);
      setCurrentFile(message.file_name);
      setScanStatus(`${t("matchFoundStatus")} ${message.file_name}`);
      toast.success(`${t("matchFound")} ${message.file_name}`);
    } else if (message.type === "error") {
      setScanStatus(`${t("errorPrefix")} ${message.error}`);
      toast.error(message.error);
    } else if (message.type === "token_expired") {
      setScanStatus(t("sessionExpiredTitle"));
      toast.error(t("sessionExpiredToast"), { duration: 4000 });
      setTimeout(() => {
        setIsScanning(false);
        disconnectRef.current();
        setShowSessionExpired(true);
      }, 500);
    } else if (message.type === "completed") {
      setScanStatus(t("scanComplete"));
      setTimeout(() => {
        setIsScanning(false);
        disconnectRef.current();
      }, 0);
      toast.success(t("scanComplete"), { duration: 3000 });
    }
  }, [t]);

  const { isConnected, error: wsError, connect, disconnect } = useScanSocket(
    process.env.NEXT_PUBLIC_WS_URL,
    handleSocketMessage
  );
  useEffect(() => { disconnectRef.current = disconnect; }, [disconnect]);

  useEffect(() => {
    if (wsError) {
      toast.error(wsError);
      setTimeout(() => setIsScanning(false), 0);
    }
  }, [wsError]);

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

    try {
      await connect();
      setScanStatus(t("initializing"));
      const response = await startScan(driveLink, selectedFile, authState.accessToken);
      setTotalFiles(response.total_files);
      setCurrentScanId(response.scan_id);
      setScanStatus(t("connected"));
      toast.info(`${t("scanStarted")} ${response.total_files} ${t("filesToProcess")}`);
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
    let interval: ReturnType<typeof setInterval>;
    if (isScanning && !isConnected && currentScanId) {
      interval = setInterval(async () => {
        try {
          const res = await fetchScanStatus(currentScanId);
          if (res.status === "completed") {
            setScanStatus(t("scanComplete"));
            setTimeout(() => {
              setIsScanning(false);
              disconnectRef.current();
            }, 0);
            toast.success(t("scanComplete"), { duration: 3000 });
            clearInterval(interval);
          } else {
            setScanStatus(`${t("connecting")}... (${res.remaining} ${t("filesToProcess")})`);
          }
        } catch (err) {
          console.error("Polling error", err);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [isScanning, isConnected, currentScanId, t]);

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
