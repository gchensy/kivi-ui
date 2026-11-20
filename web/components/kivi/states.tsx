"use client";

import { RiErrorWarningLine, RiRefreshLine } from "@remixicon/react";

import { Button } from "@/components/base/buttons/button";
import { errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { cx } from "@/utils/cx";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-2xl bg-background-secondary-default", className)} aria-hidden />;
}

/** Placeholder layout while a page's first data arrives. */
export function PageSkeleton() {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-4" role="status" aria-label={t("common.loading")}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-[172px]" />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <Skeleton className="h-[360px] xl:col-span-2" />
        <Skeleton className="h-[360px]" />
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const i18n = useI18n();
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl bg-background-secondary-default px-6 py-16 text-center">
      <RiErrorWarningLine className="size-8 text-foreground-icon-tertiary" aria-hidden />
      <div className="flex flex-col gap-1">
        <p className="text-headline-medium text-text-primary">{i18n.t("common.loadFailed")}</p>
        <p className="text-body-regular text-text-secondary">{errorMessage(error, i18n.t)}</p>
      </div>
      {onRetry && (
        <Button variant="secondary" size="small" leadingIcon={RiRefreshLine} onClick={onRetry}>
          {i18n.t("common.retry")}
        </Button>
      )}
    </div>
  );
}
