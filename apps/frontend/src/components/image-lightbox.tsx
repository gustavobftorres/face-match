"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Download, ExternalLink } from "lucide-react";
import { TranslationKey } from "@/lib/i18n";

interface ImageLightboxProps {
  fileId: string;
  fileName: string;
  onClose: () => void;
  t: (key: TranslationKey) => string;
  accessToken: string | null;
}

export function ImageLightbox({ fileId, fileName, onClose, t, accessToken }: ImageLightboxProps) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  const previewUrl = accessToken
    ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1/drive/image/${fileId}?access_token=${accessToken}`
    : `https://drive.google.com/thumbnail?id=${fileId}&sz=w1600`;

  const handleDownload = () => {
    if (!accessToken) return;
    fetch(`https://www.googleapis.com/drive/v3/files/${fileId}?alt=media`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = fileName;
        a.click();
        URL.revokeObjectURL(a.href);
      });
  };

  return (
    <AnimatePresence>
      <motion.div
        key="lightbox-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8"
        onClick={onClose}
      >
        <div className="absolute inset-0 bg-black/85 backdrop-blur-md" />

        <motion.div
          key="lightbox-panel"
          initial={{ opacity: 0, scale: 0.88, y: 24 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.88, y: 24 }}
          transition={{ type: "spring", stiffness: 260, damping: 26 }}
          className="relative z-10 w-full max-w-3xl flex flex-col rounded-2xl overflow-hidden border border-white/10 bg-black/60 shadow-2xl shadow-black/60"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/8 bg-black/40">
            <span className="text-sm font-medium text-white/70 truncate pr-4">{fileName}</span>
            <button
              onClick={onClose}
              className="shrink-0 w-7 h-7 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 flex items-center justify-center text-white/50 hover:text-white transition-all"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="relative w-full bg-black/80 flex items-center justify-center min-h-[240px] sm:min-h-[400px]">
            <img
              src={previewUrl}
              alt={fileName}
              className="max-w-full max-h-[60vh] object-contain"
              loading="eager"
            />
          </div>

          <div className="flex items-center gap-3 px-4 py-3 border-t border-white/8 bg-black/40">
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary/20 hover:bg-primary/35 border border-primary/30 text-primary text-sm font-medium transition-all"
            >
              <Download className="w-4 h-4" />
              {t("download")}
            </button>
            <button
              onClick={() => window.open(`https://drive.google.com/file/d/${fileId}/view`, "_blank")}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white/60 hover:text-white text-sm font-medium transition-all"
            >
              <ExternalLink className="w-4 h-4" />
              {t("openInDrive")}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
