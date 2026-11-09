import * as React from "react";
import { cn } from "@/lib/utils";

const Button = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ className, ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-lg px-6 py-3 text-sm font-medium transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none",
          "bg-white/10 hover:bg-white/20 text-white backdrop-blur-md border border-white/20 shadow-lg hover:shadow-xl hover:-translate-y-0.5 active:translate-y-0",
          className
        )}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };
