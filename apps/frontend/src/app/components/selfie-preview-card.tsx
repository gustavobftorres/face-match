import { motion, useReducedMotion } from "framer-motion";
import { X, Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { scaleInPop } from "@/lib/animations";

interface SelfiePreviewCardProps {
  previewUrl: string;
  file: File;
  isSearching?: boolean;
  onClear: () => void;
}

export function SelfiePreviewCard({
  previewUrl,
  file,
  isSearching,
  onClear,
}: SelfiePreviewCardProps) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <motion.div
      key="preview"
      variants={prefersReducedMotion ? undefined : scaleInPop}
      initial={prefersReducedMotion ? false : "hidden"}
      animate="visible"
      exit="exit"
      className="relative flex items-center justify-between gap-3 p-3.5 rounded-2xl border border-[#211E1D]/12 bg-white shadow-2xs"
    >
      <div className="flex items-center gap-3.5 min-w-0">
        <div className="relative h-16 w-16 shrink-0 rounded-2xl overflow-hidden border border-[#211E1D]/12 bg-[#F4EFE3]">
          <img
            src={previewUrl}
            alt="Selfie selecionada"
            className="h-full w-full object-cover"
          />
          {isSearching && !prefersReducedMotion && (
            <motion.div
              initial={{ y: "-100%" }}
              animate={{ y: "220%" }}
              transition={{
                repeat: Infinity,
                duration: 1.2,
                ease: "easeInOut",
                repeatType: "reverse",
              }}
              className="absolute inset-x-0 h-5 bg-gradient-to-b from-transparent via-[#F7B519]/80 to-transparent"
            />
          )}
        </div>

        <div className="min-w-0">
          <div className="mb-1">
            <Badge variant={isSearching ? "warning" : "success"}>
              {!isSearching && <Check className="h-3 w-3" />}
              <span>{isSearching ? "Buscando..." : "Foto pronta"}</span>
            </Badge>
          </div>
          <p className="text-sm font-medium text-[#211E1D] truncate">{file.name}</p>
        </div>
      </div>

      <button
        type="button"
        onClick={onClear}
        disabled={isSearching}
        aria-label="Remover foto"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#6E675F] hover:text-[#211E1D] hover:bg-[#F4EFE3] transition-colors disabled:opacity-40 cursor-pointer"
      >
        <X className="h-4 w-4" />
      </button>
    </motion.div>
  );
}
