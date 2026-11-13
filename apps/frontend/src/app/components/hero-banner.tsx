import { motion, useReducedMotion } from "framer-motion";
import { ArrowDown, Camera, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AntigravityParticles } from "@/components/theme/antigravity-particles";
import { SquiggleUnderline } from "@/components/theme/theme-motifs";
import { fadeInUp } from "@/lib/animations";

interface HeroBannerProps {
  onQuickUpload: () => void;
  onQuickCamera: () => void;
  onJumpToStudio: () => void;
}

export function HeroBanner({
  onQuickUpload,
  onQuickCamera,
  onJumpToStudio,
}: HeroBannerProps) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <section className="relative w-full overflow-hidden py-12 sm:py-20 md:py-24 px-4 sm:px-6">
      <AntigravityParticles />

      <motion.div
        variants={prefersReducedMotion ? undefined : fadeInUp}
        initial={prefersReducedMotion ? false : "hidden"}
        animate="visible"
        className="relative z-10 mx-auto max-w-2xl text-center"
      >
        <h1 className="text-[2.25rem] sm:text-5xl md:text-[62px] font-medium tracking-[-0.035em] leading-[1.06] text-[#211E1D]">
          Encontre{" "}
          <span className="relative inline-block">
            <span className="relative z-10">suas fotos</span>
            <SquiggleUnderline className="absolute left-0 -bottom-1 sm:-bottom-1.5 w-full h-3 sm:h-4 pointer-events-none" />
          </span>
        </h1>

        <p className="mt-4 text-sm sm:text-base text-[#6E675F] max-w-md mx-auto">
          Selecione um álbum e envie uma selfie.
        </p>

        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button
            type="button"
            variant="primary"
            size="lg"
            onClick={onQuickUpload}
            className="px-6"
          >
            <Upload className="h-4 w-4" />
            <span>Enviar selfie</span>
          </Button>

          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={onQuickCamera}
            className="sm:hidden px-5"
          >
            <Camera className="h-4 w-4 text-[#E6511A]" />
            <span>Tirar selfie</span>
          </Button>

          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={onJumpToStudio}
            className="hidden sm:inline-flex px-6"
          >
            <span>Ver álbuns</span>
            <ArrowDown className="h-4 w-4 text-[#6E675F]" />
          </Button>
        </div>
      </motion.div>
    </section>
  );
}
