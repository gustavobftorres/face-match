"use client";

import { motion, AnimatePresence } from "framer-motion";
import { LockKeyhole, LogIn, X } from "lucide-react";
import { TranslationKey } from "@/lib/i18n";

interface SessionExpiredModalProps {
  t: (key: TranslationKey) => string;
  onLogin: () => void;
  onClose: () => void;
}

export function SessionExpiredModal({ t, onLogin, onClose }: SessionExpiredModalProps) {
  return (
    <AnimatePresence>
      <motion.div
        key="session-expired-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-[60] flex items-center justify-center p-6"
        onClick={onClose}
      >
        <div className="absolute inset-0 bg-black/80 backdrop-blur-md" />

        <motion.div
          key="session-expired-panel"
          initial={{ opacity: 0, scale: 0.88, y: 24 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.88, y: 24 }}
          transition={{ type: "spring", stiffness: 260, damping: 26 }}
          className="relative z-10 w-full max-w-sm flex flex-col items-center gap-6 p-8 rounded-3xl border border-white/10 bg-black/70 shadow-2xl shadow-black/60 text-center"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={onClose}
            className="absolute top-4 right-4 w-7 h-7 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 flex items-center justify-center text-white/40 hover:text-white transition-all"
          >
            <X className="w-4 h-4" />
          </button>

          <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/25 flex items-center justify-center">
            <LockKeyhole className="w-8 h-8 text-amber-400" />
          </div>

          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-white">{t("sessionExpiredTitle")}</h2>
            <p className="text-sm text-white/50 leading-relaxed">{t("sessionExpiredDesc")}</p>
          </div>

          <motion.button
            onClick={onLogin}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-primary hover:bg-primary/85 text-white font-semibold text-sm transition-colors glow-primary"
          >
            <LogIn className="w-4 h-4" />
            {t("signInAgain")}
          </motion.button>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
