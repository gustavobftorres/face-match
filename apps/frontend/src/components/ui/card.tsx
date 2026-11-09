import * as React from "react";
import { cn } from "@/lib/utils";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "rounded-xl border border-white/10 bg-black/40 text-card-foreground shadow-2xl backdrop-blur-xl",
          className
        )}
        {...props}
      />
    );
  }
);
Card.displayName = "Card";

export { Card };
