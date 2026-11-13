import * as React from "react";
import { HTMLMotionProps, motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { fadeInUp } from "@/lib/animations";

export interface PanelProps extends Omit<HTMLMotionProps<"div">, "ref" | "title" | "children"> {
  title?: string;
  description?: string;
  action?: React.ReactNode;
  dotColor?: string;
  children?: React.ReactNode;
}

export function Panel({
  title,
  description,
  action,
  dotColor = "#E6511A",
  children,
  className,
  ...props
}: PanelProps) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <motion.div
      variants={prefersReducedMotion ? undefined : fadeInUp}
      initial={prefersReducedMotion ? false : "hidden"}
      animate="visible"
      className={cn(
        "rounded-[28px] border border-[#211E1D]/10 bg-white shadow-[0_24px_64px_-28px_rgba(33,30,29,0.12)] overflow-hidden",
        className
      )}
      {...props}
    >
      {(title || action) && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#211E1D]/8 px-5 py-4 sm:px-7 sm:py-5">
          <div className="flex items-center gap-2.5 min-w-0">
            <span
              className="h-2.5 w-2.5 rounded-full shrink-0 border border-[#211E1D]/20"
              style={{ backgroundColor: dotColor }}
            />
            <div className="min-w-0">
              {title && (
                <h3 className="text-sm sm:text-base font-medium tracking-[-0.015em] text-[#211E1D] truncate">
                  {title}
                </h3>
              )}
              {description && (
                <p className="mt-0.5 text-xs text-[#6E675F] line-clamp-2">
                  {description}
                </p>
              )}
            </div>
          </div>
          {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
        </div>
      )}
      <div className="p-5 sm:p-7">{children}</div>
    </motion.div>
  );
}
