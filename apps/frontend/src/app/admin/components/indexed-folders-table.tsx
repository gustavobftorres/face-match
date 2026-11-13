import { motion, useReducedMotion } from "framer-motion";
import { Clock, RefreshCw } from "lucide-react";
import { IndexedFolder } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { staggerFastContainer, staggerItem, springs } from "@/lib/animations";

interface IndexedFoldersTableProps {
  folders: IndexedFolder[];
  isLoading: boolean;
  onRefresh: () => void;
}

const folderDots = ["#E6511A", "#F7B519", "#BA78D3", "#82C5B6", "#F383AA"];

function statusBadgeVariant(status: IndexedFolder["status"]) {
  if (status === "ready") return "success";
  if (status === "failed") return "danger";
  return "warning";
}

function formatStatusLabel(status: IndexedFolder["status"]) {
  if (status === "ready") return "Pronto";
  if (status === "failed") return "Erro";
  return "Indexando";
}

export function IndexedFoldersTable({
  folders,
  isLoading,
  onRefresh,
}: IndexedFoldersTableProps) {
  const prefersReducedMotion = useReducedMotion();
  const hasIndexing = folders.some((f) => f.status === "indexing");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <h4 className="text-sm font-medium text-[#211E1D]">
            {folders.length} {folders.length === 1 ? "álbum" : "álbuns"}
          </h4>
          {hasIndexing && (
            <Badge variant="warning">
              <span className="h-1.5 w-1.5 rounded-full bg-[#E6511A] animate-ping" />
              <span>Sincronizando</span>
            </Badge>
          )}
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onRefresh}
          disabled={isLoading}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin" : ""}`} />
          <span>Atualizar</span>
        </Button>
      </div>

      {folders.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[#211E1D]/15 bg-[#FCF9F2] p-8 text-center text-xs sm:text-sm text-[#6E675F]">
          Nenhum álbum indexado.
        </div>
      ) : (
        <>
          <motion.div
            variants={prefersReducedMotion ? undefined : staggerFastContainer}
            initial={prefersReducedMotion ? false : "hidden"}
            animate="visible"
            className="md:hidden space-y-2.5"
          >
            {folders.map((folder, index) => {
              const dotColor = folderDots[index % folderDots.length];
              return (
                <motion.div
                  key={folder.id}
                  variants={prefersReducedMotion ? undefined : staggerItem}
                  transition={springs.snappy}
                  className="rounded-2xl border border-[#211E1D]/10 bg-[#FCF9F2] p-4 space-y-2.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span
                        className="h-2.5 w-2.5 rounded-full shrink-0 border border-[#211E1D]/20"
                        style={{ backgroundColor: dotColor }}
                      />
                      <div className="min-w-0">
                        <p className="font-medium text-sm text-[#211E1D] truncate">
                          {folder.name}
                        </p>
                        <p className="font-mono text-[11px] text-[#6E675F] truncate">
                          {folder.drive_folder_id}
                        </p>
                      </div>
                    </div>
                    <Badge variant={statusBadgeVariant(folder.status)}>
                      {formatStatusLabel(folder.status)}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-[#211E1D]/8 text-xs text-[#6E675F]">
                    <span className="font-mono tabular-nums text-[#211E1D]">
                      {folder.photo_count} fotos · {folder.faces_count} rostos
                    </span>
                    <span className="flex items-center gap-1 text-[11px]">
                      <Clock className="h-3 w-3" />
                      {new Date(folder.indexed_at).toLocaleDateString("pt-BR")}
                    </span>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>

          <div className="hidden md:block rounded-2xl border border-[#211E1D]/10 overflow-hidden bg-white">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#FCF9F2] text-[11px] font-medium text-[#6E675F] uppercase tracking-wider border-b border-[#211E1D]/8">
                  <tr>
                    <th className="px-4 py-3">Álbum</th>
                    <th className="px-4 py-3">ID da pasta</th>
                    <th className="px-4 py-3">Fotos</th>
                    <th className="px-4 py-3">Rostos</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Data</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#211E1D]/8">
                  {folders.map((folder, index) => {
                    const dotColor = folderDots[index % folderDots.length];
                    return (
                      <tr
                        key={folder.id}
                        className="hover:bg-[#FCF9F2]/75 transition-colors"
                      >
                        <td className="px-4 py-3.5 font-medium text-[#211E1D]">
                          <div className="flex items-center gap-2.5">
                            <span
                              className="h-2.5 w-2.5 rounded-full shrink-0 border border-[#211E1D]/20"
                              style={{ backgroundColor: dotColor }}
                            />
                            <span className="truncate max-w-xs">{folder.name}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-xs text-[#6E675F]">
                          <span className="rounded-full bg-[#FCF9F2] border border-[#211E1D]/10 px-2.5 py-0.5">
                            {folder.drive_folder_id}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-xs text-[#211E1D] tabular-nums">
                          {folder.photo_count}
                        </td>
                        <td className="px-4 py-3.5 font-mono text-xs text-[#211E1D] tabular-nums">
                          {folder.faces_count}
                        </td>
                        <td className="px-4 py-3.5">
                          <Badge variant={statusBadgeVariant(folder.status)}>
                            {formatStatusLabel(folder.status)}
                          </Badge>
                        </td>
                        <td className="px-4 py-3.5 text-xs text-[#6E675F] whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <Clock className="h-3.5 w-3.5" />
                            {new Date(folder.indexed_at).toLocaleDateString("pt-BR")}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
