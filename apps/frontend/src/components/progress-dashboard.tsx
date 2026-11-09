"use client";

import { motion } from "framer-motion";
import { Activity, CheckCircle, AlertTriangle } from "lucide-react";
import { TranslationKey } from "@/lib/i18n";

interface ProgressDashboardProps {
  status: string;
  processed: number;
  total: number;
  currentFile: string;
  t: (key: TranslationKey) => string;
}

export function ProgressDashboard({ status, processed, total, currentFile, t }: ProgressDashboardProps) {
  const percentage = total > 0 ? (processed / total) * 100 : 0;

  const isError = status.toLowerCase().includes("error") || status.toLowerCase().includes("failed") || status.toLowerCase().includes("erro");
  const isMatch = status.toLowerCase().includes("match") || status.toLowerCase().includes("correspondência");
  const isProcessing = !isError && !isMatch && status !== t("idle");

  const statusColor = isError ? "text-red-400" : isMatch ? "text-green-400" : "text-primary";
  const barFrom = isError ? "#ef4444" : isMatch ? "#22c55e" : "#6366f1";
  const barTo = isError ? "#dc2626" : isMatch ? "#10b981" : "#a855f7";
  const borderColor = isError ? "border-red-500/20" : isMatch ? "border-green-500/20" : "border-white/8";

  const StatusIcon = isError ? AlertTriangle : isMatch ? CheckCircle : Activity;

  return (
    <motion.div
      initial={{ opacity: 0, y: 30, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 80, damping: 20 }}
      className="w-full max-w-2xl mx-auto mt-10 px-4"
    >
      <div className={`p-6 rounded-2xl glass-panel bg-black/50 border ${borderColor}`}>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2.5">
            <motion.div
              className={`p-1.5 rounded-lg ${isError ? "bg-red-500/10" : isMatch ? "bg-green-500/10" : "bg-primary/10"}`}
              animate={isProcessing ? { opacity: [1, 0.5, 1] } : {}}
              transition={{ duration: 1.5, repeat: Infinity }}
            >
              <StatusIcon className={`w-4 h-4 ${statusColor}`} />
            </motion.div>
            <h3 className="text-sm font-semibold text-white/60 uppercase tracking-widest">
              Neural Engine
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <span className={`text-xs font-mono ${statusColor}`}>{status}</span>
            {isProcessing && (
              <div className="flex gap-0.5">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-1 h-1 rounded-full bg-primary"
                    animate={{ opacity: [0.2, 1, 0.2], y: [0, -3, 0] }}
                    transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="relative h-2 w-full bg-white/5 rounded-full overflow-hidden mb-5">
          <motion.div
            className="absolute top-0 left-0 h-full rounded-full"
            style={{ background: `linear-gradient(90deg, ${barFrom}, ${barTo})` }}
            initial={{ width: 0 }}
            animate={{ width: `${percentage}%` }}
            transition={{ type: "spring", stiffness: 40, damping: 20 }}
          />
          <motion.div
            className="absolute top-0 right-0 h-full w-20 rounded-full"
            style={{ background: `linear-gradient(90deg, transparent, ${barTo}60)` }}
            animate={{ opacity: isProcessing ? [0, 0.5, 0] : 0 }}
            transition={{ duration: 1.5, repeat: Infinity }}
          />
        </div>

        <div className="flex items-center justify-between text-xs font-mono text-white/30">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="shrink-0">{t("current")}:</span>
            <span className="truncate text-white/50">{currentFile || "…"}</span>
          </div>
          <span className="shrink-0 ml-4 tabular-nums">
            {processed} <span className="text-white/20">/</span> {total}
          </span>
        </div>
      </div>
    </motion.div>
  );
}
