import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { springs } from "@/lib/animations";

const navItems = [
  { to: "/", label: "Buscar fotos", matchAdmin: false },
  { to: "/admin", label: "Álbuns", matchAdmin: true },
];

export function Header() {
  const location = useLocation();
  const isAdmin = location.pathname.startsWith("/admin");

  return (
    <header className="sticky top-0 z-40 border-b border-[#211E1D]/8 bg-[#FCF9F2]/90 backdrop-blur-md">
      <div className="mx-auto flex h-14 sm:h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-8">
          <Link
            to="/"
            className="text-base font-medium tracking-[-0.025em] text-[#211E1D] hover:opacity-80 transition-opacity"
          >
            Face Match
          </Link>

          <nav className="hidden md:flex items-center gap-7">
            {navItems.map((item) => {
              const active = item.matchAdmin ? isAdmin : !isAdmin;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`relative py-1 text-sm transition-colors ${
                    active
                      ? "font-medium text-[#211E1D]"
                      : "font-normal text-[#6E675F] hover:text-[#211E1D]"
                  }`}
                >
                  {item.label}
                  {active && (
                    <motion.span
                      layoutId="desktop-nav-dot"
                      transition={springs.tabIndicator}
                      className="absolute -bottom-1 left-1/2 -translate-x-1/2 h-1.5 w-1.5 rounded-full bg-[#E6511A]"
                    />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        <Link
          to={isAdmin ? "/" : "/admin"}
          className="inline-flex items-center gap-1.5 rounded-full bg-[#211E1D] px-4 py-1.5 sm:py-2 text-xs sm:text-sm font-medium text-[#FCF9F2] hover:bg-[#383331] transition-colors"
        >
          <span>{isAdmin ? "Buscar" : "Admin"}</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
    </header>
  );
}
