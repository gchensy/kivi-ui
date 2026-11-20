"use client";

import {
  RiAlarmWarningLine,
  RiCloseLine,
  RiDashboardLine,
  RiDatabase2Line,
  RiFileList3Line,
  RiFlowChart,
  RiGitBranchLine,
  RiKey2Line,
  RiLogoutBoxRLine,
  RiPulseLine,
  RiRadarLine,
  RiRulerLine,
  RiSettings4Line,
  RiSideBarFill,
  RiStackLine,
  RiTeamLine,
  RiUserForbidLine,
} from "@remixicon/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ComponentType } from "react";

import { ThemeToggle } from "@/components/application/theme/theme-toggle";
import { Avatar } from "@/components/base/avatar/avatar";
import { Badge } from "@/components/base/badges/badge";
import { Dropdown, DropdownDivider, DropdownItem, DropdownPopover, DropdownTrigger } from "@/components/base/dropdown/dropdown";
import { initials } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { useSignOut } from "@/lib/queries";
import type { User } from "@/lib/types";
import { cx } from "@/utils/cx";

import { LocaleToggle } from "./locale-toggle";
import { KiviMark } from "./logo";

type IconComponent = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;

interface NavEntry {
  href: string;
  key: string;
  icon: IconComponent;
  soon?: boolean;
  badge?: number;
}

interface NavGroup {
  key: string;
  items: NavEntry[];
  adminOnly?: boolean;
}

export function navGroups(pendingUsers?: number, activeAlerts?: number): NavGroup[] {
  return [
    { key: "", items: [{ href: "/", key: "overview", icon: RiDashboardLine }] },
    {
      key: "dataGroup",
      items: [
        { href: "/data", key: "data", icon: RiDatabase2Line },
        { href: "/indicators", key: "indicators", icon: RiRulerLine },
      ],
    },
    {
      key: "analysis",
      items: [
        { href: "/models", key: "models", icon: RiStackLine },
        { href: "/stability", key: "stability", icon: RiPulseLine },
        { href: "/monitors", key: "monitors", icon: RiRadarLine },
        { href: "/alerts", key: "alerts", icon: RiAlarmWarningLine, badge: activeAlerts || undefined },
      ],
    },
    {
      key: "management",
      items: [
        { href: "/strategies", key: "strategies", icon: RiFlowChart },
        { href: "/lists", key: "lists", icon: RiUserForbidLine },
        { href: "/decisions", key: "decisions", icon: RiGitBranchLine },
      ],
    },
    {
      key: "system",
      adminOnly: true,
      items: [
        { href: "/admin/users", key: "users", icon: RiTeamLine, badge: pendingUsers || undefined },
        { href: "/admin/tokens", key: "tokens", icon: RiKey2Line },
        { href: "/admin/audit", key: "audit", icon: RiFileList3Line },
      ],
    },
  ];
}

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function NavLink({ entry, collapsed, active, onNavigate }: { entry: NavEntry; collapsed: boolean; active: boolean; onNavigate?: () => void }) {
  const { t } = useI18n();
  const label = t(`nav.${entry.key}`);
  const body = (
    <>
      <span className="flex min-w-0 items-center gap-2">
        <entry.icon className={cx("size-5 shrink-0", active ? "text-white" : "text-foreground-icon-secondary")} aria-hidden />
        <span
          className={cx(
            "overflow-hidden text-body-medium whitespace-nowrap transition-[max-width,opacity] duration-300",
            collapsed ? "max-w-0 opacity-0" : "max-w-[160px] opacity-100",
            active ? "text-white" : entry.soon ? "text-text-tertiary" : "text-text-secondary",
          )}
        >
          {label}
        </span>
      </span>
      {!collapsed && entry.soon && (
        <span className="rounded-md bg-background-tertiary-default px-1.5 py-px text-caption-2-medium text-text-tertiary">{t("common.soon")}</span>
      )}
      {!collapsed && entry.badge !== undefined && <Badge color={active ? "primary" : "neutral"}>{entry.badge}</Badge>}
    </>
  );
  const className = cx(
    "flex items-center justify-between overflow-hidden rounded-2lg p-2 outline-none transition-[width,background-color] duration-300 focus-visible:ring-2 focus-visible:ring-border-focus-ring",
    collapsed ? "w-9" : "w-full",
    active ? "bg-linear-to-b from-accent-500 to-accent-600 shadow-nav-selected" : entry.soon ? "cursor-default" : "hover:bg-background-secondary-hover",
  );
  if (entry.soon) {
    return (
      <span className={className} aria-disabled title={`${label} · ${t("common.soon")}`}>
        {body}
      </span>
    );
  }
  return (
    <Link href={entry.href} className={className} aria-current={active ? "page" : undefined} title={collapsed ? label : undefined} onClick={onNavigate}>
      {body}
    </Link>
  );
}

function UserMenu({ user, collapsed }: { user: User; collapsed: boolean }) {
  const { t } = useI18n();
  const signOut = useSignOut();
  return (
    <Dropdown>
      <DropdownTrigger
        aria-label={t("nav.account")}
        className={cx(
          "flex cursor-pointer items-center gap-2.5 rounded-2xl text-start outline-none transition-colors hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring",
          collapsed ? "justify-center p-0" : "w-full bg-background-primary-default p-2 shadow-card",
        )}
      >
        <Avatar size="sm" color={user.role === "admin" ? "blue" : "lime"} initials={initials(user.display_name)} />
        {!collapsed && (
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-body-medium text-text-primary">{user.display_name}</span>
            <span className="truncate text-caption-1-regular text-text-tertiary">
              {t(`users.${user.role}`)} · {user.username}
            </span>
          </span>
        )}
      </DropdownTrigger>
      <DropdownPopover aria-label={t("nav.account")} placement="top start" className="w-[240px]">
        <div className="flex flex-col gap-0.5 px-2 py-1.5">
          <span className="truncate text-body-medium text-text-primary">{user.display_name}</span>
          <span className="truncate text-caption-1-regular text-text-tertiary">{user.email}</span>
        </div>
        <DropdownDivider />
        <Link href="/settings" className="contents">
          <DropdownItem>
            <span className="flex items-center gap-2">
              <RiSettings4Line className="size-5 text-foreground-icon-secondary" aria-hidden />
              {t("nav.settings")}
            </span>
          </DropdownItem>
        </Link>
        <DropdownItem onSelect={() => signOut.mutate()}>
          <span className="flex items-center gap-2">
            <RiLogoutBoxRLine className="size-5 text-foreground-icon-secondary" aria-hidden />
            {t("nav.signOut")}
          </span>
        </DropdownItem>
      </DropdownPopover>
    </Dropdown>
  );
}

export function Sidebar({
  user,
  pendingUsers,
  activeAlerts,
  mobile = false,
  onClose,
  className,
}: {
  user: User;
  pendingUsers?: number;
  activeAlerts?: number;
  mobile?: boolean;
  onClose?: () => void;
  className?: string;
}) {
  const { t } = useI18n();
  const pathname = usePathname() ?? "/";
  const [collapsedState, setCollapsed] = useState(false);
  const collapsed = mobile ? false : collapsedState;
  const groups = navGroups(pendingUsers, activeAlerts).filter((g) => !g.adminOnly || user.role === "admin");

  return (
    <aside
      className={cx(
        "flex h-full shrink-0 flex-col justify-between overflow-hidden rounded-3xl border border-border-button-white bg-background-secondary-default shadow-sidebar transition-[width] duration-300",
        collapsed ? "w-[60px] px-[11px] py-3" : "w-[260px] p-3",
        className,
      )}
    >
      {/* The nav scrolls on short windows; it ends at the controls below and fades out instead of being cut mid-line. */}
      <div className="-mx-2 -mt-2 flex min-h-0 w-[calc(100%+16px)] flex-col gap-4 overflow-y-auto px-2 pt-2 pb-6 [mask-image:linear-gradient(to_bottom,black_calc(100%-28px),transparent)] [scrollbar-width:none]">
        <div className={cx("flex items-center", collapsed ? "flex-col-reverse gap-3" : "justify-between gap-2")}>
          <Link href="/" className="flex min-w-0 items-center gap-2.5 rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring">
            <KiviMark className={collapsed ? "size-9" : undefined} />
            {!collapsed && (
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-headline-semibold text-text-primary">{t("common.appName")}</span>
                <span className="truncate text-caption-1-regular text-text-tertiary">{t("common.engine")}</span>
              </span>
            )}
          </Link>
          {mobile ? (
            <button type="button" aria-label={t("nav.closeNav")} onClick={onClose} className="cursor-pointer text-foreground-icon-secondary">
              <RiCloseLine className="size-5" aria-hidden />
            </button>
          ) : (
            <button
              type="button"
              aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
              aria-expanded={!collapsed}
              onClick={() => setCollapsed(!collapsedState)}
              className={cx("cursor-pointer text-foreground-icon-secondary", collapsed && "flex w-9 justify-center")}
            >
              <RiSideBarFill className={cx("size-5", collapsed ? "" : "-scale-x-100")} aria-hidden />
            </button>
          )}
        </div>

        <nav className="flex flex-col gap-4">
          {groups.map((group) => (
            <div key={group.key || "home"} className="flex flex-col gap-1">
              {group.key && !collapsed && (
                <span className="px-2 pb-0.5 text-caption-1-medium text-text-tertiary">{t(`nav.${group.key}`)}</span>
              )}
              {group.key && collapsed && <span className="mx-auto mb-1 h-px w-6 bg-separator-border" aria-hidden />}
              {group.items.map((entry) => (
                <NavLink key={entry.key} entry={entry} collapsed={collapsed} active={!entry.soon && isActive(pathname, entry.href)} onNavigate={onClose} />
              ))}
            </div>
          ))}
        </nav>
      </div>

      <div className="flex shrink-0 flex-col gap-3 pt-3">
        {collapsed ? (
          <div className="flex flex-col items-center gap-2">
            <LocaleToggle collapsed />
            <ThemeToggle collapsed />
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <LocaleToggle />
            <ThemeToggle appearance="sidebar-segmented" />
          </div>
        )}
        <UserMenu user={user} collapsed={collapsed} />
      </div>
    </aside>
  );
}
