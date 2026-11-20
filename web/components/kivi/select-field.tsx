"use client";

import type { Key } from "react-aria-components";

import { Select, SelectItem } from "@/components/base/select/select";
import { cx } from "@/utils/cx";

export interface Option {
  id: string;
  label: string;
}

/** A labelled BoardUI select over plain string options. */
export function SelectField({
  label,
  value,
  onChange,
  options,
  hint,
  isDisabled,
  className,
  size = "md",
}: {
  label?: string;
  value: string | null;
  onChange: (value: string) => void;
  options: Option[];
  hint?: string;
  isDisabled?: boolean;
  className?: string;
  size?: "sm" | "md";
}) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-1.5", className)}>
      {label && <span className="text-body-medium text-text-secondary">{label}</span>}
      <Select
        aria-label={label ?? options[0]?.label}
        size={size}
        selectedKey={value as Key | null}
        onSelectionChange={(key) => key !== null && onChange(String(key))}
        isDisabled={isDisabled}
      >
        {options.map((option) => (
          <SelectItem key={option.id} id={option.id} textValue={option.label}>
            {option.label}
          </SelectItem>
        ))}
      </Select>
      {hint && <span className="text-caption-1-regular text-text-tertiary">{hint}</span>}
    </div>
  );
}
