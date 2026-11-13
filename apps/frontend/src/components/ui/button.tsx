import * as React from "react";
import { HTMLMotionProps, motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";
import { springs } from "@/lib/animations";

export interface ButtonProps extends Omit<HTMLMotionProps<"button">, "ref"> {
  variant?: "primary" | "orange" | "lilac" | "outline" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
}

const variantStyles: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary:
    "bg-[#211E1D] text-[#FCF9F2] hover:bg-[#383331] border border-[#211E1D] shadow-xs",
  orange:
    "bg-[#E6511A] text-white hover:bg-[#D44713] border border-[#211E1D]/15 shadow-xs",
  lilac:
    "bg-[#F4E9FA] text-[#6D238E] hover:bg-[#EAD7F5] border border-[#BA78D3]/35",
  outline:
    "bg-white text-[#211E1D] hover:bg-[#F4EFE3]/70 border border-[#211E1D]/15",
  ghost:
    "bg-transparent text-[#6E675F] hover:bg-[#F4EFE3] hover:text-[#211E1D]",
  danger:
    "bg-[#C8331B] text-white hover:bg-[#B22B15] border border-[#211E1D]/10",
};

const sizeStyles: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "min-h-[36px] px-4 py-1.5 text-xs rounded-full gap-1.5",
  md: "min-h-[42px] px-5 py-2 text-sm rounded-full gap-2",
  lg: "min-h-[48px] px-6 py-2.5 text-sm sm:text-base rounded-full gap-2.5",
};

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", disabled, children, ...props }, ref) => {
    const prefersReducedMotion = useReducedMotion();
    const interactive = !disabled && !prefersReducedMotion;

    return (
      <motion.button
        ref={ref}
        disabled={disabled}
        whileHover={interactive ? { scale: 1.02 } : undefined}
        whileTap={interactive ? { scale: 0.97 } : undefined}
        transition={springs.buttonPress}
        className={cn(
          "inline-flex items-center justify-center font-medium tracking-[-0.01em] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#211E1D] focus-visible:ring-offset-2 focus-visible:ring-offset-[#FCF9F2] disabled:opacity-45 disabled:pointer-events-none cursor-pointer select-none whitespace-nowrap",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        {...props}
      >
        {children}
      </motion.button>
    );
  }
);
Button.displayName = "Button";

export { Button };
