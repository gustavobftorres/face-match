"use client";

import { useState, useEffect, useMemo } from "react";
import { Locale, getTranslations, TranslationKey } from "@/lib/i18n";

function detectLocale(): Locale {
  if (typeof navigator === "undefined") return "en";
  const langs = navigator.languages?.length ? Array.from(navigator.languages) : [navigator.language];
  const prefersPt = langs.some((l) => l.toLowerCase().startsWith("pt"));
  return prefersPt ? "pt-BR" : "en";
}

export function useLocale() {
  const [locale, setLocale] = useState<Locale>("en");

  useEffect(() => {
    setTimeout(() => setLocale(detectLocale()), 0);
  }, []);

  const t = useMemo(() => {
    const dict = getTranslations(locale);
    return (key: TranslationKey): string => dict[key];
  }, [locale]);

  return { locale, t };
}
