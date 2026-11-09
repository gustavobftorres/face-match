"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { motion } from "framer-motion";

export default function AuthCallbackPage() {
  const router = useRouter();
  const { handleCallback } = useAuth();
  const handledRef = useRef(false);

  useEffect(() => {
    if (handledRef.current) return;
    handledRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");

    if (!code) {
      router.replace("/");
      return;
    }

    handleCallback(code)
      .then(() => router.replace("/"))
      .catch(() => router.replace("/"));
  }, [handleCallback, router]);

  return (
    <main className="min-h-screen bg-gradient-to-b from-black via-gray-900 to-black text-white flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex flex-col items-center gap-4"
      >
        <div className="w-10 h-10 rounded-full border-2 border-primary border-t-transparent animate-spin" />
        <p className="text-white/60 text-sm">Signing in...</p>
      </motion.div>
    </main>
  );
}
