import { createContext } from 'svelte';
import { getObservation, latest, observations, seededReviews, type ModelId, type Reviews, type SensorFilter } from './data/research';

export const pages = {
  overview: 'Overview',
  map: 'Geospatial Workspace',
  temporal: 'Temporal Analysis',
  learning: 'Active Learning',
  arena: 'Model Arena',
  evaluation: 'Results & Evaluation',
} as const;

export type Page = keyof typeof pages;
export type MapLayer = 'imagery' | 'classification' | 'boundary' | 'samples';
export type Basemap = 'satellite' | 'terrain';
export type Selection = { kind: 'water' | 'vegetation' | 'boundary' } | { kind: 'sample'; id: string };

export interface ResearchState {
  page: Page;
  observation: string;
  reference: string;
  sensor: SensorFilter;
  model: ModelId;
  challenger: ModelId;
  reviews: Reviews;
  selectedSample: string | null;
  map: {
    layers: Record<MapLayer, boolean>;
    opacity: number;
    basemap: Basemap;
    selected: Selection | null;
  };
}

export interface WorkspaceProps {
  go: (page: Page) => void;
  notify: (message: string) => void;
}

export const [getWorkspace, provideWorkspace] = createContext<ResearchState>();

export function createState(): ResearchState {
  const workspace = $state<ResearchState>({
    page: 'map', observation: latest.date, reference: observations[0].date, sensor: 'all',
    model: 'fusion', challenger: 'unet', reviews: { ...seededReviews }, selectedSample: null,
    map: { layers: { imagery: true, classification: true, boundary: true, samples: true }, opacity: 82, basemap: 'satellite', selected: { kind: 'water' } },
  });
  return workspace;
}

export function pageFromHash(hash: string): Page {
  const value = hash.replace(/^#\/?/, '');
  return Object.prototype.hasOwnProperty.call(pages, value) ? value as Page : 'map';
}

export function filterSensor(workspace: ResearchState, sensor: SensorFilter) {
  workspace.sensor = sensor;
  if (sensor === 'all' || getObservation(workspace.observation).sensor === sensor) return;
  const date = Date.parse(workspace.observation);
  const candidates = observations.filter(item => item.sensor === sensor);
  workspace.observation = candidates.reduce((nearest, item) =>
    Math.abs(Date.parse(item.date) - date) < Math.abs(Date.parse(nearest.date) - date) ? item : nearest).date;
}

export function selectModel(workspace: ResearchState, model: ModelId, side: 'primary' | 'challenger' = 'primary') {
  if (side === 'challenger') {
    if (workspace.model === model) workspace.model = workspace.challenger;
    workspace.challenger = model;
  } else {
    if (workspace.challenger === model) workspace.challenger = workspace.model;
    workspace.model = model;
  }
}