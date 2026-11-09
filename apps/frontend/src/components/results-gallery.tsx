"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Eye, Zap } from "lucide-react";
import { Card } from "@/components/ui/card";
import { ImageLightbox } from "@/components/image-lightbox";
import { TranslationKey } from "@/lib/i18n";

interface MatchResult {
  file_id: string;
  file_name: string;
  download_url: string;
}

interface ResultsGalleryProps {
  results: MatchResult[];
  t: (key: TranslationKey) => string;
  accessToken: string | null;
}

interface SelectedImage {
  fileId: string;
  fileName: string;
  downloadUrl: string;
}

export function ResultsGallery({ results, t, accessToken }: ResultsGalleryProps) {
  const [selected, setSelected] = useState<SelectedImage | null>(null);

  if (results.length === 0) return null;

  return (
    <>
      <div className="w-full max-w-5xl mx-auto mt-10 px-3 sm:px-4 pb-16">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-center gap-3 mb-8"
        >
          <div className="h-px flex-1 bg-gradient-to-r from-transparent to-primary/30" />
          <div className="flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/20">
            <Zap className="w-3.5 h-3.5 text-primary" />
            <span className="text-sm font-semibold text-white/80">
              {results.length} {results.length !== 1 ? t("matchesFoundPlural") : t("matchesFound")} {t("found")}
            </span>
          </div>
          <div className="h-px flex-1 bg-gradient-to-l from-transparent to-primary/30" />
        </motion.div>

        <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-5">
          <AnimatePresence>
            {results.map((result, index) => (
              <motion.div
                key={`${result.file_id}-${index}`}
                initial={{ opacity: 0, scale: 0.85, y: 40 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.85 }}
                transition={{
                  type: "spring",
                  stiffness: 120,
                  damping: 15,
                  delay: index * 0.06,
                }}
                layout
                whileHover={{ y: -4 }}
                onClick={() =>
                  setSelected({
                    fileId: result.file_id,
                    fileName: result.file_name,
                    downloadUrl: result.download_url,
                  })
                }
                className="cursor-pointer"
              >
                <Card className="overflow-hidden group border-white/8 bg-black/40 hover:border-primary/30 transition-all duration-500 hover:shadow-lg hover:shadow-primary/10">
                  <div className="relative aspect-square sm:aspect-[4/3] overflow-hidden bg-gradient-to-br from-gray-900 to-black">
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Eye className="w-10 h-10 sm:w-12 sm:h-12 text-white/10 group-hover:text-primary/40 transition-colors duration-500" />
                    </div>

                    <img
                      src={`${process.env.NEXT_PUBLIC_API_URL}/api/v1/drive/image/${result.file_id}?access_token=${accessToken}`}
                      alt={result.file_name}
                      className="absolute inset-0 w-full h-full object-cover transition-opacity duration-500"
                      loading="lazy"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.opacity = "0";
                      }}
                    />

                    <motion.div
                      className="absolute inset-0 bg-gradient-to-tr from-primary/10 to-purple-600/5 opacity-0 group-hover:opacity-100"
                      transition={{ duration: 0.4 }}
                    />

                    <motion.div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-center justify-center backdrop-blur-sm">
                      <span className="text-xs font-semibold text-white/80 bg-primary/20 px-3 py-1 rounded-full border border-primary/30">
                        {t("view")}
                      </span>
                    </motion.div>

                    <div className="absolute top-2 right-2">
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ delay: index * 0.06 + 0.3, type: "spring" }}
                        className="px-1.5 sm:px-2 py-0.5 rounded-full bg-green-500/20 border border-green-500/30 text-green-400 text-xs font-mono"
                      >
                        MATCH
                      </motion.div>
                    </div>
                  </div>

                  <div className="p-2.5 sm:p-4">
                    <h3
                      className="text-xs sm:text-sm font-medium truncate text-white/80 group-hover:text-white transition-colors"
                      title={result.file_name}
                    >
                      {result.file_name}
                    </h3>
                    <div className="mt-1.5 sm:mt-2 flex items-center justify-between">
                      <span className="text-xs text-white/25 font-mono hidden sm:block">
                        {result.file_id.slice(0, 8)}...
                      </span>
                      <div className="flex items-center gap-1">
                        <div className="w-1 h-1 rounded-full bg-green-400" />
                        <span className="text-xs text-green-400 font-mono">{t("confirmed")}</span>
                      </div>
                    </div>
                  </div>
                </Card>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>

      {selected && (
        <ImageLightbox
          fileId={selected.fileId}
          fileName={selected.fileName}
          onClose={() => setSelected(null)}
          t={t}
          accessToken={accessToken}
        />
      )}
    </>
  );
}
