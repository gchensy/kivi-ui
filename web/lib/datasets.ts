import type { I18n } from "./i18n/provider";
import type { Dataset } from "./types";

/** "Dec 2025 – Nov 2026" from the dataset's monthly profile, or null without a date column. */
export function periodText(dataset: Dataset, i18n: I18n): string | null {
  const months = dataset.profile.monthly ?? [];
  if (!months.length) return null;
  const first = months[0].month;
  const last = months[months.length - 1].month;
  return first === last ? i18n.month(first, true) : `${i18n.month(first, true)} – ${i18n.month(last, true)}`;
}

/** Parse "0.3, 0.5；0.7" into unique numbers, ignoring blanks and anything non-numeric. */
export function parseNumbers(text: string): number[] {
  const values = text
    .split(/[\s,，;；]+/)
    .filter((part) => part.trim() !== "")
    .map(Number)
    .filter(Number.isFinite);
  return [...new Set(values)];
}
