"use client";

import { RiDeleteBinLine } from "@remixicon/react";
import { useState } from "react";

import { Button } from "@/components/base/buttons/button";
import { errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";

import { FormError } from "./form-error";
import { Modal } from "./modal";

/** Destructive confirmation: states what goes and that it can't be undone. */
export function ConfirmDelete({
  isOpen,
  onClose,
  title,
  description,
  confirmLabel,
  onConfirm,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => Promise<unknown>;
}) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} description={description}>
      <FormError message={error} />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button
          variant="danger"
          leadingIcon={RiDeleteBinLine}
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await onConfirm();
              onClose();
            } catch (err) {
              setError(errorMessage(err, t));
            } finally {
              setBusy(false);
            }
          }}
        >
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
