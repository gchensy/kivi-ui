"use client";

import { RiLockLine, RiUserLine } from "@remixicon/react";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Button } from "@/components/base/buttons/button";
import { LinkButton } from "@/components/base/buttons/link-button";
import { Input } from "@/components/base/input/input";
import { FormError } from "@/components/kivi/form-error";
import { api, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale } from "@/lib/i18n/messages";
import { meKey } from "@/lib/queries";
import type { User } from "@/lib/types";

function LoginForm() {
  const i18n = useI18n();
  const { t } = i18n;
  const router = useRouter();
  const params = useSearchParams();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const user = await api<User>("/auth/login", {
        body: { username: String(form.get("username") ?? ""), password: String(form.get("password") ?? "") },
      });
      client.setQueryData(meKey, user);
      if (user.locale && user.locale !== i18n.locale && !document.cookie.includes("kivi_locale=")) {
        i18n.setLocale(user.locale as Locale);
      }
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError(errorMessage(err, t));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5">
        <h1 className="text-title-1-medium text-text-primary">{t("auth.signInTitle")}</h1>
        <p className="text-body-regular text-text-secondary">{t("auth.signInDesc")}</p>
      </div>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Input
          name="username"
          label={t("auth.loginName")}
          placeholder={t("auth.loginNamePlaceholder")}
          autoComplete="username"
          leadingIcon={RiUserLine}
          inputDir="ltr"
          isRequired
          autoFocus
        />
        <Input
          name="password"
          type="password"
          label={t("auth.password")}
          placeholder={t("auth.passwordPlaceholder")}
          autoComplete="current-password"
          leadingIcon={RiLockLine}
          isRequired
        />
        <FormError message={error} />
        <Button type="submit" className="mt-1 w-full" disabled={busy}>
          {busy ? t("auth.signingIn") : t("auth.signIn")}
        </Button>
      </form>
      <p className="text-center text-body-regular text-text-secondary">
        {t("auth.noAccount")} <LinkButton href="/signup">{t("auth.createAccount")}</LinkButton>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
