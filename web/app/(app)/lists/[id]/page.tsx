"use client";

import { RiAddLine, RiCloseCircleLine, RiDeleteBinLine, RiSearchLine } from "@remixicon/react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Pagination } from "@/components/base/pagination/pagination";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { Notice } from "@/components/kivi/notice";
import { Panel } from "@/components/kivi/panel";
import { ErrorState, PageSkeleton, Skeleton } from "@/components/kivi/states";
import { api, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName } from "@/lib/indicators";
import { LIST_KIND_CHIP } from "@/lib/lists";
import { useMe } from "@/lib/queries";
import type { ListItem, RiskList } from "@/lib/types";

const SIZE = 20;
const ROW_ACTION =
  "rounded-md px-2 py-1 text-body-2-medium text-text-secondary transition-colors hover:bg-background-secondary-hover hover:text-status-rose-text disabled:opacity-50";

function AddItemsModal({ list, isOpen, onClose, onDone }: { list: RiskList; isOpen: boolean; onClose: () => void; onDone: (text: string) => void }) {
  const { t } = useI18n();
  const client = useQueryClient();
  const [values, setValues] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<{ added: number; skipped: number }>(`/risk-lists/${list.id}/items`, { body }),
    onSuccess: (r) => {
      client.invalidateQueries({ queryKey: ["risk-lists"] });
      setValues("");
      setError(null);
      onClose();
      onDone(t("lst.added", { added: r.added, skipped: r.skipped }));
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const lines = values.split(/[\n,;]+/).map((v) => v.trim()).filter(Boolean);
    if (!lines.length) {
      setError(t("errors.validation_error"));
      return;
    }
    const days = Number(form.get("days") ?? "");
    const expires = days > 0 ? new Date(Date.now() + days * 86_400_000).toISOString() : null;
    add.mutate({ values: lines, reason: String(form.get("reason") ?? ""), expires_at: expires });
  };
  const count = values.split(/[\n,;]+/).filter((v) => v.trim()).length;
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("lst.addTitle")} description={t("lst.addDesc")}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Textarea label={`${t("lst.values")} · ${count}`} value={values} onChange={setValues} rows={6} placeholder={list.dimension === "phone" ? "13800001234\n13900005678" : undefined} />
        <div className="grid grid-cols-2 gap-3">
          <Input name="reason" label={t("lst.reason")} />
          <Input name="days" label={t("lst.expiresDays")} type="number" inputDir="ltr" />
        </div>
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={add.isPending}>{t("lst.add")}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function ListPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["risk-lists", id], queryFn: ({ signal }) => api<RiskList>(`/risk-lists/${id}`, { signal }) });
  const params = new URLSearchParams({ page: String(page), size: String(SIZE) });
  if (search.trim()) params.set("q", search.trim());
  const items = useQuery({
    queryKey: ["risk-lists", id, "items", page, search.trim()],
    queryFn: ({ signal }) => api<{ items: ListItem[]; total: number }>(`/risk-lists/${id}/items?${params}`, { signal }),
    placeholderData: keepPreviousData,
  });
  const [removing, setRemoving] = useState<ListItem | null>(null);

  if (list.error) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;
  if (!list.data || !me.data) return <PageSkeleton />;
  const l = list.data;
  const canDelete = me.data.role === "admin" || l.owner?.id === me.data.id;
  const now = Date.now();

  return (
    <>
      <PageHeader
        title={indicatorName(l, i18n.locale)}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{l.code}</code>
            <Chip variant="subtle" color={LIST_KIND_CHIP[l.kind]}>{t(`lst.kinds.${l.kind}`)}</Chip>
            <Chip variant="subtle" color="neutral">{t(`lst.dimensions.${l.dimension}`)}</Chip>
            <span>{t("lst.entries", { n: i18n.num(l.item_count) })} · {t("lst.active", { n: i18n.num(l.active_count) })}</span>
          </span>
        }
        actions={
          <>
            {canDelete && (
              <Button variant="secondary" leadingIcon={RiDeleteBinLine} onClick={() => setDeleting(true)}>
                {t("lst.deleteList")}
              </Button>
            )}
            <Button leadingIcon={RiAddLine} onClick={() => setAdding(true)}>{t("lst.add")}</Button>
          </>
        }
      />
      {l.description && <p className="mx-1 text-body-regular text-text-secondary">{l.description}</p>}

      <Panel title={t("lst.items")} description={t("lst.subtitle")}>
        <div className="flex flex-col gap-3">
          <Input
            aria-label={t("common.search")}
            placeholder={t("lst.checkPlaceholder")}
            leadingIcon={RiSearchLine}
            value={search}
            onChange={(v) => {
              setSearch(v);
              setPage(1);
            }}
            inputDir="ltr"
            size="small"
            className="w-[280px]"
          />
          <div className="overflow-x-auto rounded-xl bg-background-primary-default">
            {!items.data ? (
              <Skeleton className="h-[320px] rounded-xl" />
            ) : (
              <table className={`bui-table bui-table-sm ${items.isFetching ? "opacity-60" : ""} transition-opacity`}>
                <thead>
                  <tr>
                    <th>{t("lst.value")}</th>
                    <th>{t("lst.reason")}</th>
                    <th>{t("lst.expiresAt")}</th>
                    <th>{t("lst.addedBy")}</th>
                    <th aria-label={t("common.actions")} />
                  </tr>
                </thead>
                <tbody>
                  {items.data.items.map((item) => {
                    const expired = item.expires_at !== null && new Date(item.expires_at).getTime() <= now;
                    return (
                      <tr key={item.id} className={expired ? "opacity-60" : undefined}>
                        <td className="font-mono text-body-2-medium text-text-primary">{item.value_masked}</td>
                        <td className="max-w-[280px] truncate text-text-secondary">{item.reason || "—"}</td>
                        <td className="whitespace-nowrap text-text-secondary">
                          {item.expires_at ? (
                            <span className="flex items-center gap-2">
                              {i18n.date(item.expires_at, { dateStyle: "medium" })}
                              {expired && <Chip variant="caption" color="neutral">{t("tok.expired")}</Chip>}
                            </span>
                          ) : (
                            t("lst.never")
                          )}
                        </td>
                        <td className="whitespace-nowrap text-text-tertiary">
                          {item.author?.display_name ?? "—"} · {i18n.date(item.created_at, { dateStyle: "short", timeStyle: "short" })}
                        </td>
                        <td className="text-end">
                          <button type="button" className={ROW_ACTION} onClick={() => setRemoving(item)}>
                            {t("lst.remove")}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {items.data.items.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-10 text-center text-text-tertiary">
                        {search.trim() ? (
                          <span className="inline-flex items-center gap-1.5">
                            <RiCloseCircleLine className="size-4" aria-hidden />
                            {t("lst.notListed")}
                          </span>
                        ) : (
                          t("common.noData")
                        )}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
          {items.data && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-body-2-regular text-text-tertiary">{t("common.total", { n: items.data.total })}</span>
              {items.data.total > SIZE && <Pagination page={page} totalPages={Math.ceil(items.data.total / SIZE)} onChange={setPage} />}
            </div>
          )}
        </div>
      </Panel>

      <AddItemsModal list={l} isOpen={adding} onClose={() => setAdding(false)} onDone={setNotice} />
      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("lst.deleteList")}
        description={t("lst.deleteListDesc", { name: indicatorName(l, i18n.locale) })}
        confirmLabel={t("lst.deleteList")}
        onConfirm={async () => {
          await api(`/risk-lists/${l.id}`, { method: "DELETE" });
          await client.invalidateQueries({ queryKey: ["risk-lists"] });
          router.replace("/lists");
        }}
      />
      <ConfirmDelete
        isOpen={!!removing}
        onClose={() => setRemoving(null)}
        title={t("lst.removeTitle")}
        description={t("lst.removeDesc", { value: removing?.value_masked ?? "" })}
        confirmLabel={t("lst.remove")}
        onConfirm={async () => {
          if (!removing) return;
          await api(`/risk-lists/${id}/items/${removing.id}`, { method: "DELETE" });
          await client.invalidateQueries({ queryKey: ["risk-lists"] });
          setRemoving(null);
        }}
      />
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}
