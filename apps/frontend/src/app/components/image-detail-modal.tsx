import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { X, Download, ExternalLink } from "lucide-react";
import { FaceSearchMatch } from "@/lib/types";
import { getDriveImageUrl } from "@/lib/api";
import { modalBackdrop, modalSheet } from "@/lib/animations";

interface ImageDetailModalProps {
  match: FaceSearchMatch | null;
  onClose: () => void;
}

export function ImageDetailModal({ match, onClose }: ImageDetailModalProps) {
  const prefersReducedMotion = useReducedMotion();
  const [previewLoaded, setPreviewLoaded] = useState(false);

  useEffect(() => {
    setPreviewLoaded(false);
  }, [match?.file_id]);

  useEffect(() => {
    if (!match) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [match, onClose]);

  const thumbUrl = match ? getDriveImageUrl(match.file_id, "thumb") : "";
  const previewUrl = match ? getDriveImageUrl(match.file_id, "preview") : "";
  const downloadUrl = match
    ? match.download_url || getDriveImageUrl(match.file_id, "full", true)
    : "";

  return (
    <AnimatePresence>
      {match && (
        <motion.div
          key="image-modal-backdrop"
          variants={prefersReducedMotion ? undefined : modalBackdrop}
          initial={prefersReducedMotion ? false : "hidden"}
          animate="visible"
          exit="exit"
          onClick={onClose}
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-[#211E1D]/65 backdrop-blur-xs sm:p-6"
        >
          <motion.div
            key="image-modal-sheet"
            variants={prefersReducedMotion ? undefined : modalSheet}
            initial={prefersReducedMotion ? false : "hidden"}
            animate="visible"
            exit="exit"
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-4xl rounded-t-3xl sm:rounded-3xl border border-[#211E1D]/12 bg-[#FCF9F2] shadow-2xl overflow-hidden flex flex-col max-h-[92dvh]"
          >
            <div className="flex items-center justify-between px-4 py-3.5 sm:px-6 border-b border-[#211E1D]/10 bg-white">
              <h3 className="text-sm sm:text-base font-medium text-[#211E1D] truncate max-w-[200px] sm:max-w-md">
                {match.file_name}
              </h3>

              <div className="flex items-center gap-2 shrink-0">
                <a
                  href={downloadUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 min-h-[38px] px-4 py-1.5 text-xs font-medium rounded-full bg-[#211E1D] text-[#FCF9F2] hover:bg-[#383331] transition-colors"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>Baixar</span>
                  <ExternalLink className="h-3 w-3 opacity-75 hidden sm:inline" />
                </a>
                <button
                  type="button"
                  onClick={onClose}
                  aria-label="Fechar"
                  className="inline-flex items-center justify-center h-9 w-9 rounded-full bg-[#F4EFE3] text-[#211E1D] hover:bg-[#EAE2D0] transition-colors cursor-pointer"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto bg-[#F4EFE3]/60 flex items-center justify-center p-3 sm:p-6 min-h-[260px]">
              <div className="relative flex items-center justify-center">
                {!previewLoaded && (
                  <img
                    src={thumbUrl}
                    alt={match.file_name}
                    className="max-h-[68dvh] w-auto max-w-full object-contain rounded-2xl shadow-sm border border-[#211E1D]/10 blur-[1px]"
                  />
                )}
                <img
                  src={previewUrl}
                  alt={match.file_name}
                  decoding="async"
                  onLoad={() => setPreviewLoaded(true)}
                  className={`max-h-[68dvh] w-auto max-w-full object-contain rounded-2xl shadow-sm border border-[#211E1D]/10 transition-opacity duration-200 ${
                    previewLoaded
                      ? "opacity-100"
                      : "absolute inset-0 opacity-0 pointer-events-none"
                  }`}
                />
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
