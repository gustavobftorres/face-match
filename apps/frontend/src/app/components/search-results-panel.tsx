import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { FaceSearchMatch, SearchResponse } from "@/lib/types";
import { fadeInUp, springs } from "@/lib/animations";
import { DaisyMark } from "@/components/theme/theme-motifs";
import { SearchResultsGrid } from "./search-results-grid";

interface SearchResultsPanelProps {
  isSearching: boolean;
  searchResponse: SearchResponse | null;
  onOpenImage: (match: FaceSearchMatch) => void;
}

export function SearchResultsPanel({
  isSearching,
  searchResponse,
  onOpenImage,
}: SearchResultsPanelProps) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <AnimatePresence mode="wait">
      {isSearching ? (
        <motion.div
          key="searching-state"
          variants={prefersReducedMotion ? undefined : fadeInUp}
          initial={prefersReducedMotion ? false : "hidden"}
          animate="visible"
          exit="exit"
          className="space-y-4"
        >
          <div className="flex items-center justify-between border-b border-[#211E1D]/8 pb-3">
            <p className="text-sm font-medium text-[#211E1D]">
              Buscando suas fotos...
            </p>
            <span className="h-2.5 w-2.5 rounded-full bg-[#E6511A] animate-ping" />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 sm:gap-4">
            {[1, 2, 3, 4, 5, 6].map((item) => (
              <div
                key={item}
                className="aspect-4/3 rounded-2xl bg-[#F4EFE3] animate-pulse"
              />
            ))}
          </div>
        </motion.div>
      ) : searchResponse ? (
        <motion.div
          key="results-state"
          variants={prefersReducedMotion ? undefined : fadeInUp}
          initial={prefersReducedMotion ? false : "hidden"}
          animate="visible"
          exit="exit"
        >
          <SearchResultsGrid
            matches={searchResponse.matches}
            onOpenImage={onOpenImage}
          />
        </motion.div>
      ) : (
        <motion.div
          key="idle-state"
          variants={prefersReducedMotion ? undefined : fadeInUp}
          initial={prefersReducedMotion ? false : "hidden"}
          animate="visible"
          exit="exit"
          transition={springs.snappy}
          className="flex flex-col items-center justify-center min-h-[240px] py-8 text-center"
        >
          <div className="flex h-12 w-12 items-center justify-center rounded-full border border-[#211E1D]/10 bg-[#FCF9F2] mb-4">
            <DaisyMark size={24} />
          </div>
          <p className="text-sm text-[#6E675F]">
            As fotos encontradas aparecerão aqui.
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
