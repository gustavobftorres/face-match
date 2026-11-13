import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 min-h-[44px] w-full rounded-full border border-[#211E1D]/15 bg-[#FCF9F2]/60 px-4 py-2 text-sm text-[#211E1D] placeholder:text-[#8A8279] focus-visible:outline-none focus-visible:bg-white focus-visible:border-[#211E1D] focus-visible:ring-4 focus-visible:ring-[#F7B519]/25 disabled:cursor-not-allowed disabled:bg-[#F4EFE3]/60 disabled:text-[#8A8279] transition-all",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
