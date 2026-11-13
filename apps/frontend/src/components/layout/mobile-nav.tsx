import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { Search, FolderSync } from "lucide-react";
import { springs } from "@/lib/animations";

const mobileTabs = [
  {
    to: "/",
    label: "Buscar",
    icon: Search,
    isActive: (pathname: string) => !pathname.startsWith("/admin"),
  },
  {
    to: "/admin",
    label: "Álbuns",
    icon: FolderSync,
    isActive: (pathname: string) => pathname.startsWith("/admin"),
  },
];

export function MobileNav() {
  const { pathname } = useLocation();

  return (
    <nav
      aria-label="Navegação móvel"
      className="md:hidden fixed bottom-4 left-1/2 -translate-x-1/2 z-40 w-[calc(100%-2rem)] max-w-[300px] rounded-full border border-[#211E1D]/12 bg-white/95 backdrop-blur-md p-1.5 shadow-[0_14px_38px_-10px_rgba(33,30,29,0.2)]"
      style={{ marginBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      <div className="grid grid-cols-2 gap-1">
        {mobileTabs.map((tab) => {
          const active = tab.isActive(pathname);
          const Icon = tab.icon;
          return (
            <Link
              key={tab.to}
              to={tab.to}
              className={`relative flex items-center justify-center gap-2 min-h-[44px] rounded-full px-3 py-2 text-xs font-medium transition-colors z-10 ${
                active ? "text-[#FCF9F2]" : "text-[#6E675F] active:bg-[#F4EFE3]"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="mobile-nav-pill"
                  transition={springs.tabIndicator}
                  className="absolute inset-0 rounded-full bg-[#211E1D] -z-10"
                />
              )}
              <Icon className="h-3.5 w-3.5 shrink-0" />
              <span>{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
