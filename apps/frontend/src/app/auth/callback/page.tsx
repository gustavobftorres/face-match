import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { useAuth } from "@/hooks/use-auth";
import { scaleInPop } from "@/lib/animations";

export default function AuthCallbackPage() {
  const prefersReducedMotion = useReducedMotion();
  const navigate = useNavigate();
  const { handleCallback } = useAuth();
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    handledRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");

    if (!code) {
      navigate("/admin", { replace: true });
      return;
    }

    handleCallback(code)
      .then(() => navigate("/admin", { replace: true }))
      .catch(() => navigate("/admin", { replace: true }));
  }, [handleCallback, navigate]);

  return (
    <main className="min-h-[100dvh] bg-[#FCF9F2] flex items-center justify-center p-4 text-[#211E1D]">
      <motion.div
        variants={prefersReducedMotion ? undefined : scaleInPop}
        initial={prefersReducedMotion ? false : "hidden"}
        animate="visible"
        className="w-full max-w-xs rounded-[28px] border border-[#211E1D]/10 bg-white p-8 text-center shadow-[0_24px_60px_-24px_rgba(33,30,29,0.16)]"
      >
        <div className="mx-auto mb-4 h-6 w-6 rounded-full border-2 border-[#211E1D] border-t-transparent animate-spin" />
        <p className="text-sm font-medium text-[#211E1D]">
          Conectando Google Drive...
        </p>
      </motion.div>
    </main>
  );
}
