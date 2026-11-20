"use client";

import { RiCheckLine } from "@remixicon/react";
import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/application/theme/theme-toggle";
import { useI18n } from "@/lib/i18n/provider";

import { LocaleToggle } from "./locale-toggle";
import { KiviWordmark } from "./logo";

/** Decorative preview on the brand panel: a ROC curve and two KPI chips. */
function BrandArt() {
  const { t } = useI18n();
  return (
    <div className="relative w-full max-w-[380px]" aria-hidden>
      <div className="rounded-3xl border border-white/15 bg-white/10 p-5 shadow-2xl backdrop-blur-md">
        <div className="mb-3 flex items-center justify-between text-caption-1-medium text-white/80">
          <span>ROC · OOT</span>
          <span className="rounded-full bg-white/15 px-2 py-0.5 text-white">AUC 0.735</span>
        </div>
        <svg viewBox="0 0 200 140" className="w-full">
          {[0, 35, 70, 105, 140].map((y) => (
            <line key={y} x1="0" x2="200" y1={y} y2={y} stroke="white" strokeOpacity="0.12" />
          ))}
          <line x1="0" y1="140" x2="200" y2="0" stroke="white" strokeOpacity="0.35" strokeDasharray="4 4" />
          <path d="M0 140 C 18 70, 60 38, 200 8 L200 140 Z" fill="white" fillOpacity="0.12" />
          <path d="M0 140 C 18 70, 60 38, 200 8" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
          <path d="M0 140 C 24 82, 70 46, 200 14" fill="none" stroke="#fdba74" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>
      <div className="absolute -bottom-8 -start-10 rounded-2xl border border-white/15 bg-white/15 px-4 py-3 text-white shadow-xl backdrop-blur-md">
        <p className="text-caption-1-medium text-white/75">KS</p>
        <p className="text-title-2-semibold">0.370</p>
      </div>
      <div className="absolute -top-16 -end-6 rounded-2xl border border-white/15 bg-white/15 px-4 py-3 text-white shadow-xl backdrop-blur-md">
        <p className="text-caption-1-medium text-white/75">PSI</p>
        <p className="text-title-2-semibold">0.082</p>
        <p className="text-caption-2-medium text-white/70">{t("alerts.normal")}</p>
      </div>
    </div>
  );
}

export function AuthFrame({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  return (
    <main className="grid min-h-dvh bg-background-full lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <div className="flex flex-col px-6 py-6 sm:px-10">
        <div className="flex items-center justify-between gap-4">
          <KiviWordmark name={t("common.appName")} tagline={t("common.tagline")} />
          <div className="flex items-center gap-2">
            <div className="w-[132px]">
              <LocaleToggle />
            </div>
            <ThemeToggle collapsed />
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[400px]">{children}</div>
        </div>
        <p className="text-center text-caption-1-regular text-text-tertiary">
          kivi-ui · MIT · {t("common.engine")}
        </p>
      </div>

      <div className="relative m-3 hidden overflow-hidden rounded-3xl bg-linear-to-br from-accent-600 via-accent-700 to-indigo-900 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div
          className="pointer-events-none absolute inset-0 opacity-40"
          style={{
            backgroundImage:
              "radial-gradient(circle at 20% 15%, rgba(255,255,255,0.35), transparent 40%), radial-gradient(circle at 85% 80%, rgba(253,186,116,0.35), transparent 45%)",
          }}
          aria-hidden
        />
        <div className="relative flex max-w-[460px] flex-col gap-4 text-white">
          <h2 className="text-display-4-semibold">{t("auth.brandTitle")}</h2>
          <p className="text-body-regular text-white/80">{t("auth.brandDesc")}</p>
          <ul className="mt-2 flex flex-col gap-2.5">
            {(["brandPoint1", "brandPoint2", "brandPoint3"] as const).map((key) => (
              <li key={key} className="flex items-center gap-2.5 text-body-medium">
                <span className="flex size-6 items-center justify-center rounded-full bg-white/20">
                  <RiCheckLine className="size-4" aria-hidden />
                </span>
                {t(`auth.${key}`)}
              </li>
            ))}
          </ul>
        </div>
        <div className="relative flex justify-center pb-8">
          <BrandArt />
        </div>
      </div>
    </main>
  );
}
