"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Link2, ArrowRight, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { TranslationKey } from "@/lib/i18n";

interface DriveInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
  isAuthenticated: boolean;
  t: (key: TranslationKey) => string;
}

export function DriveInput({ value, onChange, onSubmit, isLoading, isAuthenticated, t }: DriveInputProps) {
  const canSubmit = !!(value && isAuthenticated && !isLoading);

  return (
    <div className="w-full space-y-2">
      <div className="relative group">
        <AnimatedGlow active={canSubmit} />

        <div className="relative flex items-center p-1.5 rounded-2xl glass-panel bg-black/50 border border-white/8">
          <div className="flex-shrink-0 pl-3 pr-2 text-white/25">
            <Link2 className="w-4 h-4" />
          </div>

          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && canSubmit && onSubmit()}
            placeholder={
              !isAuthenticated ? `${t("signInWithGoogle")}...` : t("driveUrlPlaceholder")
            }
            disabled={!isAuthenticated}
            className="border-none bg-transparent shadow-none focus-visible:ring-0 h-10 text-sm text-white/80 placeholder:text-white/20 disabled:opacity-40 disabled:cursor-not-allowed"
          />

          <motion.div whileHover={canSubmit ? { scale: 1.04 } : {}} whileTap={canSubmit ? { scale: 0.96 } : {}}>
            <Button
              onClick={onSubmit}
              disabled={!canSubmit}
              className={`ml-1 shrink-0 h-9 px-4 text-sm font-medium transition-all duration-300 rounded-xl ${
                canSubmit
                  ? "bg-primary hover:bg-primary/80 text-white glow-primary-sm border-primary/40"
                  : "bg-white/5 text-white/20 border-white/5"
              }`}
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <span className="flex items-center gap-1.5">
                  {t("scan")}
                  <ArrowRight className="w-3.5 h-3.5" />
                </span>
              )}
            </Button>
          </motion.div>
        </div>
      </div>
    </div>
  );
}

function AnimatedGlow({ active }: { active: boolean }) {
  return (
    <motion.div
      className="absolute -inset-1 rounded-2xl bg-gradient-to-r from-primary/50 via-purple-500/30 to-primary/50 blur-lg pointer-events-none"
      animate={{ opacity: active ? [0.4, 0.8, 0.4] : 0 }}
      transition={{ duration: 2, repeat: Infinity }}
    />
  );
}
