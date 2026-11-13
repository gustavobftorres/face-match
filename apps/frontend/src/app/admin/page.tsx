import { useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { AppShell } from "@/components/layout/app-shell";
import { Panel } from "@/components/ui/panel";
import { AdminStatsBar } from "./components/admin-stats-bar";
import { FolderIndexingForm } from "./components/folder-indexing-form";
import { IndexedFoldersTable } from "./components/indexed-folders-table";
import { IndexedFolder } from "@/lib/types";
import { fetchPublicFolders } from "@/lib/api";
import { fadeInUp } from "@/lib/animations";

export default function AdminPage() {
  const prefersReducedMotion = useReducedMotion();
  const [folders, setFolders] = useState<IndexedFolder[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const loadFolders = useCallback((silent = false) => {
    if (!silent) setIsLoading(true);
    fetchPublicFolders()
      .then((data) => setFolders(data))
      .catch(() => {
        if (!silent) setFolders([]);
      })
      .finally(() => {
        if (!silent) setIsLoading(false);
      });
  }, []);

  useEffect(() => {
    loadFolders();
  }, [loadFolders]);

  useEffect(() => {
    const hasIndexing = folders.some((folder) => folder.status === "indexing");
    if (!hasIndexing) return;
    const interval = setInterval(() => loadFolders(true), 4000);
    return () => clearInterval(interval);
  }, [folders, loadFolders]);

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-3.5 sm:px-6 pt-8 sm:pt-12 space-y-6 sm:space-y-8">
        <motion.div
          variants={prefersReducedMotion ? undefined : fadeInUp}
          initial={prefersReducedMotion ? false : "hidden"}
          animate="visible"
        >
          <h1 className="text-3xl sm:text-4xl font-medium tracking-[-0.03em] text-[#211E1D]">
            Gerenciar álbuns
          </h1>
        </motion.div>

        <AdminStatsBar folders={folders} />

        <div className="space-y-6">
          <Panel title="Indexar pasta" dotColor="#E6511A">
            <FolderIndexingForm onFolderIndexed={() => loadFolders()} />
          </Panel>

          <Panel title="Álbuns indexados" dotColor="#82C5B6">
            <IndexedFoldersTable
              folders={folders}
              isLoading={isLoading}
              onRefresh={() => loadFolders()}
            />
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}
