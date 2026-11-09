"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";

interface Particle {
  id: number;
  x: number;
  y: number;
  size: number;
  duration: number;
  delay: number;
  opacity: number;
}

const PARTICLE_COUNT = 30;

const orbs = [
  { size: 600, x: "10%", y: "15%", color: "rgba(99,102,241,0.12)", duration: 25, delay: 0 },
  { size: 500, x: "70%", y: "60%", color: "rgba(139,92,246,0.10)", duration: 30, delay: 5 },
  { size: 400, x: "40%", y: "80%", color: "rgba(59,130,246,0.08)", duration: 20, delay: 10 },
  { size: 350, x: "85%", y: "10%", color: "rgba(168,85,247,0.09)", duration: 35, delay: 3 },
  { size: 300, x: "20%", y: "50%", color: "rgba(99,102,241,0.07)", duration: 28, delay: 8 },
];

export function AnimatedBackground() {
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    setTimeout(() => {
      setParticles(
        Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
          id: i,
          x: Math.random() * 100,
          y: Math.random() * 100,
          size: Math.random() * 2 + 0.5,
          duration: Math.random() * 10 + 8,
          delay: Math.random() * 5,
          opacity: Math.random() * 0.4 + 0.1,
        }))
      );
    }, 0);
  }, []);

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,#0d0d2b_0%,#020208_60%)]" />

      <div
        className="absolute inset-0 animate-grid opacity-[0.04]"
        style={{
          backgroundImage: `
            linear-gradient(rgba(99,102,241,0.5) 1px, transparent 1px),
            linear-gradient(90deg, rgba(99,102,241,0.5) 1px, transparent 1px)
          `,
          backgroundSize: "60px 60px",
        }}
      />

      {orbs.map((orb, i) => (
        <div
          key={i}
          className="absolute rounded-full blur-3xl animate-float"
          style={{
            width: orb.size,
            height: orb.size,
            left: orb.x,
            top: orb.y,
            background: orb.color,
            animationDuration: `${orb.duration}s`,
            animationDelay: `${orb.delay}s`,
            transform: "translate(-50%, -50%)",
          }}
        />
      ))}

      {particles.map((p) => (
        <motion.div
          key={p.id}
          className="absolute rounded-full bg-indigo-400"
          style={{
            width: p.size,
            height: p.size,
            left: `${p.x}%`,
            top: `${p.y}%`,
            opacity: p.opacity,
          }}
          animate={{
            y: [0, -30, 10, -20, 0],
            x: [0, 10, -5, 15, 0],
            opacity: [p.opacity, p.opacity * 2, p.opacity * 0.5, p.opacity * 1.5, p.opacity],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}

      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-[#020208]/80" />
    </div>
  );
}
