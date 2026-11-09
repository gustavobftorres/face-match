"use client";

import { motion, AnimatePresence } from "framer-motion";
import { LogIn, LogOut, User, Loader2 } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { AuthState } from "@/lib/types";
import { TranslationKey } from "@/lib/i18n";

interface AuthButtonProps {
  authState: AuthState;
  onLogin: () => void;
  onLogout: () => void;
  t: (key: TranslationKey) => string;
}

export function AuthButton({ authState, onLogin, onLogout, t }: AuthButtonProps) {
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    await onLogin();
  };

  return (
    <AnimatePresence mode="wait">
      {authState.isAuthenticated ? (
        <motion.div
          key="authenticated"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 20 }}
          transition={{ type: "spring", stiffness: 200, damping: 20 }}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl glass-panel border border-white/8 bg-black/30"
        >
          <div className="flex items-center gap-2 text-sm text-white/60">
            <div className="relative">
              <div className="p-1 rounded-lg bg-green-500/10 text-green-400">
                <User className="w-3.5 h-3.5" />
              </div>
              <div className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-green-400 border border-black" />
            </div>
            <span className="hidden sm:block max-w-[140px] truncate text-xs">{authState.userEmail}</span>
          </div>
          <motion.button
            onClick={onLogout}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center gap-1 text-xs text-white/30 hover:text-white/70 transition-colors px-1.5 py-1 rounded-lg hover:bg-white/5"
            title={t("signOut")}
          >
            <LogOut className="w-3 h-3" />
          </motion.button>
        </motion.div>
      ) : (
        <motion.div
          key="unauthenticated"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 20 }}
          transition={{ type: "spring", stiffness: 200, damping: 20 }}
        >
          <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
            <Button
              onClick={handleLogin}
              disabled={loading}
              className="flex items-center gap-2 text-sm bg-primary/15 hover:bg-primary/30 text-white border border-primary/25 backdrop-blur-sm glow-primary-sm"
            >
              {loading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <LogIn className="w-3.5 h-3.5" />
              )}
              <span>{t("signInWithGoogle")}</span>
            </Button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
