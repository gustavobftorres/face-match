import { useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Search, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { HeroBanner } from "./components/hero-banner";
import { FolderPicker } from "./components/folder-picker";
import { SelfieUploader } from "./components/selfie-uploader";
import { SearchResultsPanel } from "./components/search-results-panel";
import { ImageDetailModal } from "./components/image-detail-modal";
import { IndexedFolder, FaceSearchMatch, SearchResponse } from "@/lib/types";
import { fetchPublicFolders, searchFacesPublic } from "@/lib/api";
import { fadeInUp } from "@/lib/animations";

export default function HomePage() {
  const prefersReducedMotion = useReducedMotion();
  const studioRef = useRef<HTMLElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const [folders, setFolders] = useState<IndexedFolder[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<IndexedFolder | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [activeModalImage, setActiveModalImage] = useState<FaceSearchMatch | null>(null);
  const [loadingFolders, setLoadingFolders] = useState(true);

  useEffect(() => {
    fetchPublicFolders()
      .then((data) => {
        setFolders(data);
        if (data.length > 0) {
          const firstReady = data.find((f) => f.status === "ready") || data[0];
          setSelectedFolder(firstReady);
        }
      })
      .catch(() => {
        setFolders([]);
      })
      .finally(() => {
        setLoadingFolders(false);
      });
  }, []);

  const scrollToStudio = () => {
    studioRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const handleFilePicked = (file: File | null) => {
    setSelectedFile(file);
    setSearchResponse(null);
    if (file) {
      setTimeout(() => {
        studioRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 100);
    }
  };

  const handleSearch = async () => {
    if (!selectedFolder) {
      toast.error("Selecione um álbum primeiro");
      return;
    }
    if (!selectedFile) {
      toast.error("Envie uma selfie primeiro");
      return;
    }

    setIsSearching(true);
    setSearchResponse(null);

    try {
      const result = await searchFacesPublic(selectedFolder.id, selectedFile);
      setSearchResponse(result);
      if (result.matches.length > 0) {
        toast.success(`${result.matches.length} foto(s) encontrada(s)`);
      } else {
        toast.info("Nenhuma foto correspondente encontrada");
      }
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 120);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Erro ao buscar fotos";
      toast.error(message);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <AppShell>
      <HeroBanner
        onQuickUpload={() => fileInputRef.current?.click()}
        onQuickCamera={() => cameraInputRef.current?.click()}
        onJumpToStudio={scrollToStudio}
      />

      <section id="studio" ref={studioRef} className="mx-auto max-w-6xl px-3.5 sm:px-6">
        <motion.div
          variants={prefersReducedMotion ? undefined : fadeInUp}
          initial={prefersReducedMotion ? false : "hidden"}
          animate="visible"
          className="rounded-[28px] sm:rounded-[32px] border border-[#211E1D]/10 bg-white shadow-[0_24px_70px_-30px_rgba(33,30,29,0.14)] overflow-hidden"
        >
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#211E1D]/8 bg-[#FCF9F2]/75 px-4 py-3.5 sm:px-7 sm:py-4">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <span className="text-xs font-medium uppercase tracking-wider text-[#6E675F] shrink-0">
                Álbuns
              </span>
              <div className="min-w-0 flex-1">
                <FolderPicker
                  folders={folders}
                  selectedFolderId={selectedFolder?.id || null}
                  onSelectFolder={(f) => {
                    setSelectedFolder(f);
                    setSearchResponse(null);
                  }}
                  isLoading={loadingFolders}
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12">
            <div className="lg:col-span-5 p-4 sm:p-7 border-b lg:border-b-0 lg:border-r border-[#211E1D]/8 bg-[#FCF9F2]/40 flex flex-col justify-between gap-5">
              <div className="space-y-4">
                <h2 className="text-sm sm:text-base font-medium text-[#211E1D]">
                  Sua selfie
                </h2>

                <SelfieUploader
                  selectedFile={selectedFile}
                  onFileSelected={handleFilePicked}
                  isSearching={isSearching}
                  fileInputRef={fileInputRef}
                  cameraInputRef={cameraInputRef}
                />
              </div>

              <Button
                type="button"
                variant={selectedFolder && selectedFile ? "orange" : "primary"}
                size="lg"
                onClick={handleSearch}
                disabled={!selectedFolder || !selectedFile || isSearching}
                className="w-full justify-between px-6"
              >
                {isSearching ? (
                  <span className="flex items-center justify-center w-full gap-2">
                    <span className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                    <span>Buscando...</span>
                  </span>
                ) : (
                  <>
                    <span className="flex items-center gap-2">
                      <Search className="h-4 w-4" />
                      <span>Buscar fotos</span>
                    </span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </Button>
            </div>

            <div ref={resultsRef} className="lg:col-span-7 p-4 sm:p-7 bg-white">
              <SearchResultsPanel
                isSearching={isSearching}
                searchResponse={searchResponse}
                onOpenImage={(match) => setActiveModalImage(match)}
              />
            </div>
          </div>
        </motion.div>
      </section>

      <ImageDetailModal
        match={activeModalImage}
        onClose={() => setActiveModalImage(null)}
      />
    </AppShell>
  );
}
