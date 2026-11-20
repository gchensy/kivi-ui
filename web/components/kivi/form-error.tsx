import { RiErrorWarningFill } from "@remixicon/react";

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="flex items-start gap-2 rounded-xl bg-status-rose-background px-3 py-2.5 text-body-2-medium text-status-rose-text">
      <RiErrorWarningFill className="mt-px size-4 shrink-0" aria-hidden />
      {message}
    </p>
  );
}
