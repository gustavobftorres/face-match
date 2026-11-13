import React from "react";
import { Header } from "./header";
import { MobileNav } from "./mobile-nav";
import { WaveHorizon } from "@/components/theme/theme-motifs";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-[100dvh] flex flex-col text-[#211E1D] bg-[#FCF9F2]">
      <Header />
      <main className="flex-1 w-full pb-24 md:pb-12">{children}</main>
      <footer className="mt-16 sm:mt-20">
        <WaveHorizon />
      </footer>
      <MobileNav />
    </div>
  );
}
