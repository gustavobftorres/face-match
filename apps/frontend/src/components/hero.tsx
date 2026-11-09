"use client";

import * as React from "react";
import Image from "next/image";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, X, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { TranslationKey } from "@/lib/i18n";

interface HeroProps {
  onFileSelect: (file: File | null) => void;
  selectedFile: File | null;
  t: (key: TranslationKey) => string;
}

export function Hero({ onFileSelect, selectedFile, t }: HeroProps) {
  const [dragActive, setDragActive] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [preview, setPreview] = React.useState<string | null>(null);
  const [scanning, setScanning] = React.useState(false);

  React.useEffect(() => {
    if (selectedFile) {
      const url = URL.createObjectURL(selectedFile);
      setPreview(url);
      setScanning(true);
      const timeout = setTimeout(() => setScanning(false), 2000);
      return () => {
        URL.revokeObjectURL(url);
        clearTimeout(timeout);
      };
    } else {
      setPreview(null);
      setScanning(false);
    }
  }, [selectedFile]);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) onFileSelect(e.dataTransfer.files[0]);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) onFileSelect(e.target.files[0]);
  };

  return (
    <div className="w-full">
      <motion.div
        layout
        className="relative group cursor-pointer"
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.99 }}
        onClick={() => inputRef.current?.click()}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept="image/*"
          onChange={handleChange}
        />

        <AnimatePresence>
          {(dragActive || selectedFile) && (
            <motion.div
              className="absolute -inset-1 rounded-2xl bg-primary/20 blur-xl"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            />
          )}
        </AnimatePresence>

        <div
          className={cn(
            "relative flex items-center gap-4 p-4 rounded-2xl border-2 border-dashed transition-all duration-300",
            "glass-panel bg-black/40",
            dragActive ? "border-primary/70 bg-primary/5" : "border-white/10 hover:border-white/20",
            selectedFile ? "border-solid border-primary/30" : "",
            scanning ? "scan-card" : ""
          )}
        >
          <AnimatePresence mode="wait">
            {preview ? (
              <motion.div
                key="preview"
                initial={{ opacity: 0, scale: 0.85, rotateY: 90 }}
                animate={{ opacity: 1, scale: 1, rotateY: 0 }}
                exit={{ opacity: 0, scale: 0.85 }}
                transition={{ type: "spring", stiffness: 120 }}
                className="relative shrink-0"
              >
                <div className="relative w-16 h-16 rounded-xl overflow-hidden border-2 border-primary/20">
                  <Image src={preview} alt="Target" fill className="object-cover" />
                  <div className="absolute inset-0 bg-gradient-to-t from-primary/20 to-transparent" />
                </div>

                <AnimatePresence>
                  {scanning && (
                    <motion.div
                      className="absolute inset-0 rounded-xl border-2 border-primary/60"
                      animate={{ scale: [1, 1.6], opacity: [0.8, 0] }}
                      transition={{ duration: 1.2, repeat: 2 }}
                    />
                  )}
                </AnimatePresence>

                <button
                  onClick={(e) => { e.stopPropagation(); onFileSelect(null); }}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-black/80 border border-white/20 flex items-center justify-center text-white/60 hover:text-white transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="w-16 h-16 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center shrink-0 group-hover:bg-primary/10 group-hover:border-primary/20 transition-all duration-300"
              >
                <Upload className="w-6 h-6 text-white/30 group-hover:text-primary/70 transition-colors duration-300" />
              </motion.div>
            )}
          </AnimatePresence>

          <div className="flex-1 min-w-0">
            <AnimatePresence mode="wait">
              {selectedFile ? (
                <motion.div
                  key="selected"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                >
                  <div className="flex items-center gap-1.5 text-primary text-sm font-medium">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {t("changePhoto")}
                  </div>
                  <p className="text-xs text-white/30 truncate mt-0.5">{selectedFile.name}</p>
                </motion.div>
              ) : (
                <motion.div
                  key="empty-text"
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                >
                  <p className="text-sm font-medium text-white/70">{t("selectFacePhoto")}</p>
                  <p className="text-xs text-white/30 mt-0.5">{t("dragOrClick")} · JPG, PNG</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
