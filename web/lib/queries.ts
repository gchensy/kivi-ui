"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api, ApiError } from "./api";
import type { Analytics, User } from "./types";

export const meKey = ["auth", "me"] as const;

export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: ({ signal }) => api<User>("/auth/me", { signal }),
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    staleTime: 60_000,
  });
}

export function useAnalytics() {
  return useQuery({
    queryKey: ["analytics", "demo"],
    queryFn: ({ signal }) => api<Analytics>("/analytics/demo", { signal }),
    staleTime: 5 * 60_000,
  });
}

export function useSignOut() {
  const client = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: () => api<void>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      client.clear();
      router.replace("/login");
    },
  });
}
