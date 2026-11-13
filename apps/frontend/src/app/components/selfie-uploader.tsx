import React, { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Camera, ImagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DaisyMark } from "@/components/theme/theme-motifs";
import { scaleInPop, springs } from "@/lib/animations";
import { SelfiePreviewCard } from "./selfie-preview-card";

interface SelfieUploaderProps {
  onFileSelected: (file: File | null) => void;
  selectedFile: File | null;
  isSearching?: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  cameraInputRef: React.RefObject<HTMLInputElement | null>;
}

export function SelfieUploader({
  onFileSelected,
  selectedFile,
  isSearching,
  fileInputRef,
  cameraInputRef,
}: SelfieUploaderProps) {
  const prefersReducedMotion = useReducedMotion();
  const [dragOver, setDragOver] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedFile) {
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }
    const url = URL.createObjectURL(selectedFile);
    setPreviewUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [selectedFile]);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleClear = () => {
    onFileSelected(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (cameraInputRef.current) cameraInputRef.current.value = "";
  };

  return (
    <div className="w-full">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files[0]) {
            onFileSelected(e.target.files[0]);
          }
        }}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="user"
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files[0]) {
            onFileSelected(e.target.files[0]);
          }
        }}
      />

      <AnimatePresence mode="wait">
        {previewUrl && selectedFile ? (
          <SelfiePreviewCard
            previewUrl={previewUrl}
            file={selectedFile}
            isSearching={isSearching}
            onClear={handleClear}
          />
        ) : (
          <motion.div
            key="dropzone"
            variants={prefersReducedMotion ? undefined : scaleInPop}
            initial={prefersReducedMotion ? false : "hidden"}
            animate="visible"
            exit="exit"
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            transition={springs.snappy}
            className={`relative flex flex-col items-center justify-center p-6 rounded-2xl border border-dashed transition-colors text-center ${
              dragOver
                ? "border-[#E6511A] bg-[#FDECE5]/40"
                : "border-[#211E1D]/20 bg-white/80 hover:border-[#211E1D]/35"
            }`}
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#FCF9F2] border border-[#211E1D]/12 mb-3">
              <DaisyMark size={24} />
            </div>

            <p className="text-sm font-medium text-[#211E1D]">
              Solte sua foto aqui
            </p>

            <div className="mt-4 grid grid-cols-2 sm:flex items-center justify-center gap-2 w-full">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => cameraInputRef.current?.click()}
                className="w-full sm:w-auto min-h-[40px]"
              >
                <Camera className="h-3.5 w-3.5 text-[#E6511A]" />
                <span>Câmera</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                className="w-full sm:w-auto min-h-[40px]"
              >
                <ImagePlus className="h-3.5 w-3.5 text-[#6D238E]" />
                <span>Galeria</span>
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
