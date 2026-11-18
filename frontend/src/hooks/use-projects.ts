'use client';
import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/utils';
import { useReviewQueue } from '@/stores/review-queue';
import type {
  CreateProjectInput,
  LabelInput,
  MapLayer,
  Sample,
  SceneUploadMetadata,
  SomClassifyInput,
  SomQueryOptions,
  UncertaintyMethod,
} from '@/types';
export const keys = {
  projects: ['projects'] as const,
  dataset: (id: string) => ['project', id, 'dataset'] as const,
  scenes: (id: string) => ['project', id, 'scenes'] as const,
  labels: (id: string) => ['project', id, 'labels'] as const,
  metrics: (id: string) => ['project', id, 'metrics'] as const,
  mapField: (
    id: string,
    layer: MapLayer,
    method: UncertaintyMethod,
    datasetId: string | undefined,
  ) => ['project', id, 'map', layer, method, datasetId ?? 'all'] as const,
  som: (id: string, datasetId?: string, size?: number) =>
    ['project', id, 'som', datasetId ?? 'latest', size ?? 'auto'] as const,
  somClassify: (id: string, input: SomClassifyInput) =>
    [
      'project',
      id,
      'som-classify',
      input.datasetId ?? 'latest',
      input.rows,
      input.cols,
      input.nClusters ?? 'neurons',
      input.epochs ?? 50,
      input.resolution ?? 'pixel',
    ] as const,
};

/**
 * A model-derived map layer. Keyed by dataset + layer + method so switching the
 * uncertainty method or the active dataset reuses or refetches exactly one field.
 */
export function useMapField(
  id: string,
  options: {
    layer: MapLayer;
    method: UncertaintyMethod;
    datasetId: string | undefined;
    enabled: boolean;
  },
) {
  return useQuery({
    queryKey: keys.mapField(id, options.layer, options.method, options.datasetId),
    queryFn: () => api.mapField(id, options),
    enabled: !!id && options.enabled,
    staleTime: 60_000,
    retry: 0,
  });
}
export function useProjects() {
  return useQuery({ queryKey: keys.projects, queryFn: api.projects });
}
export function useDatasets(id: string) {
  return useQuery({ queryKey: keys.dataset(id), queryFn: () => api.dataset(id), enabled: !!id });
}
export function useScenes(id: string) {
  return useQuery({ queryKey: keys.scenes(id), queryFn: () => api.scenes(id), enabled: !!id });
}
export function useUploadScene(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, metadata }: { file: File; metadata: SceneUploadMetadata }) =>
      api.uploadScene(id, file, metadata),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.scenes(id) });
      await client.invalidateQueries({ queryKey: keys.projects });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
}
export function useDeleteScene(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sceneId: string) => api.deleteScene(id, sceneId),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.scenes(id) }),
    onError: (error) => toast.error(errorMessage(error)),
  });
}
const EMPTY: Sample[] = [];
/**
 * Review queue (persisted locally) merged with the backend's saved labels.
 * Saved labels make labeled patches visible on the map and correctable;
 * batch entries win on id collisions so positions/predictions stay intact.
 */
export function useSamples(id: string) {
  const batch = useReviewQueue((s) => s.batches[id]) ?? EMPTY;
  const saved = useQuery({
    queryKey: keys.labels(id),
    queryFn: () => api.savedLabels(id),
    enabled: !!id,
  });
  const data = useMemo(() => {
    const savedLabels = saved.data ?? EMPTY;
    const byId = new Map(savedLabels.map((s) => [s.id, s]));
    const merged: Sample[] = batch.map((s) => {
      const stored = byId.get(s.id);
      return stored
        ? { ...s, status: 'labeled' as const, label: stored.label, saved: true }
        : s;
    });
    const batchIds = new Set(batch.map((s) => s.id));
    for (const s of savedLabels) if (!batchIds.has(s.id)) merged.push(s);
    return merged;
  }, [batch, saved.data]);
  return {
    data,
    isLoading: !!id && saved.isLoading,
    error: saved.error,
    refetch: saved.refetch,
  };
}
export function useMetrics(id: string) {
  return useQuery({ queryKey: keys.metrics(id), queryFn: () => api.metrics(id), enabled: !!id });
}
export function useSom(
  id: string,
  options?: { datasetId?: string; size?: number; enabled?: boolean },
) {
  const datasetId = options?.datasetId;
  const size = options?.size;
  return useQuery({
    queryKey: keys.som(id, datasetId, size),
    queryFn: () =>
      api.som(id, {
        datasetId,
        rows: size,
        cols: size,
      }),
    enabled: !!id && (options?.enabled ?? true),
  });
}
export function useUnsupervisedSom(
  id: string,
  input: SomClassifyInput,
  enabled = true,
) {
  return useQuery({
    queryKey: keys.somClassify(id, input),
    queryFn: () => api.somClassify(id, input),
    enabled: !!id && enabled,
    staleTime: Infinity,
  });
}
export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateProjectInput) => api.createProject(input),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.projects }),
    onError: (e) => toast.error(errorMessage(e)),
  });
}
export function useQueryBatch(id: string) {
  const setBatch = useReviewQueue((s) => s.setBatch);
  const mergeBatch = useReviewQueue((s) => s.mergeBatch);
  return useMutation({
    mutationFn: ({
      batchSize,
      strategy,
      datasetId,
      options,
    }: {
      batchSize: number;
      strategy: string;
      datasetId?: string;
      options?: SomQueryOptions;
      merge?: boolean;
    }) => api.query(id, batchSize, strategy, datasetId, options),
    onSuccess: (result, variables) => {
      if (variables.merge) mergeBatch(id, result.samples);
      else setBatch(id, result.samples);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
export function useSaveLabels(id: string) {
  const client = useQueryClient();
  const applyDrafts = useReviewQueue((s) => s.applyDrafts);
  return useMutation({
    mutationFn: (labels: LabelInput[]) => api.labels(id, labels),
    onSuccess: async (_result, labels) => {
      applyDrafts(id, labels);
      await Promise.all([
        client.invalidateQueries({ queryKey: ['project', id] }),
        client.invalidateQueries({ queryKey: keys.projects }),
        client.invalidateQueries({ queryKey: ['project', id, 'map'] }),
      ]);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
export function useDeleteLabel(id: string) {
  const client = useQueryClient();
  const revertSample = useReviewQueue((s) => s.revertSample);
  return useMutation({
    mutationFn: (sampleId: string) => api.deleteLabel(id, sampleId),
    onSuccess: async (_result, sampleId) => {
      revertSample(id, sampleId);
      await Promise.all([
        client.invalidateQueries({ queryKey: ['project', id] }),
        client.invalidateQueries({ queryKey: keys.projects }),
        client.invalidateQueries({ queryKey: ['project', id, 'map'] }),
      ]);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
export function useTrain(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.train(id),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['project', id] }),
        client.invalidateQueries({ queryKey: keys.projects }),
        // Classification/uncertainty fields are keyed by dataset+layer+method,
        // not by iteration, so without this a visible layer keeps painting the
        // *previous* model's output after training (and still calls it fresh).
        client.invalidateQueries({ queryKey: ['project', id, 'map'] }),
      ]);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
export function useUpload(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress: (n: number) => void }) =>
      api.upload(id, file, onProgress),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.dataset(id) });
      await client.invalidateQueries({ queryKey: keys.projects });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
export function useDeleteDataset(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (datasetId: string) => api.deleteDataset(id, datasetId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['project', id] }),
        client.invalidateQueries({ queryKey: keys.projects }),
      ]);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
