"use client";

import {
  RiAddLine,
  RiKey2Line,
  RiMore2Fill,
  RiSearchLine,
  RiShieldStarLine,
  RiUserForbidLine,
  RiUserFollowLine,
  RiUserLine,
} from "@remixicon/react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { Avatar } from "@/components/base/avatar/avatar";
import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Dropdown, DropdownDivider, DropdownItem, DropdownPopover, DropdownTrigger } from "@/components/base/dropdown/dropdown";
import { Input } from "@/components/base/input/input";
import { Pagination } from "@/components/base/pagination/pagination";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Select, SelectItem } from "@/components/base/select/select";
import { PageHeader } from "@/components/kivi/app-shell";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { Notice } from "@/components/kivi/notice";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { api, ApiError, errorMessage } from "@/lib/api";
import { initials } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { useMe } from "@/lib/queries";
import type { Role, User, UserPage, UserStatus } from "@/lib/types";

const SIZE = 10;
type Filter = "all" | UserStatus;

const STATUS_CHIP: Record<UserStatus, "yellow" | "lime" | "neutral"> = { pending: "yellow", active: "lime", disabled: "neutral" };

function CreateUserModal({ isOpen, onClose, onCreated }: { isOpen: boolean; onClose: () => void; onCreated: (user: User) => void }) {
  const { t } = useI18n();
  const i18n = useI18n();
  const [role, setRole] = useState<Role>("analyst");
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);
  const create = useMutation({
    mutationFn: (body: Record<string, string>) => api<User>("/users", { body }),
    onSuccess: (user) => {
      setError(null);
      onCreated(user);
    },
    onError: (err) => {
      setError(errorMessage(err, t));
      if (err instanceof ApiError) setInvalid([...err.fields, ...(err.code === "username_taken" ? ["username"] : []), ...(err.code === "email_taken" ? ["email"] : [])]);
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      username: String(form.get("username") ?? ""),
      email: String(form.get("email") ?? ""),
      display_name: String(form.get("display_name") ?? ""),
      password: String(form.get("password") ?? ""),
      role,
      locale: i18n.locale,
    });
  };
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("users.createTitle")} description={t("users.createDesc")}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Input name="display_name" label={t("auth.displayName")} placeholder={t("auth.displayNamePlaceholder")} isRequired isInvalid={invalid.includes("display_name")} />
        <Input name="username" label={t("auth.username")} placeholder={t("auth.usernamePlaceholder")} hint={t("auth.usernameHint")} inputDir="ltr" isRequired isInvalid={invalid.includes("username")} />
        <Input name="email" type="email" label={t("auth.email")} placeholder={t("auth.emailPlaceholder")} isRequired isInvalid={invalid.includes("email")} />
        <Input name="password" type="password" label={t("auth.newPassword")} hint={t("auth.passwordHint")} autoComplete="new-password" isRequired isInvalid={invalid.includes("password")} />
        <div className="flex flex-col gap-1.5">
          <span className="text-body-medium text-text-secondary">{t("users.role")}</span>
          <Select aria-label={t("users.role")} selectedKey={role} onSelectionChange={(key) => key && setRole(key as Role)}>
            <SelectItem id="analyst" textValue={t("users.analyst")}>{t("users.analyst")}</SelectItem>
            <SelectItem id="admin" textValue={t("users.admin")}>{t("users.admin")}</SelectItem>
          </Select>
        </div>
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={create.isPending}>{create.isPending ? t("common.saving") : t("users.create")}</Button>
        </div>
      </form>
    </Modal>
  );
}

function ResetPasswordModal({ user, onClose, onDone }: { user: User | null; onClose: () => void; onDone: (user: User) => void }) {
  const { t } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const reset = useMutation({
    mutationFn: (password: string) => api<User>(`/users/${user?.id}/reset-password`, { body: { new_password: password } }),
    onSuccess: (u) => {
      setError(null);
      onDone(u);
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  return (
    <Modal isOpen={user !== null} onClose={onClose} title={t("users.resetTitle", { name: user?.display_name ?? "" })} description={t("users.resetDesc")}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          reset.mutate(String(new FormData(event.currentTarget).get("password") ?? ""));
        }}
        className="flex flex-col gap-4"
        noValidate
      >
        <Input name="password" type="password" label={t("users.newPassword")} hint={t("auth.passwordHint")} autoComplete="new-password" isRequired />
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={reset.isPending}>{t("users.resetPassword")}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function UsersPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const client = useQueryClient();
  const me = useMe();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [resetting, setResetting] = useState<User | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQ(search.trim());
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const params = new URLSearchParams({ page: String(page), size: String(SIZE) });
  if (filter !== "all") params.set("status", filter);
  if (q) params.set("q", q);
  const list = useQuery({
    queryKey: ["users", "list", filter, q, page],
    queryFn: () => api<UserPage>(`/users?${params}`),
    placeholderData: keepPreviousData,
  });

  const refresh = () => client.invalidateQueries({ queryKey: ["users"] });
  const update = useMutation({
    mutationFn: ({ user, changes }: { user: User; changes: Partial<Pick<User, "role" | "status">> }) =>
      api<User>(`/users/${user.id}`, { method: "PATCH", body: changes }),
    onSuccess: (user) => {
      setActionError(null);
      setNotice(t("users.updated", { name: user.display_name }));
      refresh();
    },
    onError: (err) => setActionError(errorMessage(err, t)),
  });

  if (list.error) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;
  const data = list.data;
  const counts = data?.counts ?? { pending: 0, active: 0, disabled: 0 };
  const total = counts.pending + counts.active + counts.disabled;
  const filters: { id: Filter; count: number }[] = [
    { id: "all", count: total },
    { id: "pending", count: counts.pending },
    { id: "active", count: counts.active },
    { id: "disabled", count: counts.disabled },
  ];

  return (
    <>
      <PageHeader
        title={t("users.title")}
        subtitle={t("users.subtitle")}
        actions={<Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("users.create")}</Button>}
      />

      {counts.pending > 0 && filter !== "pending" && (
        <button
          type="button"
          onClick={() => {
            setFilter("pending");
            setPage(1);
          }}
          className="mx-1 flex cursor-pointer items-center gap-2 rounded-xl bg-status-yellow-background px-3 py-2 text-start text-body-2-medium text-status-yellow-text"
        >
          <RiUserFollowLine className="size-4" aria-hidden />
          {t("users.pendingBanner", { n: counts.pending })}
        </button>
      )}

      <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SegmentedControl
            aria-label={t("users.status")}
            selectedKeys={new Set([filter])}
            onSelectionChange={(keys) => {
              const next = [...keys][0] as Filter | undefined;
              if (next) {
                setFilter(next);
                setPage(1);
              }
            }}
          >
            {filters.map((f) => (
              <SegmentedControlItem key={f.id} id={f.id}>
                <span className="flex items-center gap-1.5">
                  {t(`users.${f.id}`)}
                  <span className="text-caption-1-medium text-text-tertiary tabular-nums">{f.count}</span>
                </span>
              </SegmentedControlItem>
            ))}
          </SegmentedControl>
          <Input
            aria-label={t("common.search")}
            placeholder={t("users.searchPlaceholder")}
            leadingIcon={RiSearchLine}
            value={search}
            onChange={setSearch}
            size="small"
            className="w-full sm:w-[280px]"
          />
        </div>
        <FormError message={actionError} />

        <div className="overflow-x-auto rounded-xl bg-background-primary-default">
          {!data ? (
            <Skeleton className="h-[320px] rounded-xl" />
          ) : (
            <table className={`bui-table ${list.isFetching ? "opacity-60" : ""} transition-opacity`}>
              <thead>
                <tr>
                  <th>{t("users.user")}</th>
                  <th>{t("users.role")}</th>
                  <th>{t("users.status")}</th>
                  <th>{t("users.lastLogin")}</th>
                  <th>{t("users.createdAt")}</th>
                  <th className="!text-end">{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((user) => {
                  const self = user.id === me.data?.id;
                  return (
                    <tr key={user.id}>
                      <td>
                        <div className="flex items-center gap-2.5">
                          <Avatar size="sm" color={user.role === "admin" ? "blue" : "lime"} initials={initials(user.display_name)} />
                          <div className="flex min-w-0 flex-col">
                            <span className="truncate text-body-medium text-text-primary">
                              {user.display_name}
                              {self && <span className="text-text-tertiary"> ({t("common.you")})</span>}
                            </span>
                            <span className="truncate text-caption-1-regular text-text-tertiary">
                              {user.username} · {user.email}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="flex items-center gap-1.5 text-body-2-medium text-text-secondary">
                          {user.role === "admin" ? <RiShieldStarLine className="size-4 text-foreground-icon-secondary" aria-hidden /> : <RiUserLine className="size-4 text-foreground-icon-secondary" aria-hidden />}
                          {t(`users.${user.role}`)}
                        </span>
                      </td>
                      <td>
                        <Chip variant="subtle" color={STATUS_CHIP[user.status]}>{t(`users.${user.status}`)}</Chip>
                      </td>
                      <td className="text-body-2-regular text-text-secondary">
                        {user.last_login_at ? i18n.date(user.last_login_at) : t("common.never")}
                      </td>
                      <td className="text-body-2-regular text-text-secondary">{i18n.date(user.created_at, { dateStyle: "medium" })}</td>
                      <td>
                        <div className="flex items-center justify-end gap-1.5">
                          {user.status === "pending" && (
                            <Button size="small" leadingIcon={RiUserFollowLine} onClick={() => update.mutate({ user, changes: { status: "active" } })}>
                              {t("users.activate")}
                            </Button>
                          )}
                          <Dropdown>
                            <DropdownTrigger
                              aria-label={t("users.more")}
                              className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-foreground-icon-secondary outline-none hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
                            >
                              <RiMore2Fill className="size-5" aria-hidden />
                            </DropdownTrigger>
                            <DropdownPopover aria-label={t("users.more")} placement="bottom end" className="w-[200px]">
                              {!self && (
                                <DropdownItem onSelect={() => update.mutate({ user, changes: { role: user.role === "admin" ? "analyst" : "admin" } })}>
                                  <span className="flex items-center gap-2">
                                    <RiShieldStarLine className="size-4 text-foreground-icon-secondary" aria-hidden />
                                    {user.role === "admin" ? t("users.makeAnalyst") : t("users.makeAdmin")}
                                  </span>
                                </DropdownItem>
                              )}
                              {!self && user.status !== "pending" && (
                                <DropdownItem onSelect={() => update.mutate({ user, changes: { status: user.status === "active" ? "disabled" : "active" } })}>
                                  <span className="flex items-center gap-2">
                                    {user.status === "active" ? (
                                      <RiUserForbidLine className="size-4 text-foreground-icon-secondary" aria-hidden />
                                    ) : (
                                      <RiUserFollowLine className="size-4 text-foreground-icon-secondary" aria-hidden />
                                    )}
                                    {user.status === "active" ? t("users.disable") : t("users.enable")}
                                  </span>
                                </DropdownItem>
                              )}
                              {!self && <DropdownDivider />}
                              <DropdownItem onSelect={() => setResetting(user)}>
                                <span className="flex items-center gap-2">
                                  <RiKey2Line className="size-4 text-foreground-icon-secondary" aria-hidden />
                                  {t("users.resetPassword")}
                                </span>
                              </DropdownItem>
                            </DropdownPopover>
                          </Dropdown>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-text-tertiary">{t("common.noData")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        {data && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-body-2-regular text-text-tertiary">{t("common.total", { n: data.total })}</span>
            {data.total > SIZE && <Pagination page={page} totalPages={Math.ceil(data.total / SIZE)} onChange={setPage} />}
          </div>
        )}
      </section>

      <CreateUserModal
        isOpen={creating}
        onClose={() => setCreating(false)}
        onCreated={(user) => {
          setCreating(false);
          setNotice(t("users.created", { name: user.display_name }));
          refresh();
        }}
      />
      <ResetPasswordModal
        user={resetting}
        onClose={() => setResetting(null)}
        onDone={(user) => {
          setResetting(null);
          setNotice(t("users.reset", { name: user.display_name }));
        }}
      />
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}
