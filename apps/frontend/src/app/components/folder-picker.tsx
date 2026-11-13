import { motion, useReducedMotion } from "framer-motion";
import { Check, Folder, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { IndexedFolder } from "@/lib/types";
import { springs } from "@/lib/animations";

interface FolderPickerProps {
  folders: IndexedFolder[];
  selectedFolderId: string | null;
  onSelectFolder: (folder: IndexedFolder) => void;
  isLoading?: boolean;
}

const albumDots = ["#E6511A", "#F7B519", "#BA78D3", "#82C5B6", "#F383AA"];

export function FolderPicker({
  folders,
  selectedFolderId,
  onSelectFolder,
  isLoading,
}: FolderPickerProps) {
  const prefersReducedMotion = useReducedMotion();

  if (isLoading) {
    return (
      <div className="flex gap-2.5 overflow-x-auto no-scrollbar py-1">
        {[1, 2].map((i) => (
          <div
            key={i}
            className="h-11 w-48 shrink-0 rounded-full bg-[#F4EFE3] animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (folders.length === 0) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-dashed border-[#211E1D]/15 bg-[#FCF9F2] px-4 py-3 text-xs sm:text-sm">
        <div className="flex items-center gap-2 text-[#6E675F]">
          <Folder className="h-4 w-4 text-[#E6511A]" />
          <span>Nenhum álbum disponível.</span>
        </div>
        <Link
          to="/admin"
          className="inline-flex items-center gap-1 rounded-full bg-[#211E1D] px-3.5 py-1.5 text-xs font-medium text-[#FCF9F2] hover:bg-[#383331] transition-colors"
        >
          <span>Indexar álbum</span>
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2.5 overflow-x-auto no-scrollbar snap-x snap-mandatory py-1">
      {folders.map((folder, index) => {
        const isSelected = folder.id === selectedFolderId;
        const dotColor = albumDots[index % albumDots.length];

        return (
          <motion.button
            key={folder.id}
            type="button"
            whileTap={prefersReducedMotion ? undefined : { scale: 0.97 }}
            transition={springs.buttonPress}
            onClick={() => onSelectFolder(folder)}
            className={`relative snap-start shrink-0 inline-flex items-center gap-2.5 min-h-[42px] px-4 py-2 rounded-full border text-left transition-colors cursor-pointer ${
              isSelected
                ? "border-[#211E1D] bg-[#211E1D] text-[#FCF9F2]"
                : "border-[#211E1D]/12 bg-[#FCF9F2] text-[#211E1D] hover:bg-[#F4EFE3]"
            }`}
          >
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0 border border-[#211E1D]/20"
              style={{ backgroundColor: dotColor }}
            />
            <span className="text-xs sm:text-sm font-medium whitespace-nowrap">
              {folder.name}
            </span>
            {isSelected && (
              <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-[#F7B519] text-[#211E1D]">
                <Check className="h-2.5 w-2.5 stroke-[3]" />
              </span>
            )}
          </motion.button>
        );
      })}
    </div>
  );
}
