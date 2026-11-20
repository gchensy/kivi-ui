"use client";

import type { ReactNode } from "react";
import { Dialog, Heading, Modal as AriaModal, ModalOverlay } from "react-aria-components";

import { CloseButton } from "@/components/base/buttons/close-button";
import { useI18n } from "@/lib/i18n/provider";

/** A centred dialog on BoardUI surfaces, built on React Aria's modal primitives. */
export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <ModalOverlay
      isOpen={isOpen}
      onOpenChange={(open) => !open && onClose()}
      isDismissable
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 data-[entering]:animate-in data-[entering]:fade-in"
    >
      <AriaModal className="w-full max-w-[440px] rounded-3xl border border-border-button-default bg-background-primary-default p-6 shadow-2xl outline-none dark:bg-background-secondary-default">
        <Dialog className="flex flex-col gap-5 outline-none">
          <div className="flex items-start justify-between gap-3">
            <div className="flex flex-col gap-1">
              <Heading slot="title" className="text-title-3-semibold text-text-primary">
                {title}
              </Heading>
              {description && <p className="text-body-2-regular text-text-secondary">{description}</p>}
            </div>
            <CloseButton size="xs" aria-label={t("common.close")} onClick={onClose} />
          </div>
          {children}
        </Dialog>
      </AriaModal>
    </ModalOverlay>
  );
}
