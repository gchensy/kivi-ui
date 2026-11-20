import type { ComponentProps } from "react";

import type { Chip } from "@/components/base/badges/chip";
import type { ListKind } from "@/lib/types";

export const LIST_KINDS: ListKind[] = ["black", "white", "gray"];
export const LIST_DIMENSIONS = ["phone", "id_no", "device", "ip", "company", "account", "other"] as const;

type ChipColor = NonNullable<ComponentProps<typeof Chip>["color"]>;

export const LIST_KIND_CHIP: Record<ListKind, ChipColor> = { black: "rose", white: "lime", gray: "neutral" };

export const LIST_KIND_GRADIENT: Record<ListKind, string> = {
  black: "from-rose-500 to-rose-600",
  white: "from-emerald-500 to-emerald-600",
  gray: "from-zinc-500 to-zinc-600",
};
