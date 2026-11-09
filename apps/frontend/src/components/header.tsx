"use client";

import { motion } from "framer-motion";
import { ScanFace, Wifi, WifiOff } from "lucide-react";
import { AuthState } from "@/lib/types";
import { AuthButton } from "@/components/auth-button";

import { TranslationKey } from "@/lib/i18n";

interface HeaderProps {
  t: (key: TranslationKey) => string;
  authState: AuthState;
  onLogin: () => void;
  onLogout: () => void;
  isConnected?: boolean;
}

export function Header({ t, authState, onLogin, onLogout, isConnected = false }: HeaderProps) {
  return (
    <motion.header
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 80, damping: 20, delay: 0.1 }}
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-3 glass-panel bg-black/30 border-b border-white/5"
    >
      <motion.div
        className="flex items-center gap-3"
        whileHover={{ scale: 1.02 }}
        transition={{ type: "spring", stiffness: 400 }}
      >
        <div className="relative flex items-center justify-center p-2 rounded-xl bg-primary/10 border border-primary/20 glow-primary-sm">
          <ScanFace className="w-5 h-5 text-primary" />
          <motion.div
            className="absolute inset-0 rounded-xl bg-primary/20"
            animate={{ opacity: [0.3, 0.7, 0.3] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        </div>
        <span className="text-lg font-bold tracking-tight text-shimmer">
          Face Recon Drive
        </span>
      </motion.div>

      <div className="flex items-center gap-4">
        <motion.div
          className="hidden sm:flex items-center gap-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
        >
          {isConnected ? (
            <Wifi className="w-3.5 h-3.5 text-green-400" />
          ) : (
            <WifiOff className="w-3.5 h-3.5 text-white/30" />
          )}
          <span className="text-xs font-medium text-white/40 uppercase tracking-widest">
            {isConnected ? "Connected" : "Offline"}
          </span>
          <motion.div
            className={`h-1.5 w-1.5 rounded-full ${isConnected ? "bg-green-400" : "bg-red-500/50"}`}
            animate={isConnected ? { scale: [1, 1.5, 1], opacity: [1, 0.5, 1] } : {}}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
        </motion.div>

        <AuthButton authState={authState} onLogin={onLogin} onLogout={onLogout} t={t} />
      </div>
    </motion.header>
  );
}
