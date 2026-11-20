"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { I18nProvider } from "@/lib/i18n/provider";
import type { Locale } from "@/lib/i18n/messages";

export function Providers({ locale, children }: { locale: Locale; children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale={locale}>{children}</I18nProvider>
    </QueryClientProvider>
  );
}
