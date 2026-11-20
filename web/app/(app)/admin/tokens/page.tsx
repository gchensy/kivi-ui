"use client";

import { RiAddLine, RiCheckLine, RiFileCopyLine, RiKey2Line } from "@remixicon/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { PageHeader } from "@/components/kivi/app-shell";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { Panel } from "@/components/kivi/panel";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { useStrategies } from "@/lib/queries";
import type { ApiToken } from "@/lib/types";

function CopyButton({ text }: { text: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);
  return (
    <Button
      size="small"
      variant="secondary"
      leadingIcon={copied ? RiCheckLine : RiFileCopyLine}
      onClick={() => {
        navigator.clipboard?.writeText(text).then(() => setCopied(true), () => setCopied(false));
      }}
    >
      {copied ? t("tok.copied") : t("tok.copy")}
    </Button>
  );
}

function CreateTokenModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);
  const [created, setCreated] = useState<ApiToken | null>(null);
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<ApiToken>("/api-tokens", { body }),
    onSuccess: (token) => {
      client.invalidateQueries({ queryKey: ["api-tokens"] });
      setCreated(token);
      setError(null);
    },
    onError: (err) => {
      setError(errorMessage(err, t));
      if (err instanceof ApiError) setInvalid(err.fields);
    },
  });
  const close = () => {
    setCreated(null);
    setError(null);
    setInvalid([]);
    onClose();
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const days = Number(form.get("days") ?? "");
    create.mutate({ name: String(form.get("name") ?? ""), expires_days: days > 0 ? days : null });
  };
  return (
    <Modal isOpen={isOpen} onClose={close} title={created ? t("tok.created") : t("tok.createTitle")} description={created ? t("tok.copyNow") : t("tok.subtitle")}>
      {created?.token ? (
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2 rounded-xl bg-background-secondary-default p-3">
            <code className="min-w-0 flex-1 break-all font-mono text-body-2-medium text-text-primary">{created.token}</code>
            <CopyButton text={created.token} />
          </div>
          <div className="flex justify-end">
            <Button onClick={close}>{t("common.close")}</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
          <Input name="name" label={t("tok.name")} placeholder={t("tok.namePlaceholder")} isRequired isInvalid={invalid.includes("name")} />
          <Input name="days" label={t("tok.expires")} type="number" inputDir="ltr" isInvalid={invalid.includes("expires_days")} />
          <FormError message={error} />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={close}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={create.isPending}>{t("tok.create")}</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function status(token: ApiToken, now: number): "active" | "revoked" | "expired" {
  if (token.revoked_at) return "revoked";
  if (token.expires_at && new Date(token.expires_at).getTime() <= now) return "expired";
  return "active";
}

export default function TokensPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const client = useQueryClient();
  const strategies = useStrategies();
  const tokens = useQuery({ queryKey: ["api-tokens"], queryFn: ({ signal }) => api<ApiToken[]>("/api-tokens", { signal }) });
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<ApiToken | null>(null);
  const [origin, setOrigin] = useState("http://localhost:3000");
  useEffect(() => setOrigin(window.location.origin), []);
  if (tokens.error) return <ErrorState error={tokens.error} onRetry={() => tokens.refetch()} />;
  const now = Date.now();
  const code = strategies.data?.find((s) => s.online)?.code ?? strategies.data?.[0]?.code ?? "RETAIL_APPLY";
  const example = [
    `curl -X POST ${origin}/api/v1/decide/${code} \\`,
    `  -H "Authorization: Bearer kv_…" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{`,
    `    "request_id": "APP-20261120-0001",`,
    `    "data": {`,
    `      "phone": "13800001234", "age": 35, "monthly_income": 9000,`,
    `      "debt_ratio": 0.35, "inquiries_6m": 2, "overdue_24m": 0, "channel": "app"`,
    `    }`,
    `  }'`,
  ].join("\n");

  return (
    <>
      <PageHeader title={t("tok.title")} subtitle={t("tok.subtitle")} actions={<Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("tok.create")}</Button>} />
      <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
        <div className="overflow-x-auto rounded-xl bg-background-primary-default">
          {!tokens.data ? (
            <Skeleton className="h-[200px] rounded-xl" />
          ) : tokens.data.length === 0 ? (
            <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
              <RiKey2Line className="size-8 text-foreground-icon-tertiary" aria-hidden />
              <p className="text-body-regular text-text-secondary">{t("tok.empty")}</p>
            </div>
          ) : (
            <table className="bui-table bui-table-sm">
              <thead>
                <tr>
                  <th>{t("tok.name")}</th>
                  <th>{t("tok.prefix")}</th>
                  <th>{t("tok.status")}</th>
                  <th>{t("tok.lastUsed")}</th>
                  <th>{t("tok.expiresAt")}</th>
                  <th>{t("tok.owner")}</th>
                  <th aria-label={t("common.actions")} />
                </tr>
              </thead>
              <tbody>
                {tokens.data.map((token) => {
                  const s = status(token, now);
                  return (
                    <tr key={token.id} className={s === "active" ? undefined : "opacity-60"}>
                      <td className="text-body-2-medium text-text-primary">{token.name}</td>
                      <td className="font-mono text-caption-1-medium text-text-secondary">{token.prefix}…</td>
                      <td>
                        <Chip variant="subtle" color={s === "active" ? "lime" : s === "revoked" ? "rose" : "neutral"}>{t(`tok.${s}`)}</Chip>
                      </td>
                      <td className="whitespace-nowrap text-text-secondary">
                        {token.last_used_at ? i18n.date(token.last_used_at, { dateStyle: "short", timeStyle: "short" }) : t("common.never")}
                      </td>
                      <td className="whitespace-nowrap text-text-secondary">
                        {token.expires_at ? i18n.date(token.expires_at, { dateStyle: "medium" }) : t("lst.never")}
                      </td>
                      <td className="whitespace-nowrap text-text-tertiary">
                        {token.owner?.display_name ?? "—"} · {i18n.date(token.created_at, { dateStyle: "short" })}
                      </td>
                      <td className="text-end">
                        {s !== "revoked" && (
                          <button
                            type="button"
                            className="rounded-md px-2 py-1 text-body-2-medium text-text-secondary transition-colors hover:bg-background-secondary-hover hover:text-status-rose-text"
                            onClick={() => setRevoking(token)}
                          >
                            {t("tok.revoke")}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <Panel title={t("tok.example")} description={t("stg.apiHint", { code })} actions={<CopyButton text={example} />}>
        <pre className="overflow-x-auto rounded-xl bg-background-primary-default p-3 font-mono text-caption-1-regular text-text-primary shadow-card">{example}</pre>
      </Panel>

      <CreateTokenModal isOpen={creating} onClose={() => setCreating(false)} />
      <ConfirmDelete
        isOpen={!!revoking}
        onClose={() => setRevoking(null)}
        title={t("tok.revokeTitle")}
        description={t("tok.revokeDesc", { name: revoking?.name ?? "" })}
        confirmLabel={t("tok.revoke")}
        onConfirm={async () => {
          if (!revoking) return;
          await api(`/api-tokens/${revoking.id}`, { method: "DELETE" });
          await client.invalidateQueries({ queryKey: ["api-tokens"] });
          setRevoking(null);
        }}
      />
    </>
  );
}
