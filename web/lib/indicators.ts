import type { IndicatorCategory, IvLevel } from "./types";

export const CATEGORIES: IndicatorCategory[] = ["basic", "application", "credit", "transaction", "behavior", "derived", "other"];

export const LEVEL_CHIP: Record<IvLevel, "neutral" | "yellow" | "cyan" | "blue" | "purple"> = {
  useless: "neutral",
  weak: "yellow",
  medium: "cyan",
  strong: "blue",
  suspicious: "purple",
};

/** Conventional IV strength bands (same as the backend's iv_level). */
export function ivLevel(iv: number): IvLevel {
  return iv < 0.02 ? "useless" : iv < 0.1 ? "weak" : iv < 0.3 ? "medium" : iv < 0.5 ? "strong" : "suspicious";
}

export function indicatorName(item: { name: string; name_en: string | null }, locale: string): string {
  return locale === "en-US" && item.name_en ? item.name_en : item.name;
}
