'use client';
import dynamic from 'next/dynamic';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Database,
  Download,
  Eye,
  EyeOff,
  FileImage,
  Grid2x2,
  LoaderCircle,
  Maximize,
  Minus,
  Plus,
  Scan,
  Shrink,
  Sparkles,
  Target,
} from 'lucide-react';
import { toast } from 'sonner';
import { useDatasets, useUnsupervisedSom } from '@/hooks/use-projects';
import {
  decodeClusterRaster,
  renderClusterOverlay,
  renderRaster,
} from '@/lib/geotiff';
import { cn, downloadCSV, downloadJSON, formatNumber } from '@/lib/utils';
import { useWorkspace } from '@/stores/workspace';
import { Button } from './ui/button';
import { Badge, EmptyState, ErrorState, Skeleton } from './ui/common';
import type {
  BandMode,
  Project,
  SomClusterSummary,
  SomPaletteMode,
} from '@/types';
import type { SomMapAction } from './map/som-cluster-map';

const SomClusterMap = dynamic(() => import('./map/som-cluster-map'), {
  ssr: false,
  loading: () => (
    <div className="map-loading">
      <LoaderCircle className="spin" size={25} />
      <span>Preparing unsupervised map…</span>
    </div>
  ),
});

function rgbToHex([r, g, b]: [number, number, number]): string {
  return `#${[r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')}`;
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  const num = Number.parseInt(clean, 16);
  if (Number.isNaN(num)) return [52, 142, 98];
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

function topologicalColor(
  cluster: SomClusterSummary,
  rows: number,
  cols: number,
): [number, number, number] {
  if (!cluster.neurons.length) return cluster.color;
  const meanR =
    cluster.neurons.reduce((acc, [r]) => acc + r, 0) /
    cluster.neurons.length /
    Math.max(rows - 1, 1);
  const meanC =
    cluster.neurons.reduce((acc, [, c]) => acc + c, 0) /
    cluster.neurons.length /
    Math.max(cols - 1, 1);
  const r = Math.round(44 + meanR * 176);
  const g = Math.round(172 - meanR * 64 + meanC * 44);
  const b = Math.round(74 + (1 - meanR) * 76 + meanC * 92);
  return [
    Math.max(0, Math.min(255, r)),
    Math.max(0, Math.min(255, g)),
    Math.max(0, Math.min(255, b)),
  ];
}

function spectralColor(cluster: SomClusterSummary): [number, number, number] {
  const p = cluster.bandProfile;
  const p0 = p[0] ?? 0.5;
  const p1 = p[1] ?? p0;
  const p2 = p[2] ?? (p.length === 2 ? (p0 + p1) * 0.5 : p0);
  return [
    Math.round(36 + p0 * 204),
    Math.round(40 + p1 * 198),
    Math.round(42 + p2 * 196),
  ];
}

export function UnsupervisedSom({ project }: { project: Project }) {
  const {
    data: datasets = [],
    isLoading: datasetsLoading,
    error: datasetsError,
    refetch: retryDatasets,
  } = useDatasets(project.id);
  const { selectedDatasetId, selectDataset, setView } = useWorkspace();

  const dataset =
    datasets.find((d) => d.id === selectedDatasetId) ?? datasets[datasets.length - 1] ?? null;

  const defaultClusters = Math.min(Math.max(project.classes.length || 4, 2), 8);

  // Draft form controls + applied SOM configuration
  const [gridSide, setGridSide] = useState(4);
  const [clusterTarget, setClusterTarget] = useState<string>(String(defaultClusters));
  const [epochs, setEpochs] = useState(50);
  const [resolution, setResolution] = useState<'pixel' | 'patch'>('pixel');

  const [applied, setApplied] = useState<{
    rows: number;
    cols: number;
    nClusters: number | null;
    epochs: number;
    resolution: 'pixel' | 'patch';
  }>({
    rows: 4,
    cols: 4,
    nClusters: defaultClusters,
    epochs: 50,
    resolution: 'pixel',
  });

  // Map display controls
  const [bandMode, setBandMode] = useState<BandMode>('true-color');
  const [paletteMode, setPaletteMode] = useState<SomPaletteMode>('distinct');
  const [clusterOpacity, setClusterOpacity] = useState(74);
  const [showClusters, setShowClusters] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [action, setAction] = useState<SomMapAction | null>(null);
  const [manifoldView, setManifoldView] = useState<'clusters' | 'u-matrix'>('clusters');

  // Interactive cluster customization (custom names, colors, solo/hidden)
  const [customNames, setCustomNames] = useState<Record<number, string>>({});
  const [customColors, setCustomColors] = useState<Record<number, [number, number, number]>>({});
  const [hiddenIds, setHiddenIds] = useState<number[]>([]);
  const [soloId, setSoloId] = useState<number | null>(null);

  const somQuery = useUnsupervisedSom(
    project.id,
    {
      datasetId: dataset?.id,
      rows: applied.rows,
      cols: applied.cols,
      nClusters: applied.nClusters,
      epochs: applied.epochs,
      resolution: applied.resolution,
    },
    !!dataset,
  );

  const result = somQuery.data;

  // Base satellite GeoTIFF rendering
  const baseRaster = useQuery({
    queryKey: ['raster', dataset?.id, bandMode],
    queryFn: async () => {
      if (!dataset) return null;
      const response = await fetch(dataset.url);
      if (!response.ok) throw new Error('The satellite GeoTIFF could not be loaded.');
      return renderRaster(await response.arrayBuffer(), bandMode);
    },
    enabled: !!dataset,
    staleTime: Infinity,
    retry: 0,
  });

  // Classified SOM GeoTIFF decoding (cached per exportId)
  const decodedSom = useQuery({
    queryKey: ['som-tiff', result?.exportId, result?.downloadUrl],
    queryFn: async () => {
      if (!result) return null;
      const response = await fetch(result.downloadUrl);
      if (!response.ok) throw new Error('The classified SOM raster could not be loaded.');
      return decodeClusterRaster(await response.arrayBuffer());
    },
    enabled: !!result,
    staleTime: Infinity,
    retry: 0,
  });

  const resolvedColors = useMemo(() => {
    const map: Record<number, [number, number, number]> = {};
    if (!result) return map;
    for (const c of result.clusters) {
      if (paletteMode === 'distinct') {
        map[c.clusterId] = customColors[c.clusterId] ?? c.color;
      } else if (paletteMode === 'topological') {
        map[c.clusterId] = topologicalColor(c, result.rows, result.cols);
      } else {
        map[c.clusterId] = spectralColor(c);
      }
    }
    return map;
  }, [result, paletteMode, customColors]);

  const visibleSet = useMemo(() => {
    if (!result) return null;
    if (soloId !== null && soloId < result.nClusters) {
      return new Set<number>([soloId]);
    }
    if (hiddenIds.length > 0) {
      const hidden = new Set(hiddenIds);
      return new Set(
        result.clusters.map((c) => c.clusterId).filter((cid) => !hidden.has(cid)),
      );
    }
    return null;
  }, [result, soloId, hiddenIds]);

  const clusterOverlayUrl = useMemo(() => {
    if (!decodedSom.data || !result) return null;
    return renderClusterOverlay(decodedSom.data, resolvedColors, visibleSet);
  }, [decodedSom.data, result, resolvedColors, visibleSet]);

  const runSom = () => {
    const maxNeurons = gridSide * gridSide;
    const parsedTarget =
      clusterTarget === 'neurons'
        ? null
        : Math.min(Number(clusterTarget), maxNeurons);
    const next = {
      rows: gridSide,
      cols: gridSide,
      nClusters: parsedTarget,
      epochs,
      resolution,
    };
    setSoloId(null);
    setHiddenIds([]);
    if (
      next.rows === applied.rows &&
      next.cols === applied.cols &&
      next.nClusters === applied.nClusters &&
      next.epochs === applied.epochs &&
      next.resolution === applied.resolution
    ) {
      somQuery.refetch();
    } else {
      setApplied(next);
    }
  };

  const changeBandMode = (nextMode: BandMode) => {
    if ((nextMode === 'false-color' || nextMode === 'ndvi') && dataset && dataset.bands < 4) {
      toast.info('This view needs at least four spectral bands (including NIR).');
      return;
    }
    setBandMode(nextMode);
  };

  const toggleHideCluster = (cid: number) => {
    setSoloId(null);
    setHiddenIds((prev) =>
      prev.includes(cid) ? prev.filter((x) => x !== cid) : [...prev, cid],
    );
  };

  const clusterLabel = (c: SomClusterSummary) =>
    customNames[c.clusterId]?.trim() || c.label;

  const command = (kind: SomMapAction['kind']) =>
    setAction({ kind, nonce: Date.now() });

  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span />
            UNSUPERVISED CLASSIFICATION · ZERO LABELS NEEDED
          </div>
          <h1>Self-organizing map</h1>
          <p>
            Cluster satellite pixels directly by spectral signature into a georeferenced land-cover
            map.
          </p>
        </div>
        <div className="heading-actions">
          <Button
            variant="outline"
            disabled={!result}
            onClick={() =>
              result &&
              downloadCSV(
                [
                  [
                    'cluster_id',
                    'name',
                    'pixel_count',
                    'area_share_pct',
                    ...Array.from(
                      { length: result.clusters[0]?.bandMeans.length ?? 0 },
                      (_, b) => `band_${b + 1}_mean`,
                    ),
                  ],
                  ...result.clusters.map((c) => [
                    c.clusterId,
                    clusterLabel(c),
                    c.pixelCount,
                    (c.fraction * 100).toFixed(2),
                    ...c.bandMeans.map((v) => v.toFixed(3)),
                  ]),
                ],
                `${project.id}-unsupervised-som.csv`,
              )
            }
          >
            <Download size={15} />
            Export CSV
          </Button>
          <Button
            variant="outline"
            disabled={!result}
            onClick={() =>
              result &&
              downloadJSON(
                {
                  project: project.name,
                  exportedAt: new Date().toISOString(),
                  ...result,
                  clusters: result.clusters.map((c) => ({
                    ...c,
                    label: clusterLabel(c),
                    color: resolvedColors[c.clusterId] ?? c.color,
                  })),
                },
                `${project.id}-unsupervised-som.json`,
              )
            }
          >
            <Download size={15} />
            Export JSON
          </Button>
          {result ? (
            <Button asChild>
              <a href={result.downloadUrl} download>
                <Download size={15} />
                Download GeoTIFF
              </a>
            </Button>
          ) : (
            <Button disabled>
              <Download size={15} />
              Download GeoTIFF
            </Button>
          )}
        </div>
      </div>

      {result && (
        <div className="metric-grid unsup-kpi-row">
          <article className="metric-card">
            <div className="metric-top">
              <span>Unsupervised classes</span>
              <Badge>
                {result.rows}×{result.cols} SOM
              </Badge>
            </div>
            <strong>{result.nClusters}</strong>
            <p>
              {result.nClusters === result.rows * result.cols
                ? 'Direct Kohonen neuron clusters'
                : 'Merged from SOM manifold prototypes'}
            </p>
          </article>
          <article className="metric-card">
            <div className="metric-top">
              <span>Classified {result.resolution === 'pixel' ? 'pixels' : 'patches'}</span>
              <Badge>{result.resolution === 'pixel' ? 'Full raster' : 'Patch grid'}</Badge>
            </div>
            <strong>{formatNumber(result.totalValid)}</strong>
            <p>
              {result.shape[1]}×{result.shape[0]} map
              {result.nodataCount > 0 ? ` · ${formatNumber(result.nodataCount)} nodata` : ''}
            </p>
          </article>
          <article className="metric-card">
            <div className="metric-top">
              <span>Quantization error</span>
              <Badge>{result.epochs} epochs</Badge>
            </div>
            <strong>{result.quantizationError.toFixed(3)}</strong>
            <p>Mean spectral distance to winning neuron</p>
          </article>
          <article className="metric-card">
            <div className="metric-top">
              <span>Topographic error</span>
              <Badge>Topology</Badge>
            </div>
            <strong>{(result.topographicError * 100).toFixed(1)}%</strong>
            <p>Neighborhood continuity on 2D lattice</p>
          </article>
        </div>
      )}

      {datasetsError ? (
        <ErrorState message={datasetsError.message} onRetry={() => retryDatasets()} />
      ) : datasetsLoading ? (
        <div className="labeling-grid unsup-workspace-grid">
          <Skeleton className="workspace-skeleton" />
          <Skeleton className="workspace-skeleton" />
        </div>
      ) : !dataset ? (
        <div className="map-card map-empty">
          <EmptyState
            title="Upload a GeoTIFF to run unsupervised SOM classification"
            description="No training labels are needed — upload any multi-band GeoTIFF and Kohonen SOM will cluster every pixel automatically."
            action={
              <Button onClick={() => setView('datasets')}>
                <Database size={16} />
                Upload imagery
              </Button>
            }
          />
        </div>
      ) : (
        <div className="unsup-workspace-grid">
          <div className={cn('map-card unsup-map-card', expanded && 'is-expanded')}>
            <div className="map-card-header">
              <span className="dataset-file-icon">
                <FileImage size={17} />
              </span>
              <div className="map-dataset-select">
                <select
                  aria-label="Active satellite dataset"
                  value={dataset.id}
                  onChange={(e) => selectDataset(e.target.value)}
                >
                  {datasets.map((d) => (
                    <option value={d.id} key={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <span>
                  {dataset.bands} bands · {dataset.width}×{dataset.height}px · {dataset.crs}
                </span>
              </div>
              <div className="unsup-header-controls">
                <button
                  type="button"
                  className={cn('unsup-toggle-btn', showClusters && 'active')}
                  onClick={() => setShowClusters((v) => !v)}
                  title={showClusters ? 'Hide SOM overlay to inspect raw imagery' : 'Show SOM overlay'}
                >
                  {showClusters ? <Eye size={14} /> : <EyeOff size={14} />}
                  <span>{showClusters ? 'SOM overlay on' : 'Original scene'}</span>
                </button>
                <button
                  className="icon-button"
                  aria-label={expanded ? 'Exit expanded map' : 'Expand map'}
                  onClick={() => setExpanded((v) => !v)}
                >
                  {expanded ? <Shrink size={17} /> : <Maximize size={17} />}
                </button>
              </div>
            </div>

            <div className="map-canvas-wrap">
              <SomClusterMap
                dataset={dataset}
                rasterUrl={baseRaster.data ?? dataset.previewUrl}
                clusterOverlayUrl={clusterOverlayUrl}
                baseOpacity={100}
                clusterOpacity={clusterOpacity}
                showClusters={showClusters}
                action={action}
              />

              {(somQuery.isFetching || decodedSom.isFetching || baseRaster.isFetching) && (
                <div className="raster-loading">
                  <LoaderCircle className="spin" size={15} />
                  {somQuery.isFetching
                    ? 'Self-organizing spectral clusters…'
                    : 'Rendering classification map…'}
                </div>
              )}

              <div className="map-top-left unsup-map-top-left">
                <div className="band-selector">
                  <span className="rgb-icon">
                    <i />
                    <i />
                    <i />
                  </span>
                  <select
                    value={bandMode}
                    onChange={(e) => changeBandMode(e.target.value as BandMode)}
                    aria-label="Base imagery band combination"
                  >
                    <option value="true-color">True color (RGB)</option>
                    <option value="false-color">False color (NIR)</option>
                    <option value="ndvi">NDVI vegetation</option>
                  </select>
                </div>

                <div className="unsup-palette-pills" role="tablist" aria-label="Cluster palette">
                  {(
                    [
                      { id: 'distinct', label: 'Distinct' },
                      { id: 'topological', label: 'Topological' },
                      { id: 'spectral', label: 'Spectral' },
                    ] as const
                  ).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      role="tab"
                      aria-selected={paletteMode === item.id}
                      className={cn(paletteMode === item.id && 'active')}
                      onClick={() => setPaletteMode(item.id)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="map-top-right">
                <button
                  className="map-float-button"
                  onClick={() => command('in')}
                  title="Zoom in"
                  aria-label="Zoom in"
                >
                  <Plus size={17} />
                </button>
                <button
                  className="map-float-button"
                  onClick={() => command('out')}
                  title="Zoom out"
                  aria-label="Zoom out"
                >
                  <Minus size={17} />
                </button>
                <button
                  className="map-float-button"
                  onClick={() => command('fit')}
                  title="Fit scene to view"
                  aria-label="Fit scene to view"
                >
                  <Scan size={17} />
                </button>
              </div>
            </div>

            <div className="unsup-map-footer">
              <label className="unsup-opacity-slider">
                <span>SOM opacity</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={clusterOpacity}
                  onChange={(e) => setClusterOpacity(Number(e.target.value))}
                />
                <strong>{clusterOpacity}%</strong>
              </label>

              {result && (
                <div className="unsup-quick-legend">
                  {soloId !== null && (
                    <button
                      type="button"
                      className="unsup-reset-solo"
                      onClick={() => setSoloId(null)}
                    >
                      Show all ({result.nClusters})
                    </button>
                  )}
                  {result.clusters.slice(0, 8).map((c) => {
                    const rgb = resolvedColors[c.clusterId] ?? c.color;
                    const isSolo = soloId === c.clusterId;
                    return (
                      <button
                        key={c.clusterId}
                        type="button"
                        className={cn(
                          'unsup-legend-pill',
                          isSolo && 'is-solo',
                          hiddenIds.includes(c.clusterId) && 'is-hidden',
                        )}
                        onClick={() =>
                          setSoloId((cur) => (cur === c.clusterId ? null : c.clusterId))
                        }
                        title="Click to isolate this cluster on the map"
                      >
                        <i style={{ background: `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` }} />
                        <span>{clusterLabel(c)}</span>
                        <small>{Math.round(c.fraction * 100)}%</small>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <aside className="unsup-sidebar">
            <section className="chart-card unsup-config-card">
              <div className="chart-card-heading">
                <div>
                  <h3>
                    <Grid2x2 size={15} />
                    SOM configuration
                  </h3>
                  <p>Self-organize spectral vectors without supervision.</p>
                </div>
                <Badge>Kohonen</Badge>
              </div>

              <div className="unsup-form-grid">
                <label className="field-label">
                  SOM lattice
                  <select
                    className="input"
                    value={gridSide}
                    onChange={(e) => {
                      const nextSide = Number(e.target.value);
                      setGridSide(nextSide);
                      if (
                        clusterTarget !== 'neurons' &&
                        Number(clusterTarget) > nextSide * nextSide
                      ) {
                        setClusterTarget(String(nextSide * nextSide));
                      }
                    }}
                  >
                    {[2, 3, 4, 6, 8].map((n) => (
                      <option key={n} value={n}>
                        {n}×{n} ({n * n} neurons)
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field-label">
                  Output clusters
                  <select
                    className="input"
                    value={clusterTarget}
                    onChange={(e) => setClusterTarget(e.target.value)}
                  >
                    <option value="neurons">
                      All {gridSide * gridSide} SOM neurons
                    </option>
                    {[2, 3, 4, 5, 6, 8, 10, 12]
                      .filter((k) => k < gridSide * gridSide)
                      .map((k) => (
                        <option key={k} value={String(k)}>
                          Merge into {k} classes
                        </option>
                      ))}
                  </select>
                </label>

                <label className="field-label">
                  Resolution
                  <select
                    className="input"
                    value={resolution}
                    onChange={(e) => setResolution(e.target.value as 'pixel' | 'patch')}
                  >
                    <option value="pixel">Pixel-level (full GeoTIFF)</option>
                    <option value="patch">Patch grid</option>
                  </select>
                </label>

                <label className="field-label">
                  Training epochs
                  <select
                    className="input"
                    value={epochs}
                    onChange={(e) => setEpochs(Number(e.target.value))}
                  >
                    {[25, 50, 100].map((ep) => (
                      <option key={ep} value={ep}>
                        {ep} epochs
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <Button
                className="full-width unsup-run-btn"
                disabled={somQuery.isFetching}
                onClick={runSom}
              >
                {somQuery.isFetching ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <Sparkles size={15} />
                )}
                {somQuery.isFetching ? 'Running Kohonen SOM…' : 'Run unsupervised SOM'}
              </Button>
            </section>

            {somQuery.error ? (
              <ErrorState message={somQuery.error.message} onRetry={() => somQuery.refetch()} />
            ) : !result ? (
              <Skeleton className="chart-skeleton" />
            ) : (
              <>
                <section className="chart-card unsup-clusters-card">
                  <div className="chart-card-heading">
                    <div>
                      <h3>Discovered clusters</h3>
                      <p>Rename classes, adjust colors, or isolate individual clusters.</p>
                    </div>
                    <Badge>{result.nClusters} classes</Badge>
                  </div>

                  <div className="unsup-cluster-list">
                    {result.clusters.map((c) => {
                      const rgb = resolvedColors[c.clusterId] ?? c.color;
                      const isSolo = soloId === c.clusterId;
                      const isHidden = hiddenIds.includes(c.clusterId);
                      return (
                        <div
                          key={c.clusterId}
                          className={cn(
                            'unsup-cluster-row',
                            isSolo && 'is-solo',
                            isHidden && 'is-hidden',
                          )}
                        >
                          <div className="unsup-cluster-top">
                            <input
                              type="color"
                              className="unsup-color-input"
                              value={rgbToHex(rgb)}
                              disabled={paletteMode !== 'distinct'}
                              title={
                                paletteMode === 'distinct'
                                  ? 'Customize cluster color'
                                  : 'Switch palette to Distinct to pick custom colors'
                              }
                              onChange={(e) =>
                                setCustomColors((prev) => ({
                                  ...prev,
                                  [c.clusterId]: hexToRgb(e.target.value),
                                }))
                              }
                            />
                            <input
                              type="text"
                              className="unsup-name-input"
                              value={customNames[c.clusterId] ?? c.label}
                              maxLength={40}
                              aria-label={`Cluster ${c.clusterId + 1} name`}
                              onChange={(e) =>
                                setCustomNames((prev) => ({
                                  ...prev,
                                  [c.clusterId]: e.target.value,
                                }))
                              }
                            />
                            <span className="unsup-cluster-share">
                              {(c.fraction * 100).toFixed(1)}%
                            </span>
                            <button
                              type="button"
                              className={cn('icon-button small', isSolo && 'green-text')}
                              title={isSolo ? 'Show all clusters' : 'Isolate cluster on map'}
                              aria-label={`Isolate ${clusterLabel(c)}`}
                              onClick={() =>
                                setSoloId((cur) => (cur === c.clusterId ? null : c.clusterId))
                              }
                            >
                              <Target size={13} />
                            </button>
                            <button
                              type="button"
                              className="icon-button small"
                              title={isHidden ? 'Show cluster' : 'Hide cluster'}
                              aria-label={isHidden ? `Show ${clusterLabel(c)}` : `Hide ${clusterLabel(c)}`}
                              onClick={() => toggleHideCluster(c.clusterId)}
                            >
                              {isHidden ? <EyeOff size={13} /> : <Eye size={13} />}
                            </button>
                          </div>

                          <div className="unsup-area-bar">
                            <i
                              style={{
                                width: `${Math.max(2, c.fraction * 100)}%`,
                                background: `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`,
                              }}
                            />
                          </div>

                          <div className="unsup-cluster-meta">
                            <span>{formatNumber(c.pixelCount)} px</span>
                            <div className="unsup-mini-spectrum" title="Normalized mean spectral profile across bands">
                              {c.bandProfile.slice(0, 6).map((val, bi) => (
                                <span key={bi}>
                                  <i style={{ height: `${Math.max(18, Math.round(val * 100))}%` }} />
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>

                <section className="chart-card unsup-manifold-card">
                  <div className="chart-card-heading">
                    <div>
                      <h3>2D Kohonen manifold</h3>
                      <p>
                        {manifoldView === 'clusters'
                          ? 'How SOM neurons map into unsupervised classes.'
                          : 'U-Matrix ridge distances between neighboring neurons.'}
                      </p>
                    </div>
                    <select
                      className="chart-select"
                      value={manifoldView}
                      onChange={(e) =>
                        setManifoldView(e.target.value as 'clusters' | 'u-matrix')
                      }
                      aria-label="Manifold view"
                    >
                      <option value="clusters">Cluster map</option>
                      <option value="u-matrix">U-Matrix</option>
                    </select>
                  </div>

                  <div
                    className="unsup-neuron-grid"
                    style={{ gridTemplateColumns: `repeat(${result.cols}, minmax(0, 1fr))` }}
                  >
                    {result.neuronClusters.flatMap((rowArr, r) =>
                      rowArr.map((cid, c) => {
                        const hits = result.neuronHits[r]?.[c] ?? 0;
                        const uVal = result.uMatrix[r]?.[c] ?? 0;
                        const rgb = resolvedColors[cid] ?? [52, 142, 98];
                        const bg =
                          manifoldView === 'clusters'
                            ? `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${hits > 0 ? 0.85 : 0.28})`
                            : `rgba(${Math.round(58 + uVal * 144)}, ${Math.round(146 - uVal * 48)}, ${Math.round(115 - uVal * 52)}, ${0.18 + uVal * 0.72})`;
                        return (
                          <button
                            key={`${r}-${c}`}
                            type="button"
                            className={cn(
                              'unsup-neuron-cell',
                              soloId === cid && 'is-solo',
                            )}
                            style={{ background: bg }}
                            onClick={() =>
                              setSoloId((cur) => (cur === cid ? null : cid))
                            }
                            title={`Neuron (${r}, ${c}) → Cluster ${cid + 1} · ${formatNumber(hits)} px · U=${uVal.toFixed(2)}`}
                          >
                            <span>C{cid + 1}</span>
                          </button>
                        );
                      }),
                    )}
                  </div>
                </section>
              </>
            )}
          </aside>
        </div>
      )}
    </>
  );
}
