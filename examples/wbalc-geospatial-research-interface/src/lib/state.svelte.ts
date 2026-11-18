/**
 * Workspace state.
 *
 * Two kinds of state live here and they are deliberately separated:
 *  - *engine state* (projects, datasets, scenes, labels, runs) is fetched from
 *    the adapter and never cached across reloads;
 *  - *client state* (selected project/view/dataset, the pending review batch,
 *    drafts and skips) is per-browser and persisted per project, because the
 *    engine's `/query` is stateless.
 */
import { createContext } from 'svelte';
import { api, ClientError } from './client/api';
import { createLocaleStore } from './i18n/store.svelte';
import type { Locale } from './i18n/locales';
import type {
  DatasetView,
  LabelView,
  MapFieldView,
  ProjectView,
  QueryBatchView,
  QuerySampleView,
  RunView,
  SceneView,
} from './types';

export const views = {
  overview: 'nav.overview',
  map: 'nav.map',
  temporal: 'nav.temporal',
  learning: 'nav.learning',
  arena: 'nav.arena',
  evaluation: 'nav.evaluation',
} as const;

export type ViewId = keyof typeof views;
export type MapLayer = 'imagery' | 'classification' | 'uncertainty' | 'samples';
export type BandMode = 'true-color' | 'false-color' | 'ndvi';
export type UncertaintyMethod = 'entropy' | 'margin' | 'least_confidence';
export type Selection =
  | { kind: 'cell'; row: number; col: number }
  | { kind: 'sample'; sampleId: string };

export interface ReviewDraft {
  className: string;
  at: string;
}

/** Persisted per-project review state: the queue is a cache, not the truth. */
export interface ReviewState {
  batch: QueryBatchView | null;
  decisions: Record<string, { className: string; at: string; sampleId: string }>;
  skipped: string[];
}

const EMPTY_REVIEW: ReviewState = { batch: null, decisions: {}, skipped: [] };

export interface WorkspaceApi {
  locale: ReturnType<typeof createLocaleStore>;
  t: (key: keyof typeof import('./i18n/en').en, params?: Record<string, string | number>) => string;
  notify: (message: string) => void;
  go: (view: ViewId) => void;
  reload: () => Promise<void>;
  selectProject: (id: string) => Promise<void>;
  selectDataset: (id: string) => void;
  boot: () => Promise<void>;
  loadMapField: () => Promise<void>;
  train: (options: {
    resolution: 'patch' | 'pixel';
    evaluationStrategy: 'random' | 'spatial';
    modelType?: 'rf' | 'lightgbm';
    acceptUnverifiedSchema?: boolean;
  }) => Promise<RunView | null>;
  acceptSchemaOverride: () => Promise<void>;
}

class Workspace {
  // ---- routing / chrome
  view = $state<ViewId>('overview');
  loading = $state(true);
  error = $state<{ message: string; status: number } | null>(null);
  toast = $state('');

  // ---- engine data
  projects = $state<ProjectView[]>([]);
  project = $state<ProjectView | null>(null);
  datasets = $state<DatasetView[]>([]);
  scenes = $state<SceneView[]>([]);
  labels = $state<LabelView[]>([]);
  runs = $state<RunView[]>([]);
  datasetId = $state<string | null>(null);
  detailLoading = $state(false);

  // ---- map
  map = $state({
    layers: { imagery: true, classification: true, uncertainty: false, samples: true } as Record<
      MapLayer,
      boolean
    >,
    opacity: 82,
    bandMode: 'true-color' as BandMode,
    method: 'entropy' as UncertaintyMethod,
    selected: null as Selection | null,
  });
  field = $state<{ hard: unknown; uncertainty: unknown }>({ hard: null, uncertainty: null });
  fieldLoading = $state(false);
  fieldError = $state<string | null>(null);
  /** HTTP status of the last field failure: 409 = band-schema conflict. */
  fieldErrorStatus = $state<number | null>(null);
  /**
   * Explicit, per-session acceptance that this raster's bands are what the model
   * expects. It is never inferred: the engine refuses to guess, and the UI only
   * sets this after the operator confirms. Reset whenever the dataset changes.
   */
  schemaOverride = $state(false);

  // ---- review queue (client state, per project)
  review = $state<ReviewState>({ ...EMPTY_REVIEW });
  selectedSample = $state<string | null>(null);

  // ---- training
  training = $state(false);
  engineError = $state<string | null>(null);

  // ---- arena
  arena = $state({ primary: null as string | null, challenger: null as string | null });

  // ---- i18n
  locale: ReturnType<typeof createLocaleStore>;

  constructor(initialLocale: Locale = 'en') {
    this.locale = createLocaleStore(initialLocale);
  }

  get dataset(): DatasetView | null {
    return this.datasets.find((item) => item.id === this.datasetId) ?? this.datasets.at(-1) ?? null;
  }

  get latestRun(): RunView | null {
    return this.runs[0] ?? null;
  }

  get reviewStorageKey(): string {
    return `wbalc:review:${this.project?.id ?? 'none'}`;
  }

  // ------------------------------------------------------------------ errors
  private handleError(error: unknown) {
    if (error instanceof ClientError) {
      this.error = { message: error.message, status: error.status };
    } else {
      this.error = { message: error instanceof Error ? error.message : String(error), status: 500 };
    }
  }

  notify(message: string) {
    this.toast = message;
  }

  go(view: ViewId) {
    if (this.view !== view) {
      this.view = view;
      if (typeof history !== 'undefined') history.replaceState(null, '', `#/${view}`);
      if (typeof window !== 'undefined') window.scrollTo({ top: 0 });
    }
  }

  // -------------------------------------------------------------------- boot
  /** Initial load: projects, then the first (or hash-selected) project. */
  async boot() {
    this.loading = true;
    this.error = null;
    try {
      this.projects = await api.projects();
      const stored = readProjectPreference();
      const target =
        this.projects.find((item) => item.id === stored)?.id ?? this.projects[0]?.id ?? null;
      if (target) await this.loadProject(target);
    } catch (error) {
      this.handleError(error);
    } finally {
      this.loading = false;
    }
  }

  async reload() {
    if (this.project) await this.loadProject(this.project.id);
    else await this.boot();
  }

  async selectProject(id: string) {
    await this.loadProject(id);
    writeProjectPreference(id);
  }

  private async loadProject(id: string) {
    this.detailLoading = true;
    try {
      const project = await api.project(id);
      const [datasets, scenes, labels, runs] = await Promise.all([
        api.datasets(id),
        api.scenes(id),
        api.labels(id),
        api.runs(id),
      ]);
      this.project = project;
      this.datasets = datasets;
      this.scenes = scenes;
      this.labels = labels;
      this.runs = runs;
      this.datasetId = datasets.at(-1)?.id ?? null;
      this.arena = {
        primary: runs[0]?.id ?? null,
        challenger: runs[1]?.id ?? runs[0]?.id ?? null,
      };
      this.field = { hard: null, uncertainty: null };
      this.schemaOverride = false;
      this.fieldErrorStatus = null;
      this.error = null;
      this.restoreReview();
    } catch (error) {
      this.handleError(error);
    } finally {
      this.detailLoading = false;
    }
  }

  selectDataset(id: string) {
    if (this.datasetId === id) return;
    this.datasetId = id;
    this.field = { hard: null, uncertainty: null };
    this.map.selected = null;
    // A different raster is a different band question: never carry an override.
    this.schemaOverride = false;
    this.fieldErrorStatus = null;
  }

  // ------------------------------------------------------------ map layers
  /**
   * Map fields are expensive to compute (a full re-inference on the engine:
   * ~700 ms for a 64×64 grid, more for bigger scenes), and the response is tiny
   * (~30 KB). One field is cached per dataset+layer+method+run, so toggling a
   * layer or revisiting the view does not re-infer; a new run or dataset miss
   * naturally. Failures are never cached.
   */
  private fieldCache = new globalThis.Map<string, MapFieldView>();

  private fieldKey(layer: 'hard' | 'uncertainty', datasetId: string) {
    const run = this.latestRun;
    const method = layer === 'uncertainty' ? this.map.method : 'hard';
    // The override is part of the identity: an overridden field is a different
    // product from a verified one, and both may exist in one session.
    return `${this.project?.id}:${datasetId}:${layer}:${method}:${run?.id ?? 'none'}:${
      this.schemaOverride ? 'override' : 'strict'
    }`;
  }

  /**
   * Record the operator's explicit "these bands are the model's bands" decision
   * and retry the field. The flag is sent to the engine, which stores it with
   * the prediction, so the override is visible in the API and in the export.
   */
  async acceptSchemaOverride() {
    this.schemaOverride = true;
    await this.loadMapField();
  }

  async loadMapField() {
    const dataset = this.dataset;
    if (!dataset || !this.latestRun) return;
    const wantHard = this.map.layers.classification;
    const wantUncertainty = this.map.layers.uncertainty;

    const hardKey = this.fieldKey('hard', dataset.id);
    const uncertaintyKey = this.fieldKey('uncertainty', dataset.id);
    const cachedHard: MapFieldView | null = wantHard
      ? (this.fieldCache.get(hardKey) ?? null)
      : null;
    const cachedUncertainty: MapFieldView | null = wantUncertainty
      ? (this.fieldCache.get(uncertaintyKey) ?? null)
      : null;
    if ((!wantHard || cachedHard) && (!wantUncertainty || cachedUncertainty)) {
      // Everything asked for is already known: no request at all.
      this.field = { hard: cachedHard, uncertainty: cachedUncertainty };
      this.fieldError = null;
      return;
    }

    this.fieldLoading = true;
    this.fieldError = null;
    this.fieldErrorStatus = null;
    try {
      const [hard, uncertainty] = await Promise.all([
        wantHard
          ? api.mapField(this.project!.id, {
              layer: 'hard',
              method: this.map.method,
              datasetId: dataset.id,
              acceptUnverifiedSchema: this.schemaOverride,
            })
          : Promise.resolve(null),
        wantUncertainty
          ? api.mapField(this.project!.id, {
              layer: 'uncertainty',
              method: this.map.method,
              datasetId: dataset.id,
              acceptUnverifiedSchema: this.schemaOverride,
            })
          : Promise.resolve(null),
      ]);
      if (hard) this.fieldCache.set(hardKey, hard);
      if (uncertainty) this.fieldCache.set(uncertaintyKey, uncertainty);
      if (this.fieldCache.size > 8) {
        const oldest = this.fieldCache.keys().next().value;
        if (oldest !== undefined) this.fieldCache.delete(oldest);
      }
      this.field = {
        hard: hard ?? cachedHard ?? this.field.hard,
        uncertainty: uncertainty ?? cachedUncertainty ?? this.field.uncertainty,
      };
    } catch (error) {
      this.fieldError = error instanceof Error ? error.message : String(error);
      this.fieldErrorStatus = error instanceof ClientError ? error.status : 500;
    } finally {
      this.fieldLoading = false;
    }
  }

  // ----------------------------------------------------------- training
  /**
   * Train a checkpoint with an explicit resolution and evaluation protocol.
   *
   * Neither has a UI default hidden in the engine: patch cells are not pixels,
   * and a random holdout over neighbouring patches is not a spatial validation.
   * The caller passes both, and the returned run carries them back.
   */
  async train(options: {
    resolution: 'patch' | 'pixel';
    evaluationStrategy: 'random' | 'spatial';
    modelType?: 'rf' | 'lightgbm';
    acceptUnverifiedSchema?: boolean;
  }): Promise<RunView | null> {
    if (!this.project) return null;
    this.engineError = null;
    this.training = true;
    try {
      const run = await api.train(this.project.id, {
        ...options,
        iteration: (this.runs[0]?.iteration ?? -1) + 1,
      });
      this.runs = [run, ...this.runs.filter((item) => item.id !== run.id)];
      this.arena = { primary: run.id, challenger: this.arena.primary ?? this.runs[1]?.id ?? null };
      // A new run invalidates any map field painted from the previous one.
      this.field = { hard: null, uncertainty: null };
      if (this.map.layers.classification || this.map.layers.uncertainty) void this.loadMapField();
      return run;
    } catch (error) {
      this.engineError = error instanceof Error ? error.message : String(error);
      return null;
    } finally {
      this.training = false;
    }
  }

  // -------------------------------------------------------- review queue
  private restoreReview() {
    this.review = { ...EMPTY_REVIEW };
    if (typeof localStorage === 'undefined' || !this.project) return;
    try {
      const raw = localStorage.getItem(this.reviewStorageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<ReviewState>;
      this.review = {
        batch: parsed.batch ?? null,
        decisions: parsed.decisions ?? {},
        skipped: parsed.skipped ?? [],
      };
    } catch {
      this.review = { ...EMPTY_REVIEW };
    }
  }

  persistReview() {
    if (typeof localStorage === 'undefined' || !this.project) return;
    try {
      localStorage.setItem(this.reviewStorageKey, JSON.stringify(this.review));
    } catch {
      /* Storage disabled: the queue simply does not survive a reload. */
    }
  }

  setBatch(batch: QueryBatchView) {
    this.review = { ...this.review, batch };
    this.persistReview();
  }

  clearBatch() {
    this.review = { ...EMPTY_REVIEW };
    this.selectedSample = null;
    this.persistReview();
  }

  markDecision(sample: QuerySampleView, className: string) {
    this.review.decisions[sample.sampleId] = {
      className,
      at: new Date().toISOString(),
      sampleId: sample.sampleId,
    };
    this.persistReview();
  }

  unmarkDecision(sampleId: string) {
    delete this.review.decisions[sampleId];
    this.persistReview();
  }

  markSkipped(sampleId: string) {
    if (!this.review.skipped.includes(sampleId)) {
      this.review.skipped = [...this.review.skipped, sampleId];
      this.persistReview();
    }
  }

  get pendingCount(): number {
    const batch = this.review.batch;
    if (!batch) return 0;
    return batch.samples.filter((sample) => !this.review.decisions[sample.sampleId]).length;
  }
}

function readProjectPreference(): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem('wbalc:project');
  } catch {
    return null;
  }
}

function writeProjectPreference(id: string) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem('wbalc:project', id);
  } catch {
    /* Ignore: the selection is a convenience, not state the engine needs. */
  }
}

export const [getWorkspace, provideWorkspace] = createContext<Workspace>();

export function createWorkspace(locale: Locale = 'en') {
  return new Workspace(locale);
}

export type { Workspace };

export function viewFromHash(hash: string): ViewId {
  const value = hash.replace(/^#\/?/, '').split('?')[0];
  return Object.prototype.hasOwnProperty.call(views, value) ? (value as ViewId) : 'overview';
}
