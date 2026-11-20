"use client";

import { RiLoader4Line } from "@remixicon/react";

import { Chip } from "@/components/base/badges/chip";
import { useI18n } from "@/lib/i18n/provider";
import type { VersionStatus } from "@/lib/types";

const COLOR: Record<VersionStatus, "blue" | "rose" | "neutral" | "yellow" | "cyan" | "lime" | "gray"> = {
  training: "blue",
  failed: "rose",
  draft: "neutral",
  in_review: "yellow",
  approved: "cyan",
  online: "lime",
  retired: "gray",
};

export function VersionStatusChip({ status, label }: { status: VersionStatus; label?: string }) {
  const { t } = useI18n();
  return (
    <Chip variant="subtle" color={COLOR[status]}>
      <span className="flex items-center gap-1">
        {status === "training" && <RiLoader4Line className="size-3 animate-spin" aria-hidden />}
        {label ? `${label} · ` : ""}
        {t(`mdl.statuses.${status}`)}
      </span>
    </Chip>
  );
}
