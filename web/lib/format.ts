import type { I18n } from "./i18n/provider";
import type { Bin, ScorecardBin, Unit } from "./types";

/** Format a bin bound in its unit: ratios as percentages, money compactly, counts as integers. */
export function formatBound(value: number, unit: Unit, i18n: I18n): string {
  switch (unit) {
    case "ratio":
      return i18n.pct(value, 0);
    case "cny":
      return i18n.num(value, { notation: "compact", maximumFractionDigits: 1 });
    case "count":
      return i18n.num(value, { maximumFractionDigits: 0 });
    default:
      return i18n.num(value, { maximumFractionDigits: 1 });
  }
}

/** Human label for a bin: interval bounds are (lower, upper], categories use their name. */
export function binLabel(bin: Bin | ScorecardBin, unit: Unit, i18n: I18n): string {
  if (bin.label) return i18n.pick(bin.label);
  if (bin.missing) return i18n.t("indicators.missing");
  const { lower, upper } = bin;
  if (unit === "count") {
    // Integer counts read better as inclusive ranges: (0, 2] → 1–2.
    const lo = lower === null || lower === undefined ? null : Math.floor(lower) + 1;
    const hi = upper === null || upper === undefined ? null : Math.floor(upper);
    if (lo === null && hi !== null) return `≤ ${hi}`;
    if (hi === null && lo !== null) return `≥ ${lo}`;
    if (lo !== null && hi !== null) return lo === hi ? `${lo}` : `${lo}–${hi}`;
  }
  if ((lower === null || lower === undefined) && upper !== null && upper !== undefined) {
    return `≤ ${formatBound(upper, unit, i18n)}`;
  }
  if ((upper === null || upper === undefined) && lower !== null && lower !== undefined) {
    return `> ${formatBound(lower, unit, i18n)}`;
  }
  return `${formatBound(lower as number, unit, i18n)} – ${formatBound(upper as number, unit, i18n)}`;
}

export function bandLabel(lower: number | null, upper: number | null): string {
  if (lower === null) return `< ${upper}`;
  if (upper === null) return `≥ ${lower}`;
  return `${lower}–${upper}`;
}

export function signed(text: string, value: number): string {
  return value > 0 ? `+${text}` : text;
}

export function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  // CJK names: the first character (the family name); Latin names: initials of the first two words.
  if (/[㐀-鿿]/.test(trimmed)) return trimmed[0];
  return trimmed
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}
