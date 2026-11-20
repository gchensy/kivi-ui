"use client";

import { RiMenuLine } from "@remixicon/react";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { IconButton } from "@/components/base/buttons/icon-button";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { useMe } from "@/lib/queries";
import type { UserPage } from "@/lib/types";

import { KiviMark } from "./logo";
import { Sidebar } from "./sidebar";

/** Authenticated frame: floating sidebar (drawer below lg) and a 1300px content column. */
export function AppFrame({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useI18n();
  const me = useMe();
  const [navOpen, setNavOpen] = useState(false);
  const isAdmin = me.data?.role === "admin";
  const pending = useQuery({
    queryKey: ["users", "pending-count"],
    queryFn: () => api<UserPage>("/users?status=pending&size=1"),
    enabled: isAdmin,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) {
      router.replace(`/login?next=${encodeURIComponent(pathname ?? "/")}`);
    }
  }, [me.error, pathname, router]);

  if (!me.data) {
    return (
      <div className="flex h-dvh items-center justify-center bg-background-full">
        <KiviMark className="size-10 animate-pulse" />
      </div>
    );
  }

  const pendingCount = pending.data?.counts.pending;
  return (
    <div className="relative flex h-dvh w-full gap-4 overflow-hidden bg-background-full p-3">
      <Sidebar user={me.data} pendingUsers={pendingCount} className="hidden lg:flex" />
      {navOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <button type="button" aria-label={t("nav.closeNav")} onClick={() => setNavOpen(false)} className="absolute inset-0 cursor-pointer bg-black/40" />
          <div className="relative flex h-full p-3">
            <Sidebar user={me.data} pendingUsers={pendingCount} mobile onClose={() => setNavOpen(false)} className="flex" />
          </div>
        </div>
      )}
      <main className="relative flex min-h-0 min-w-0 flex-1 justify-center overflow-x-hidden overflow-y-auto sm:pt-3">
        <div className="flex w-full max-w-[1300px] flex-col gap-4 pb-6">
          <div className="flex items-center gap-2 lg:hidden">
            <IconButton icon={RiMenuLine} size="medium" aria-label={t("nav.openNav")} onClick={() => setNavOpen(true)} />
            <KiviMark className="size-7" />
            <span className="text-headline-semibold text-text-primary">{t("common.appName")}</span>
          </div>
          {children}
        </div>
      </main>
    </div>
  );
}

/** Page heading row: title, subtitle and actions above the content. */
export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3 px-1">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-title-2-medium text-text-primary">{title}</h1>
        {subtitle && <p className="text-body-regular text-text-secondary">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </header>
  );
}
