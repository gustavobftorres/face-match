"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence, useMotionValue, useSpring } from "framer-motion";

interface Particle {
  id: number;
  x: number;
  y: number;
  size: number;
  color: string;
  dx: number;
  dy: number;
}

const COLORS = [
  "rgba(99,102,241,0.8)",
  "rgba(139,92,246,0.8)",
  "rgba(168,85,247,0.8)",
  "rgba(129,140,248,0.8)",
  "rgba(196,181,253,0.7)",
];

const MAX_PARTICLES = 20;
let counter = 0;

export function CursorParticles() {
  const [particles, setParticles] = useState<Particle[]>([]);
  const lastPos = useRef({ x: -999, y: -999 });
  const throttleRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const rawX = useMotionValue(-300);
  const rawY = useMotionValue(-300);
  const glowX = useSpring(rawX, { stiffness: 80, damping: 20, mass: 0.5 });
  const glowY = useSpring(rawY, { stiffness: 80, damping: 20, mass: 0.5 });

  const spawnParticle = useCallback((x: number, y: number) => {
    const newParticle: Particle = {
      id: counter++,
      x,
      y,
      size: Math.random() * 6 + 3,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      dx: (Math.random() - 0.5) * 40,
      dy: (Math.random() - 0.5) * 40 - 15,
    };

    setParticles((prev) => {
      const next = [...prev, newParticle];
      return next.length > MAX_PARTICLES ? next.slice(next.length - MAX_PARTICLES) : next;
    });

    setTimeout(() => {
      setParticles((prev) => prev.filter((p) => p.id !== newParticle.id));
    }, 700);
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      rawX.set(e.clientX);
      rawY.set(e.clientY);

      const dx = e.clientX - lastPos.current.x;
      const dy = e.clientY - lastPos.current.y;
      const dist = Math.sqrt(dx * dx + dy * dy);

      if (dist < 12) return;
      lastPos.current = { x: e.clientX, y: e.clientY };

      if (throttleRef.current) return;
      throttleRef.current = setTimeout(() => {
        throttleRef.current = null;
        spawnParticle(e.clientX, e.clientY);
      }, 30);
    };

    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [spawnParticle, rawX, rawY]);

  return (
    <div className="fixed inset-0 pointer-events-none z-50 overflow-hidden">
      <motion.div
        className="absolute rounded-full"
        style={{
          x: glowX,
          y: glowY,
          translateX: "-50%",
          translateY: "-50%",
          width: 320,
          height: 320,
          background:
            "radial-gradient(circle, rgba(99,102,241,0.12) 0%, rgba(139,92,246,0.06) 40%, transparent 70%)",
          filter: "blur(24px)",
        }}
      />

      <AnimatePresence>
        {particles.map((p) => (
          <motion.div
            key={p.id}
            className="absolute rounded-full"
            style={{
              left: p.x,
              top: p.y,
              width: p.size,
              height: p.size,
              background: p.color,
              boxShadow: `0 0 ${p.size * 2}px ${p.color}`,
              translateX: "-50%",
              translateY: "-50%",
            }}
            initial={{ scale: 1, opacity: 1, x: 0, y: 0 }}
            animate={{ scale: 0, opacity: 0, x: p.dx, y: p.dy }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.65, ease: "easeOut" }}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
