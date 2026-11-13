import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "neutral" | "success" | "warning" | "danger" | "lilac" | "orange" | "ink";
}

const variantStyles: Record<NonNullable<BadgeProps["variant"]>, string> = {
  neutral: "bg-[#F4EFE3] text-[#5C554E] border-[#211E1D]/10",
  success: "bg-[#E2F3EE] text-[#175F50] border-[#82C5B6]/45",
  warning: "bg-[#FFF2CC] text-[#7D4F00] border-[#F7B519]/45",
  danger: "bg-[#FDE8E4] text-[#9E2B16] border-[#E6511A]/30",
  lilac: "bg-[#F4E9FA] text-[#6D238E] border-[#BA78D3]/35",
  orange: "bg-[#FDECE5] text-[#B83B0E] border-[#E6511A]/30",
  ink: "bg-[#211E1D] text-[#FCF9F2] border-[#211E1D]",
};

export function Badge({ className, variant = "neutral", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border whitespace-nowrap",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}
