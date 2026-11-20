"use client";

import { RiCheckLine } from "@remixicon/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ThemeToggle } from "@/components/application/theme/theme-toggle";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { PageHeader } from "@/components/kivi/app-shell";
import { FormError } from "@/components/kivi/form-error";
import { LocaleToggle } from "@/components/kivi/locale-toggle";
import { Panel } from "@/components/kivi/panel";
import { api, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { meKey, useMe } from "@/lib/queries";
import type { User } from "@/lib/types";

function Saved({ show, text }: { show: boolean; text: string }) {
  if (!show) return null;
  return (
    <span role="status" className="flex items-center gap-1 text-body-2-medium text-status-lime-text">
      <RiCheckLine className="size-4" aria-hidden />
      {text}
    </span>
  );
}

export default function SettingsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const client = useQueryClient();
  const me = useMe();
  const [profileError, setProfileError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [saved, setSaved] = useState<"profile" | "password" | null>(null);

  const profile = useMutation({
    mutationFn: (body: Record<string, string>) => api<User>("/auth/me", { method: "PATCH", body }),
    onSuccess: (user) => {
      client.setQueryData(meKey, user);
      setProfileError(null);
      setSaved("profile");
    },
    onError: (err) => setProfileError(errorMessage(err, t)),
  });
  const password = useMutation({
    mutationFn: (body: Record<string, string>) => api<User>("/auth/password", { body }),
    onSuccess: () => {
      setPasswordError(null);
      setSaved("password");
    },
    onError: (err) => setPasswordError(errorMessage(err, t)),
  });

  if (!me.data) return null;
  const user = me.data;

  const submitProfile = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaved(null);
    profile.mutate({ display_name: String(form.get("display_name") ?? ""), email: String(form.get("email") ?? "") });
  };
  const submitPassword = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const target = event.currentTarget;
    const form = new FormData(target);
    setSaved(null);
    if (form.get("new_password") !== form.get("confirm")) {
      setPasswordError(t("auth.passwordMismatch"));
      return;
    }
    password.mutate(
      { current_password: String(form.get("current_password") ?? ""), new_password: String(form.get("new_password") ?? "") },
      { onSuccess: () => target.reset() },
    );
  };

  return (
    <>
      <PageHeader title={t("settings.title")} subtitle={t("settings.subtitle")} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={t("settings.profile")} description={t("settings.profileDesc")}>
          <form onSubmit={submitProfile} className="flex flex-col gap-4" noValidate>
            <Input name="display_name" label={t("auth.displayName")} defaultValue={user.display_name} isRequired />
            <Input name="email" type="email" label={t("auth.email")} defaultValue={user.email} isRequired />
            <Input label={t("auth.username")} value={user.username} isReadOnly isDisabled />
            <FormError message={profileError} />
            <div className="flex items-center justify-end gap-3">
              <Saved show={saved === "profile"} text={t("settings.saved")} />
              <Button type="submit" disabled={profile.isPending}>{profile.isPending ? t("common.saving") : t("common.save")}</Button>
            </div>
          </form>
        </Panel>

        <Panel title={t("settings.password")} description={t("settings.passwordDesc")}>
          <form onSubmit={submitPassword} className="flex flex-col gap-4" noValidate>
            <Input name="current_password" type="password" label={t("settings.currentPassword")} autoComplete="current-password" isRequired />
            <Input name="new_password" type="password" label={t("settings.newPassword")} hint={t("auth.passwordHint")} autoComplete="new-password" isRequired />
            <Input name="confirm" type="password" label={t("settings.confirmPassword")} autoComplete="new-password" isRequired />
            <FormError message={passwordError} />
            <div className="flex items-center justify-end gap-3">
              <Saved show={saved === "password"} text={t("settings.changed")} />
              <Button type="submit" disabled={password.isPending}>{t("settings.changePassword")}</Button>
            </div>
          </form>
        </Panel>

        <Panel title={t("settings.preferences")} description={t("settings.preferencesDesc")}>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <span className="text-body-medium text-text-secondary">{t("common.language")}</span>
              <div className="w-full max-w-[280px]">
                <LocaleToggle />
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-body-medium text-text-secondary">{t("common.theme")}</span>
              <div className="w-full max-w-[280px]">
                <ThemeToggle appearance="segmented" />
              </div>
            </div>
          </div>
        </Panel>

      </div>
    </>
  );
}
