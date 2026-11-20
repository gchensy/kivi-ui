"use client";

import { RiCheckboxCircleFill, RiTimeLine } from "@remixicon/react";
import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Button, ButtonLink } from "@/components/base/buttons/button";
import { LinkButton } from "@/components/base/buttons/link-button";
import { Input } from "@/components/base/input/input";
import { FormError } from "@/components/kivi/form-error";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import type { User } from "@/lib/types";


type Field = "username" | "email" | "password" | "display_name" | "confirm";

export default function SignupPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const config = useQuery({
    queryKey: ["auth", "config"],
    queryFn: () => api<{ signup_mode: "approval" | "open" | "closed" }>("/auth/config"),
  });
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<Set<Field>>(new Set());
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ user: User; requires_approval: boolean } | null>(null);
  const mode = config.data?.signup_mode;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const value = (k: string) => String(form.get(k) ?? "");
    if (value("password") !== value("confirm")) {
      setInvalid(new Set(["confirm"]));
      setError(t("auth.passwordMismatch"));
      return;
    }
    setBusy(true);
    setError(null);
    setInvalid(new Set());
    try {
      const result = await api<{ user: User; requires_approval: boolean }>("/auth/signup", {
        body: {
          username: value("username"),
          email: value("email"),
          display_name: value("display_name"),
          password: value("password"),
          locale: i18n.locale,
        },
      });
      setDone(result);
    } catch (err) {
      if (err instanceof ApiError) {
        const fields = new Set<Field>(err.fields as Field[]);
        if (err.code === "username_taken") fields.add("username");
        if (err.code === "email_taken") fields.add("email");
        setInvalid(fields);
      }
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    const Icon = done.requires_approval ? RiTimeLine : RiCheckboxCircleFill;
    return (
      <div className="flex flex-col items-start gap-5">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-linear-to-b from-accent-500 to-accent-600">
          <Icon className="size-6 text-white" aria-hidden />
        </span>
        <div className="flex flex-col gap-1.5">
          <h1 className="text-title-1-medium text-text-primary">
            {done.requires_approval ? t("auth.pendingTitle") : t("auth.activeTitle")}
          </h1>
          <p className="text-body-regular text-text-secondary">
            {t(done.requires_approval ? "auth.pendingDesc" : "auth.activeDesc", { username: done.user.username })}
          </p>
        </div>
        <ButtonLink href="/login" className="w-full">
          {t("auth.backToSignIn")}
        </ButtonLink>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-title-1-medium text-text-primary">{t("auth.signUpTitle")}</h1>
        <p className="text-body-regular text-text-secondary">
          {mode === "open" ? t("auth.signUpDescOpen") : t("auth.signUpDesc")}
        </p>
      </div>
      {mode === "closed" ? (
        <FormError message={t("auth.signupClosed")} />
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <Input name="display_name" label={t("auth.displayName")} placeholder={t("auth.displayNamePlaceholder")} autoComplete="name" isRequired isInvalid={invalid.has("display_name")} />
          <Input
            name="username"
            label={t("auth.username")}
            placeholder={t("auth.usernamePlaceholder")}
            hint={t("auth.usernameHint")}
            autoComplete="username"
            inputDir="ltr"
            isRequired
            isInvalid={invalid.has("username")}
          />
          <Input name="email" type="email" label={t("auth.email")} placeholder={t("auth.emailPlaceholder")} autoComplete="email" isRequired isInvalid={invalid.has("email")} />
          <Input
            name="password"
            type="password"
            label={t("auth.newPassword")}
            hint={t("auth.passwordHint")}
            autoComplete="new-password"
            isRequired
            isInvalid={invalid.has("password")}
          />
          <Input name="confirm" type="password" label={t("auth.confirmPassword")} placeholder={t("auth.confirmPlaceholder")} autoComplete="new-password" isRequired isInvalid={invalid.has("confirm")} />
          <FormError message={error} />
          <Button type="submit" className="mt-1 w-full" disabled={busy}>
            {busy ? t("auth.signingUp") : t("auth.signUp")}
          </Button>
        </form>
      )}
      <p className="text-center text-body-regular text-text-secondary">
        {t("auth.haveAccount")} <LinkButton href="/login">{t("auth.goSignIn")}</LinkButton>
      </p>
    </div>
  );
}
