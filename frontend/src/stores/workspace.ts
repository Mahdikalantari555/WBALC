'use client';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  BandMode,
  DrawingTool,
  LabelInput,
  UncertaintyMethod,
  WorkspaceView,
} from '@/types';
interface WorkspaceState {
  view: WorkspaceView;
  projectId: string;
  selectedSampleId: string | null;
  selectedDatasetId: string | null;
  theme: 'light' | 'dark';
  sidebarOpen: boolean;
  tool: DrawingTool;
  activeClass: string;
  bandMode: BandMode;
  customBands: [number, number, number];
  opacity: number;
  showLabels: boolean;
  showSuggestions: boolean;
  /** Model-derived layers are opt-in: a map that appears unrequested reads as
      the imagery itself rather than a model output. */
  showClassification: boolean;
  showUncertainty: boolean;
  classificationOpacity: number;
  uncertaintyOpacity: number;
  uncertaintyMethod: UncertaintyMethod;
  hiddenClasses: string[];
  drafts: Record<string, LabelInput>;
  mobileReview: boolean;
  setView: (view: WorkspaceView) => void;
  setProject: (id: string) => void;
  selectSample: (id: string | null) => void;
  selectDataset: (id: string | null) => void;
  toggleTheme: () => void;
  setSidebarOpen: (open: boolean) => void;
  setTool: (tool: DrawingTool) => void;
  setActiveClass: (id: string) => void;
  setBandMode: (mode: BandMode) => void;
  setCustomBands: (bands: [number, number, number]) => void;
  setOpacity: (opacity: number) => void;
  toggleLabels: () => void;
  toggleSuggestions: () => void;
  toggleClassification: () => void;
  toggleUncertainty: () => void;
  setClassificationOpacity: (opacity: number) => void;
  setUncertaintyOpacity: (opacity: number) => void;
  setUncertaintyMethod: (method: UncertaintyMethod) => void;
  toggleClassVisibility: (name: string) => void;
  saveDraft: (draft: LabelInput) => void;
  removeDraft: (id: string) => void;
  clearDrafts: () => void;
}
export const useWorkspace = create<WorkspaceState>()(
  persist(
    (set) => ({
      view: 'learning',
      projectId: '',
      selectedSampleId: null,
      selectedDatasetId: null,
      theme: 'light',
      sidebarOpen: false,
      tool: 'pan',
      activeClass: '',
      bandMode: 'true-color',
      customBands: [3, 2, 1],
      opacity: 100,
      showLabels: true,
      showSuggestions: true,
      showClassification: false,
      showUncertainty: false,
      classificationOpacity: 55,
      uncertaintyOpacity: 65,
      uncertaintyMethod: 'entropy',
      hiddenClasses: [],
      drafts: {},
      mobileReview: false,
      setView: (view) => set({ view, sidebarOpen: false }),
      setProject: (projectId) =>
        set({
          projectId,
          selectedSampleId: null,
          selectedDatasetId: null,
          drafts: {},
          view: 'learning',
          bandMode: 'true-color',
          sidebarOpen: false,
          hiddenClasses: [],
        }),
      selectSample: (selectedSampleId) => set({ selectedSampleId }),
      selectDataset: (selectedDatasetId) => set({ selectedDatasetId, bandMode: 'true-color' }),
      toggleTheme: () => set((s) => ({ theme: s.theme === 'light' ? 'dark' : 'light' })),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      setTool: (tool) => set({ tool }),
      setActiveClass: (activeClass) => set({ activeClass }),
      setBandMode: (bandMode) => set({ bandMode }),
      setCustomBands: (customBands) => set({ customBands }),
      setOpacity: (opacity) => set({ opacity }),
      toggleLabels: () => set((s) => ({ showLabels: !s.showLabels })),
      toggleSuggestions: () => set((s) => ({ showSuggestions: !s.showSuggestions })),
      toggleClassification: () =>
        set((s) => ({ showClassification: !s.showClassification })),
      toggleUncertainty: () => set((s) => ({ showUncertainty: !s.showUncertainty })),
      setClassificationOpacity: (classificationOpacity) => set({ classificationOpacity }),
      setUncertaintyOpacity: (uncertaintyOpacity) => set({ uncertaintyOpacity }),
      setUncertaintyMethod: (uncertaintyMethod) => set({ uncertaintyMethod }),
      toggleClassVisibility: (name) =>
        set((s) => ({
          hiddenClasses: s.hiddenClasses.includes(name)
            ? s.hiddenClasses.filter((value) => value !== name)
            : [...s.hiddenClasses, name],
        })),
      saveDraft: (draft) => set((s) => ({ drafts: { ...s.drafts, [draft.sampleId]: draft } })),
      removeDraft: (id) =>
        set((s) => ({
          drafts: Object.fromEntries(Object.entries(s.drafts).filter(([key]) => key !== id)),
        })),
      clearDrafts: () => set({ drafts: {} }),
    }),
    {
      name: 'terralab-workspace-v2',
      partialize: (s) => ({
        theme: s.theme,
        projectId: s.projectId,
        drafts: s.drafts,
        showClassification: s.showClassification,
        showUncertainty: s.showUncertainty,
        classificationOpacity: s.classificationOpacity,
        uncertaintyOpacity: s.uncertaintyOpacity,
        uncertaintyMethod: s.uncertaintyMethod,
      }),
    },
  ),
);
