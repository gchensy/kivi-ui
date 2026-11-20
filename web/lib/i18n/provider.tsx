"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { DirectionProvider } from "@/components/foundations/direction/direction";

import { LOCALE_COOKIE, MESSAGES, type Locale } from "./messages";

type Vars = Record<string, string | number>;
export type Bilingual = { zh: string; en: string };

export interface I18n {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  /** Look up a dot-separated key, e.g. `t("auth.signIn")`, filling {placeholders}. */
  t: (key: string, vars?: Vars) => string;
  /** Pick the current language from a `{ zh, en }` label sent by the API. */
  pick: (label: Bilingual | undefined | null) => string;
  num: (value: number | null | undefined, options?: Intl.NumberFormatOptions) => string;
  pct: (value: number | null | undefined, digits?: number) => string;
  date: (value: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions) => string;
  /** "2026-03" → "3月" / "Mar", or with year "2026年3月" / "Mar 2026". */
  month: (value: string, withYear?: boolean) => string;
}

const I18nContext = createContext<I18n | null>(null);

function lookup(locale: Locale, key: string): string | undefined {
  let node: unknown = MESSAGES[locale];
  const parts = key.split(".");
  for (let i = 0; i < parts.length; i++) {
    if (!node || typeof node !== "object") return undefined;
    const table = node as Record<string, unknown>;
    if (parts[i] in table) {
      node = table[parts[i]];
    } else {
      // Keys like "audit.actions.auth.login" keep dots inside their last segment.
      const value = table[parts.slice(i).join(".")];
      return typeof value === "string" ? value : undefined;
    }
  }
  return typeof node === "string" ? node : undefined;
}

export function I18nProvider({ initialLocale, children }: { initialLocale: Locale; children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
  }, []);

  const value = useMemo<I18n>(() => {
    const t = (key: string, vars?: Vars) => {
      const template = lookup(locale, key) ?? lookup("zh-CN", key) ?? key;
      return vars ? template.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? `{${name}}`)) : template;
    };
    const numberFormat = (options?: Intl.NumberFormatOptions) => new Intl.NumberFormat(locale, options);
    return {
      locale,
      setLocale,
      t,
      pick: (label) => (label ? (locale === "zh-CN" ? label.zh : label.en) : ""),
      num: (value, options) =>
        value === null || value === undefined || Number.isNaN(value) ? "—" : numberFormat(options).format(value),
      pct: (value, digits = 1) =>
        value === null || value === undefined || Number.isNaN(value)
          ? "—"
          : numberFormat({ style: "percent", minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value),
      date: (value, options = { dateStyle: "medium", timeStyle: "short" }) =>
        value ? new Intl.DateTimeFormat(locale, options).format(typeof value === "string" ? new Date(value) : value) : "—",
      month: (value, withYear = false) => {
        const [year, month] = value.split("-").map(Number);
        const d = new Date(Date.UTC(year, month - 1, 1));
        return new Intl.DateTimeFormat(locale, {
          month: "short",
          year: withYear ? "numeric" : undefined,
          timeZone: "UTC",
        }).format(d);
      },
    };
  }, [locale, setLocale]);

  return (
    <I18nContext.Provider value={value}>
      <DirectionProvider locale={locale}>{children}</DirectionProvider>
    </I18nContext.Provider>
  );
}

export function useI18n(): I18n {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside I18nProvider");
  return context;
}
