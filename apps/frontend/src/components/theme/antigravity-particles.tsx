import { useEffect, useRef } from "react";
import { useReducedMotion } from "framer-motion";

interface Particle {
  baseAngle: number;
  ringRadiusRatio: number;
  length: number;
  width: number;
  color: string;
  speed: number;
  phase: number;
  tilt: number;
}

const PALETTE_COLORS = [
  "#E6511A",
  "#F7B519",
  "#BA78D3",
  "#6D238E",
  "#F383AA",
  "#82C5B6",
];

function createParticles(count: number): Particle[] {
  return Array.from({ length: count }, (_, idx) => {
    const t = idx / count;
    return {
      baseAngle: t * Math.PI * 2 + (idx % 3) * 0.21,
      ringRadiusRatio: 0.68 + ((idx * 37) % 100) / 210,
      length: 5 + (idx % 4) * 2.2,
      width: 2.1 + (idx % 2) * 0.7,
      color: PALETTE_COLORS[idx % PALETTE_COLORS.length],
      speed: 0.00018 + (idx % 5) * 0.00004,
      phase: (idx * 1.37) % (Math.PI * 2),
      tilt: (idx % 7) * 0.14 - 0.4,
    };
  });
}

export function AntigravityParticles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const particles = createParticles(110);
    const pointer = { x: -9999, y: -9999, active: false };
    let rafId = 0;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = parent.clientWidth;
      const height = parent.clientHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const drawFrame = (time: number) => {
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      context.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;
      const rxBase = Math.max(width * 0.46, 220);
      const ryBase = Math.max(height * 0.44, 150);

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        const driftAngle = p.baseAngle + (prefersReducedMotion ? 0 : time * p.speed);
        const breath = prefersReducedMotion ? 0 : Math.sin(time * 0.0012 + p.phase) * 8;

        let x = cx + Math.cos(driftAngle) * (rxBase * p.ringRadiusRatio + breath);
        let y = cy + Math.sin(driftAngle) * (ryBase * p.ringRadiusRatio + breath);

        if (pointer.active && !prefersReducedMotion) {
          const dx = x - pointer.x;
          const dy = y - pointer.y;
          const dist = Math.hypot(dx, dy);
          if (dist < 140 && dist > 1) {
            const push = ((140 - dist) / 140) * 24;
            x += (dx / dist) * push;
            y += (dy / dist) * push;
          }
        }

        const rxClear = Math.min(Math.max(width * 0.25, 160), width * 0.42);
        const ryClear = Math.max(height * 0.36, 130);
        const clearDist = Math.hypot((x - cx) / rxClear, (y - cy) / ryClear);
        if (clearDist < 1) continue;

        const edgeFade = Math.min(1, (clearDist - 1) * 1.8);
        context.save();
        context.translate(x, y);
        context.rotate(driftAngle + p.tilt);
        context.globalAlpha = edgeFade * 0.88;
        context.fillStyle = p.color;
        context.beginPath();
        context.roundRect(-p.length / 2, -p.width / 2, p.length, p.width, p.width / 2);
        context.fill();
        context.restore();
      }

      if (!prefersReducedMotion) {
        rafId = window.requestAnimationFrame(drawFrame);
      }
    };

    const handlePointerMove = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = e.clientX - rect.left;
      pointer.y = e.clientY - rect.top;
      pointer.active =
        pointer.x >= 0 && pointer.y >= 0 && pointer.x <= rect.width && pointer.y <= rect.height;
    };

    const handlePointerLeave = () => {
      pointer.active = false;
    };

    resize();
    rafId = window.requestAnimationFrame(drawFrame);
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      window.cancelAnimationFrame(rafId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerleave", handlePointerLeave);
    };
  }, [prefersReducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 h-full w-full"
      aria-hidden="true"
    />
  );
}
