"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api, ApiError } from "./api";
import type {
  Analytics,
  Dataset,
  DatasetDetail,
  FieldOptions,
  IndicatorDetail,
  IndicatorPage,
  ModelDetail,
  RiskList,
  RiskModel,
  StrategyDetail,
  StrategyItem,
  StrategyVersionDetail,
  User,
  VersionDetail,
} from "./types";

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

export function useDatasets() {
  return useQuery({ queryKey: ["datasets"], queryFn: ({ signal }) => api<Dataset[]>("/datasets", { signal }) });
}

export function useDataset(id: string) {
  return useQuery({ queryKey: ["datasets", id], queryFn: ({ signal }) => api<DatasetDetail>(`/datasets/${id}`, { signal }) });
}

export function useIndicators(params: URLSearchParams) {
  const qs = params.toString();
  return useQuery({
    queryKey: ["indicators", "list", qs],
    queryFn: ({ signal }) => api<IndicatorPage>(`/indicators${qs ? `?${qs}` : ""}`, { signal }),
  });
}

export function useIndicator(id: string) {
  return useQuery({ queryKey: ["indicators", id], queryFn: ({ signal }) => api<IndicatorDetail>(`/indicators/${id}`, { signal }) });
}

export function useModels() {
  return useQuery({ queryKey: ["models"], queryFn: ({ signal }) => api<RiskModel[]>("/models", { signal }) });
}

export function useModel(id: string) {
  return useQuery({
    queryKey: ["models", id],
    queryFn: ({ signal }) => api<ModelDetail>(`/models/${id}`, { signal }),
    refetchInterval: (query) => (query.state.data?.versions.some((v) => v.status === "training") ? 2000 : false),
  });
}

export function useVersion(id: string) {
  return useQuery({
    queryKey: ["versions", id],
    queryFn: ({ signal }) => api<VersionDetail>(`/model-versions/${id}`, { signal }),
    refetchInterval: (query) => (query.state.data?.status === "training" ? 1500 : false),
  });
}

export function useStrategies() {
  return useQuery({ queryKey: ["strategies"], queryFn: ({ signal }) => api<StrategyItem[]>("/strategies", { signal }) });
}

export function useStrategy(id: string) {
  return useQuery({ queryKey: ["strategies", id], queryFn: ({ signal }) => api<StrategyDetail>(`/strategies/${id}`, { signal }) });
}

export function useStrategyVersion(id: string) {
  return useQuery({ queryKey: ["strategy-versions", id], queryFn: ({ signal }) => api<StrategyVersionDetail>(`/strategy-versions/${id}`, { signal }) });
}

export function useFieldOptions(datasetId?: string) {
  return useQuery({
    queryKey: ["strategies", "fields", datasetId ?? ""],
    queryFn: ({ signal }) => api<FieldOptions>(`/strategies/fields${datasetId ? `?dataset_id=${datasetId}` : ""}`, { signal }),
    staleTime: 60_000,
  });
}

export function useLists() {
  return useQuery({ queryKey: ["risk-lists"], queryFn: ({ signal }) => api<RiskList[]>("/risk-lists", { signal }) });
}
