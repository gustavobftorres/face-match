"use client";

import { motion } from "framer-motion";
import { LogIn, Upload, FolderSearch } from "lucide-react";
import { TranslationKey } from "@/lib/i18n";

interface LandingViewProps {
  t: (key: TranslationKey) => string;
  onLogin: () => void;
}

const HOW_IT_WORKS_STEPS = [
  { icon: LogIn, titleKey: "step1Title" as TranslationKey, descKey: "step1Desc" as TranslationKey },
  { icon: Upload, titleKey: "step2Title" as TranslationKey, descKey: "step2Desc" as TranslationKey },
  { icon: FolderSearch, titleKey: "step3Title" as TranslationKey, descKey: "step3Desc" as TranslationKey },
];

export function LandingView({ t, onLogin }: LandingViewProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 0.96, y: -20 }}
      transition={{ duration: 0.5 }}
      className="flex flex-col lg:flex-row items-center justify-center w-full min-h-screen max-w-7xl mx-auto px-5 sm:px-8 py-20 gap-16 lg:gap-24"
    >
      {/* Left Column: Hero & Sign In */}
      <div className="flex flex-col items-center flex-1 w-full max-w-lg lg:-mt-12 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mb-4"
        >
          <img src="/logo.png?v=2" alt="Drive Face Match" width={320} height={320} className="w-48 sm:w-64 md:w-80 lg:w-[400px] h-auto object-contain drop-shadow-2xl" />
        </motion.div>

        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="text-white/40 text-sm sm:text-base lg:text-lg max-w-sm mb-10 mx-auto"
        >
          {t("tagline")}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="flex flex-col items-center gap-4 mb-8"
        >
          <motion.button
            onClick={onLogin}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            className="flex items-center gap-3 px-8 lg:px-10 py-4 lg:py-5 rounded-2xl bg-primary hover:bg-primary/85 text-white font-semibold text-base lg:text-lg transition-colors glow-primary shadow-2xl"
          >
            <LogIn className="w-5 h-5 lg:w-6 lg:h-6" />
            {t("signInWithGoogle")}
          </motion.button>
          <p className="text-xs lg:text-sm text-white/30">{t("requiresDriveAccess")}</p>
        </motion.div>
      </div>

      {/* Right Column: How it Works */}
      <motion.div
        initial={{ opacity: 0, x: 40 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: 0.7, duration: 0.6 }}
        className="flex-1 w-full max-w-xl"
      >
        <div className="flex items-center gap-4 mb-8 opacity-60 lg:opacity-100">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent to-white/10" />
          <span className="text-xs font-semibold text-white/40 uppercase tracking-widest">
            {t("howItWorks")}
          </span>
          <div className="h-px flex-1 bg-gradient-to-l from-transparent to-white/10" />
        </div>

        <div className="flex flex-col gap-4 sm:gap-6">
          {HOW_IT_WORKS_STEPS.map(({ icon: Icon, titleKey, descKey }, idx) => (
            <motion.div
              key={titleKey}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.8 + idx * 0.12, duration: 0.5 }}
              className="relative group flex items-start text-left p-5 lg:p-6 rounded-2xl border border-white/5 bg-white-[0.02] hover:border-primary/30 py-6 hover:bg-primary/5 transition-all duration-400 backdrop-blur-sm"
            >
              <div className="w-12 h-12 lg:w-14 lg:h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 mr-5 shadow-inner">
                <Icon className="w-6 h-6 lg:w-7 lg:h-7 text-primary/80 group-hover:text-primary transition-colors" />
              </div>
              
              <div className="flex flex-col justify-center flex-1">
                <div className="flex items-center gap-3 mb-1.5">
                  <span className="text-xs font-bold text-primary/50 font-mono tracking-wider">0{idx + 1}</span>
                  <h3 className="text-sm lg:text-base font-semibold text-white/80 group-hover:text-white transition-colors">
                    {t(titleKey)}
                  </h3>
                </div>
                <p className="text-xs lg:text-sm text-white/40 leading-relaxed group-hover:text-white/60 transition-colors">
                  {t(descKey)}
                </p>
              </div>

            </motion.div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}
