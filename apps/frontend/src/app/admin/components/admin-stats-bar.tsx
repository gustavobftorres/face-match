import { motion, useReducedMotion } from "framer-motion";
import { IndexedFolder } from "@/lib/types";
import { fadeInUp } from "@/lib/animations";

interface AdminStatsBarProps {
  folders: IndexedFolder[];
}

export function AdminStatsBar({ folders }: AdminStatsBarProps) {
  const prefersReducedMotion = useReducedMotion();
  const totalPhotos = folders.reduce((sum, f) => sum + (f.photo_count || 0), 0);
  const totalFaces = folders.reduce((sum, f) => sum + (f.faces_count || 0), 0);

  const stats = [
    {
      label: "Álbuns",
      value: folders.length.toLocaleString("pt-BR"),
      dot: "#E6511A",
    },
    {
      label: "Fotos",
      value: totalPhotos.toLocaleString("pt-BR"),
      dot: "#F7B519",
    },
    {
      label: "Rostos",
      value: totalFaces.toLocaleString("pt-BR"),
      dot: "#82C5B6",
    },
  ];

  return (
    <motion.div
      variants={prefersReducedMotion ? undefined : fadeInUp}
      initial={prefersReducedMotion ? false : "hidden"}
      animate="visible"
      className="rounded-[24px] border border-[#211E1D]/10 bg-white grid grid-cols-3 divide-x divide-[#211E1D]/8"
    >
      {stats.map((stat) => (
        <div key={stat.label} className="px-4 py-4 sm:px-6 sm:py-5">
          <div className="flex items-center gap-2 text-xs text-[#6E675F]">
            <span
              className="h-2 w-2 rounded-full border border-[#211E1D]/20 shrink-0"
              style={{ backgroundColor: stat.dot }}
            />
            <span className="truncate">{stat.label}</span>
          </div>
          <p className="mt-1.5 text-xl sm:text-3xl font-medium tracking-[-0.03em] text-[#211E1D] tabular-nums">
            {stat.value}
          </p>
        </div>
      ))}
    </motion.div>
  );
}
