import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Download, ExternalLink } from "lucide-react";
import { FaceSearchMatch } from "@/lib/types";
import { getDriveImageUrl } from "@/lib/api";
import { DaisyMark } from "@/components/theme/theme-motifs";
import { springs, staggerFastContainer, staggerItem } from "@/lib/animations";

interface SearchResultsGridProps {
  matches: FaceSearchMatch[];
  onOpenImage: (match: FaceSearchMatch) => void;
}

function MatchPhotoCard({
  match,
  index,
  prefersReducedMotion,
  onOpenImage,
}: {
  match: FaceSearchMatch;
  index: number;
  prefersReducedMotion: boolean | null;
  onOpenImage: (match: FaceSearchMatch) => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const thumbUrl = getDriveImageUrl(match.file_id, "thumb");
  const downloadUrl = match.download_url || getDriveImageUrl(match.file_id, "full", true);

  return (
    <motion.div
      variants={prefersReducedMotion ? undefined : staggerItem}
      whileHover={prefersReducedMotion ? undefined : { y: -3 }}
      whileTap={prefersReducedMotion ? undefined : { scale: 0.98 }}
      transition={springs.snappy}
      className="group flex flex-col rounded-2xl border border-[#211E1D]/10 bg-[#FCF9F2] overflow-hidden hover:border-[#211E1D]/25 transition-colors"
    >
      <div
        className="relative aspect-4/3 w-full bg-[#F4EFE3] overflow-hidden cursor-pointer"
        onClick={() => onOpenImage(match)}
      >
        {!loaded && !failed && (
          <div className="absolute inset-0 bg-[#F4EFE3] animate-pulse" />
        )}
        {!failed && (
          <img
            src={thumbUrl}
            alt={match.file_name}
            loading={index < 9 ? "eager" : "lazy"}
            decoding="async"
            fetchPriority={index < 6 ? "high" : "auto"}
            onLoad={() => setLoaded(true)}
            onError={() => setFailed(true)}
            className={`h-full w-full object-cover transition-all duration-300 group-hover:scale-105 ${
              loaded ? "opacity-100" : "opacity-0"
            }`}
          />
        )}
      </div>

      <div className="flex items-center justify-between px-2.5 py-2 gap-1.5 bg-white">
        <span
          className="text-xs font-medium text-[#211E1D] truncate"
          title={match.file_name}
        >
          {match.file_name}
        </span>

        <div className="flex items-center gap-0.5 shrink-0">
          <button
            type="button"
            onClick={() => onOpenImage(match)}
            aria-label="Visualizar foto"
            className="inline-flex items-center justify-center h-8 w-8 sm:h-7 sm:w-7 rounded-full text-[#6E675F] hover:text-[#211E1D] hover:bg-[#F4EFE3] transition-colors cursor-pointer"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
          <a
            href={downloadUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center h-8 w-8 sm:h-7 sm:w-7 rounded-full text-[#6E675F] hover:text-[#E6511A] hover:bg-[#FDECE5] transition-colors"
            aria-label="Baixar foto"
          >
            <Download className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>
    </motion.div>
  );
}

export function SearchResultsGrid({
  matches,
  onOpenImage,
}: SearchResultsGridProps) {
  const prefersReducedMotion = useReducedMotion();

  if (matches.length === 0) {
    return (
      <motion.div
        initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={springs.snappy}
        className="rounded-2xl border border-[#211E1D]/10 bg-[#FCF9F2] p-8 sm:p-12 text-center"
      >
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-white border border-[#211E1D]/10 mb-3.5">
          <DaisyMark size={24} />
        </div>
        <h4 className="text-base font-medium text-[#211E1D]">
          Nenhuma foto encontrada
        </h4>
        <p className="mt-1.5 text-xs sm:text-sm text-[#6E675F] max-w-sm mx-auto">
          Tente outra foto com boa iluminação.
        </p>
      </motion.div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-[#211E1D]/8">
        <h3 className="text-sm sm:text-base font-medium text-[#211E1D]">
          {matches.length} {matches.length === 1 ? "foto encontrada" : "fotos encontradas"}
        </h3>
      </div>

      <motion.div
        variants={prefersReducedMotion ? undefined : staggerFastContainer}
        initial={prefersReducedMotion ? false : "hidden"}
        animate="visible"
        className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4"
      >
        {matches.map((match, index) => (
          <MatchPhotoCard
            key={match.file_id}
            match={match}
            index={index}
            prefersReducedMotion={prefersReducedMotion}
            onOpenImage={onOpenImage}
          />
        ))}
      </motion.div>
    </div>
  );
}
