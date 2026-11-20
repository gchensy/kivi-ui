import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { cookies, headers } from "next/headers";
import Script from "next/script";

import { DEFAULT_LOCALE, LOCALE_COOKIE, LOCALES, type Locale } from "@/lib/i18n/messages";

import { Providers } from "./providers";

import "@/styles/globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"], axes: ["opsz"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-mono-source", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Kivi 风控平台 · Kivi Risk Platform", template: "%s · Kivi" },
  description: "Risk data, indicator, model and strategy management, powered by kivi.",
};

async function resolveLocale(): Promise<Locale> {
  const stored = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (LOCALES.includes(stored as Locale)) return stored as Locale;
  const accept = (await headers()).get("accept-language")?.toLowerCase() ?? "";
  if (accept.startsWith("en")) return "en-US";
  return DEFAULT_LOCALE;
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await resolveLocale();
  return (
    <html
      lang={locale}
      dir="ltr"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="flex min-h-full flex-col bg-background-full font-sans">
        {/* Apply the stored theme before first paint (key shared with BoardUI's ThemeToggle). */}
        <Script id="kivi-theme" strategy="beforeInteractive">
          {`(function(){try{var t=localStorage.getItem("boardui:theme");var dark=t?t==="dark":window.matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.classList.toggle("dark",dark)}catch(e){}})();`}
        </Script>
        <Providers locale={locale}>{children}</Providers>
      </body>
    </html>
  );
}
