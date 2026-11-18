'use client';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { LabelInput, Sample } from '@/types';

/**
 * The current review batch per project. RSAL queries are stateless, so the
 * browser owns the queue; submitted status is reconciled with saved labels.
 */
interface ReviewQueueState {
  batches: Record<string, Sample[]>;
  setBatch: (projectId: string, samples: Sample[]) => void;
  mergeBatch: (projectId: string, samples: Sample[]) => void;
  applyDrafts: (projectId: string, drafts: LabelInput[]) => void;
  revertSample: (projectId: string, sampleId: string) => void;
  clearBatch: (projectId: string) => void;
}
export const useReviewQueue = create<ReviewQueueState>()(
  persist(
    (set) => ({
      batches: {},
      setBatch: (projectId, samples) =>
        set((s) => ({ batches: { ...s.batches, [projectId]: samples } })),
      mergeBatch: (projectId, samples) =>
        set((s) => {
          const existing = s.batches[projectId] ?? [];
          const incomingIds = new Set(samples.map((item) => item.id));
          const combined = [
            ...samples,
            ...existing.filter((item) => !incomingIds.has(item.id)),
          ].map((item, idx) => ({ ...item, batchIndex: idx }));
          return { batches: { ...s.batches, [projectId]: combined } };
        }),
      applyDrafts: (projectId, drafts) =>
        set((s) => ({
          batches: {
            ...s.batches,
            [projectId]: (s.batches[projectId] ?? []).map((sample) => {
              const draft = drafts.find((d) => d.sampleId === sample.id);
              return draft
                ? { ...sample, status: draft.status, label: draft.label, note: draft.note }
                : sample;
            }),
          },
        })),
      revertSample: (projectId, sampleId) =>
        set((s) => ({
          batches: {
            ...s.batches,
            [projectId]: (s.batches[projectId] ?? []).map((sample) =>
              sample.id === sampleId
                ? { ...sample, status: 'pending', label: null, saved: false }
                : sample,
            ),
          },
        })),
      clearBatch: (projectId) =>
        set((s) => ({
          batches: Object.fromEntries(Object.entries(s.batches).filter(([k]) => k !== projectId)),
        })),
    }),
    { name: 'terralab-review-queue-v1' },
  ),
);
