'use client';
import { useMemo, useRef, useState } from 'react';
import {
  ArrowUpRight,
  Database,
  Download,
  Grid2x2,
  LoaderCircle,
  Sparkles,
  Target,
} from 'lucide-react';
import { toast } from 'sonner';
import { useDatasets, useQueryBatch, useSamples, useSom } from '@/hooks/use-projects';
import { useWorkspace } from '@/stores/workspace';
import { cn, downloadJSON, formatNumber } from '@/lib/utils';
import { Button } from './ui/button';
import { Badge, Dot, EmptyState, ErrorState, Skeleton } from './ui/common';
import type { Project, SomCell, SomColorMode, SomData } from '@/types';

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean;
  const num = Number.parseInt(full, 16);
  if (Number.isNaN(num)) return `rgba(44, 129, 103, ${alpha})`;
  const r = (num >> 16) & 255;
  const g = (num >> 8) & 255;
  const b = num & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function uMatrixBackground(u: number): { bg: string; darkText: boolean } {
  const t = Math.max(0, Math.min(1, u));
  // Calm sage cluster valley (t=0) -> warm amber transition -> terracotta boundary ridge (t=1)
  const r = Math.round(58 + t * 144);
  const g = Math.round(146 - t * 48);
  const b = Math.round(115 - t * 52);
  const alpha = 0.16 + t * 0.72;
  return { bg: `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`, darkText: t > 0.62 };
}

function spectralBackground(profile: number[]): { bg: string; darkText: boolean } {
  if (!profile.length) return { bg: 'var(--surface-subtle)', darkText: false };
  const p0 = profile[0] ?? 0.5;
  const p1 = profile[1] ?? p0;
  const p2 = profile[2] ?? (profile.length === 2 ? (p0 + p1) * 0.5 : p0);
  const r = Math.round(42 + p0 * 188);
  const g = Math.round(48 + p1 * 182);
  const b = Math.round(46 + p2 * 184);
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return { bg: `rgb(${r}, ${g}, ${b})`, darkText: lum < 0.56 };
}

function cellAppearance(
  cell: SomCell,
  mode: SomColorMode,
  maxHits: number,
  classColors: Map<string, string>,
): { bg: string; darkText: boolean } {
  if (mode === 'u-matrix') return uMatrixBackground(cell.uValue);

  if (mode === 'spectral') {
    if (cell.hitCount === 0) return { bg: 'var(--surface-subtle)', darkText: false };
    return spectralBackground(cell.bandProfile);
  }

  if (mode === 'classes') {
    if (cell.dominantLabel) {
      const color = classColors.get(cell.dominantLabel) ?? '#388e70';
      return { bg: hexToRgba(color, 0.84), darkText: true };
    }
    if (cell.predictedClass && cell.hitCount > 0) {
      const color = classColors.get(cell.predictedClass) ?? '#388e70';
      return { bg: hexToRgba(color, 0.34), darkText: false };
    }
    return { bg: 'var(--surface-subtle)', darkText: false };
  }

  if (mode === 'uncertainty') {
    if (cell.hitCount === 0 || cell.meanUncertainty == null) {
      return { bg: 'var(--surface-subtle)', darkText: false };
    }
    const u = Math.max(0, Math.min(1, cell.meanUncertainty));
    const r = Math.round(72 + u * 138);
    const g = Math.round(148 - u * 68);
    const b = Math.round(108 - u * 48);
    const alpha = 0.14 + u * 0.76;
    return { bg: `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`, darkText: u > 0.58 };
  }

  // density mode
  if (cell.hitCount === 0) return { bg: 'var(--surface-subtle)', darkText: false };
  const ratio = Math.log1p(cell.hitCount) / Math.max(Math.log1p(maxHits), 1);
  const alpha = 0.14 + ratio * 0.78;
  return {
    bg: `rgba(44, 129, 103, ${alpha.toFixed(3)})`,
    darkText: ratio > 0.55,
  };
}

function pickInitialCell(som: SomData): [number, number] {
  const best =
    som.cells
      .filter((c) => c.hitCount > 0)
      .sort((a, b) => b.unlabeledCount - a.unlabeledCount || b.hitCount - a.hitCount)[0] ??
    som.cells[0];
  return best ? [best.row, best.col] : [0, 0];
}

export function SomExplorer({
  project,
  compact = false,
}: {
  project: Project;
  compact?: boolean;
}) {
  const { data: datasets = [], isLoading: datasetsLoading } = useDatasets(project.id);
  const { data: samples = [] } = useSamples(project.id);
  const {
    view,
    setView,
    selectedDatasetId,
    selectDataset,
    selectedSampleId,
    selectSample,
  } = useWorkspace();

  const activeDataset =
    datasets.find((d) => d.id === selectedDatasetId) ?? datasets[datasets.length - 1] ?? null;

  const [gridSize, setGridSize] = useState<number | undefined>(undefined);
  const [mode, setMode] = useState<SomColorMode>('u-matrix');
  const [manualSelection, setManualSelection] = useState<{
    coords: [number, number];
    sampleId: string | null;
  } | null>(null);
  const cellRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const {
    data: som,
    isLoading: somLoading,
    error: somError,
    refetch,
  } = useSom(project.id, {
    datasetId: activeDataset?.id,
    size: gridSize,
    enabled: !!activeDataset,
  });

  const queryBatch = useQueryBatch(project.id);

  const classColors = useMemo(
    () => new Map(project.classes.map((c) => [c.id, c.color])),
    [project.classes],
  );

  const sampleById = useMemo(() => new Map(samples.map((s) => [s.id, s])), [samples]);

  const activeSampleCell = useMemo(() => {
    if (!som || !selectedSampleId) return null;
    return som.cells.find((c) => c.sampleIds.includes(selectedSampleId)) ?? null;
  }, [som, selectedSampleId]);

  const effectiveMode: SomColorMode =
    mode === 'uncertainty' && (!som || som.modelIteration == null) ? 'u-matrix' : mode;

  const selectCoords = (coords: [number, number]) => {
    setManualSelection({ coords, sampleId: selectedSampleId });
  };

  const resolvedCoords: [number, number] = useMemo(() => {
    if (!som) return [0, 0];
    const inBounds = (c: [number, number]) => c[0] < som.rows && c[1] < som.cols;
    if (
      manualSelection &&
      manualSelection.sampleId === selectedSampleId &&
      inBounds(manualSelection.coords)
    ) {
      return manualSelection.coords;
    }
    if (activeSampleCell) {
      return [activeSampleCell.row, activeSampleCell.col];
    }
    if (manualSelection && inBounds(manualSelection.coords)) {
      return manualSelection.coords;
    }
    return pickInitialCell(som);
  }, [som, manualSelection, selectedSampleId, activeSampleCell]);

  const selectedCell = useMemo(() => {
    if (!som) return null;
    return (
      som.cells.find((c) => c.row === resolvedCoords[0] && c.col === resolvedCoords[1]) ??
      som.cells[0] ??
      null
    );
  }, [som, resolvedCoords]);

  const maxHits = useMemo(
    () => (som ? Math.max(1, ...som.cells.map((c) => c.hitCount)) : 1),
    [som],
  );

  const unexploredClusters = useMemo(
    () => (som ? som.cells.filter((c) => c.hitCount > 0 && c.labeledCount === 0).length : 0),
    [som],
  );

  const handleCellKeyDown = (e: React.KeyboardEvent, row: number, col: number) => {
    if (!som) return;
    let nr = row;
    let nc = col;
    if (e.key === 'ArrowUp') nr = Math.max(0, row - 1);
    else if (e.key === 'ArrowDown') nr = Math.min(som.rows - 1, row + 1);
    else if (e.key === 'ArrowLeft') nc = Math.max(0, col - 1);
    else if (e.key === 'ArrowRight') nc = Math.min(som.cols - 1, col + 1);
    else return;
    e.preventDefault();
    selectCoords([nr, nc]);
    cellRefs.current[`${nr}-${nc}`]?.focus();
  };

  const queueFromNeuron = async (cell: SomCell) => {
    if (!som || cell.unlabeledCount <= 0) return;
    try {
      const result = await queryBatch.mutateAsync({
        batchSize: Math.min(12, cell.unlabeledCount),
        strategy: 'som',
        datasetId: som.datasetId,
        merge: true,
        options: {
          somRows: som.rows,
          somCols: som.cols,
          somEpochs: som.epochs,
          somCell: [cell.row, cell.col],
        },
      });
      if (result.samples[0]) {
        selectDataset(som.datasetId);
        selectSample(result.samples[0].id);
        if (view !== 'learning') setView('learning');
        toast.success(
          `Added ${result.samples.length} ${result.samples.length === 1 ? 'patch' : 'patches'} from neuron (${cell.row}, ${cell.col}).`,
          {
            description: 'Ready for review on the interactive map.',
          },
        );
      } else {
        toast.info('All patches in this neuron are already labeled.');
      }
    } catch {
      /* Mutation displays errors via toast. */
    }
  };

  const queryFullSomBatch = async () => {
    if (!som) return;
    try {
      const result = await queryBatch.mutateAsync({
        batchSize: 12,
        strategy: 'som',
        datasetId: som.datasetId,
        options: {
          somRows: som.rows,
          somCols: som.cols,
          somEpochs: som.epochs,
        },
      });
      if (result.samples[0]) {
        selectDataset(som.datasetId);
        selectSample(result.samples[0].id);
        if (view !== 'learning') setView('learning');
        toast.success(`${result.samples.length} SOM-guided samples added to the review queue.`, {
          description:
            som.modelIteration != null
              ? 'Balanced model uncertainty across distinct Kohonen clusters.'
              : 'Sampled representative medoids across unexplored spectral clusters.',
        });
      } else {
        toast.info('Every patch in this dataset has already been labeled.');
      }
    } catch {
      /* Mutation displays errors via toast. */
    }
  };

  if (datasetsLoading) {
    return <Skeleton className="chart-skeleton som-skeleton" />;
  }

  if (!datasets.length) {
    return (
      <article className={cn('chart-card som-card', compact && 'som-card-compact')} id="som-explorer">
        <div className="chart-card-heading">
          <div>
            <h3>
              <Grid2x2 size={16} />
              Self-organizing map
            </h3>
            <p>Organize your satellite patches onto a 2D topological manifold.</p>
          </div>
          <Badge>Kohonen SOM</Badge>
        </div>
        <EmptyState
          title="Upload a GeoTIFF to build your feature map"
          description="Once imagery is uploaded, patches self-organize by spectral similarity so you can spot clusters and boundaries."
          action={
            <Button variant="outline" size="sm" onClick={() => setView('datasets')}>
              <Database size={14} />
              Open dataset library
            </Button>
          }
        />
      </article>
    );
  }

  if (somError) {
    return <ErrorState message={somError.message} onRetry={() => refetch()} />;
  }

  const cellKnownSamples = selectedCell
    ? selectedCell.sampleIds
        .map((sid) => sampleById.get(sid))
        .filter((s): s is NonNullable<typeof s> => Boolean(s))
        .slice(0, 4)
    : [];

  const roleBadge = !selectedCell
    ? ''
    : selectedCell.hitCount === 0
      ? 'Bridge unit'
      : selectedCell.uValue >= 0.62
        ? 'Boundary ridge'
        : selectedCell.labeledCount === 0
          ? 'Unexplored cluster'
          : 'Mapped cluster';

  return (
    <article className={cn('chart-card som-card', compact && 'som-card-compact')} id="som-explorer">
      <div className="chart-card-heading som-heading">
        <div>
          <h3>
            <Grid2x2 size={16} />
            Self-organizing map
            {som && (
              <Badge>
                {som.rows}×{som.cols} Kohonen grid
              </Badge>
            )}
          </h3>
          <p>
            Patches with similar spectral signatures settle into neighboring neurons — valleys are
            clusters, ridges are boundaries.
          </p>
        </div>
        <div className="som-toolbar">
          {datasets.length > 1 && (
            <select
              className="chart-select"
              value={activeDataset?.id ?? ''}
              onChange={(e) => selectDataset(e.target.value)}
              aria-label="SOM dataset"
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          )}
          <select
            className="chart-select"
            value={gridSize ?? 'auto'}
            onChange={(e) =>
              setGridSize(e.target.value === 'auto' ? undefined : Number(e.target.value))
            }
            aria-label="SOM grid dimensions"
          >
            <option value="auto">Auto grid</option>
            <option value="6">6×6 neurons</option>
            <option value="8">8×8 neurons</option>
            <option value="10">10×10 neurons</option>
          </select>
          <button className="text-button green-text" onClick={() => setView('unsupervised')}>
            Unsupervised map
            <ArrowUpRight size={13} />
          </button>
          {!compact && som && (
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                downloadJSON(
                  { project: project.name, exportedAt: new Date().toISOString(), ...som },
                  `${project.id}-som.json`,
                )
              }
            >
              <Download size={13} />
              Export SOM
            </Button>
          )}
        </div>
      </div>

      <div className="som-mode-bar" role="tablist" aria-label="SOM overlay mode">
        {(
          [
            { id: 'u-matrix', label: 'U-Matrix' },
            { id: 'classes', label: 'Classes' },
            { id: 'spectral', label: 'Spectral' },
            { id: 'density', label: 'Density' },
            {
              id: 'uncertainty',
              label: 'Uncertainty',
              disabled: !som || som.modelIteration == null,
            },
          ] as const
        ).map((item) => (
          <button
            key={item.id}
            role="tab"
            type="button"
            aria-selected={effectiveMode === item.id}
            disabled={'disabled' in item && item.disabled}
            title={
              'disabled' in item && item.disabled
                ? 'Train a model first to view neuron uncertainty'
                : undefined
            }
            className={cn('som-mode-pill', effectiveMode === item.id && 'active')}
            onClick={() => setMode(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {somLoading || !som ? (
        <div className="som-loading-grid">
          <Skeleton className="som-matrix-skeleton" />
          <Skeleton className="som-inspector-skeleton" />
        </div>
      ) : (
        <div className="som-layout">
          <div className="som-matrix-panel">
            <div
              className="som-grid"
              style={{ gridTemplateColumns: `repeat(${som.cols}, minmax(0, 1fr))` }}
              role="grid"
              aria-label={`${som.rows} by ${som.cols} Self-Organizing Map`}
            >
              {som.cells.map((cell) => {
                const isSelected =
                  selectedCell?.row === cell.row && selectedCell?.col === cell.col;
                const hasActiveSample =
                  activeSampleCell?.row === cell.row && activeSampleCell?.col === cell.col;
                const { bg, darkText } = cellAppearance(cell, effectiveMode, maxHits, classColors);
                const labelColor = cell.dominantLabel
                  ? classColors.get(cell.dominantLabel)
                  : undefined;
                const unexplored =
                  effectiveMode === 'density' && cell.hitCount > 0 && cell.labeledCount === 0;

                return (
                  <button
                    key={`${cell.row}-${cell.col}`}
                    ref={(el) => {
                      cellRefs.current[`${cell.row}-${cell.col}`] = el;
                    }}
                    type="button"
                    role="gridcell"
                    aria-selected={isSelected}
                    aria-label={`Neuron ${cell.row}, ${cell.col}: ${cell.hitCount} patches, ${cell.labeledCount} labeled, U-matrix ${cell.uValue.toFixed(2)}`}
                    className={cn(
                      'som-cell',
                      isSelected && 'is-selected',
                      hasActiveSample && 'has-active-sample',
                      cell.hitCount === 0 && 'is-empty',
                      unexplored && 'is-unexplored',
                      darkText && 'is-dark',
                    )}
                    style={{ background: bg }}
                    onClick={() => selectCoords([cell.row, cell.col])}
                    onKeyDown={(e) => handleCellKeyDown(e, cell.row, cell.col)}
                    title={`(${cell.row}, ${cell.col}) · ${cell.hitCount} patches (${cell.labeledCount} labeled) · U=${cell.uValue.toFixed(2)}`}
                  >
                    {som.cols <= 10 && cell.hitCount > 0 && (
                      <span className="som-cell-count">{cell.hitCount}</span>
                    )}
                    {labelColor && effectiveMode !== 'classes' && (
                      <span
                        className="som-cell-dot"
                        style={{ background: labelColor }}
                        aria-hidden="true"
                      />
                    )}
                  </button>
                );
              })}
            </div>

            <div className="som-legend-row">
              {effectiveMode === 'u-matrix' && (
                <span className="som-gradient-legend">
                  <span>Cluster core</span>
                  <i className="som-ramp som-ramp-umatrix" />
                  <span>Boundary ridge</span>
                </span>
              )}
              {effectiveMode === 'density' && (
                <span className="som-gradient-legend">
                  <span>Sparse</span>
                  <i className="som-ramp som-ramp-density" />
                  <span>Dense · dashed = unlabeled</span>
                </span>
              )}
              {effectiveMode === 'uncertainty' && (
                <span className="som-gradient-legend">
                  <span>Confident</span>
                  <i className="som-ramp som-ramp-uncertainty" />
                  <span>Uncertain</span>
                </span>
              )}
              {effectiveMode === 'spectral' && (
                <span className="som-legend-caption">
                  Synthesized from each neuron’s learned spectral band prototype
                </span>
              )}
              {effectiveMode === 'classes' && (
                <span className="som-class-legend">
                  {project.classes.slice(0, 5).map((c) => (
                    <span key={c.id}>
                      <Dot color={c.color} />
                      {c.name}
                    </span>
                  ))}
                </span>
              )}
            </div>

            <div className="som-stats-strip">
              <span>
                <strong>QE</strong> {som.quantizationError.toFixed(2)}
              </span>
              <span>
                <strong>Topo error</strong> {(som.topographicError * 100).toFixed(1)}%
              </span>
              <span>
                <strong>Active</strong> {som.activeNeurons}/{som.rows * som.cols}
              </span>
              <span>
                <strong>Unexplored</strong> {unexploredClusters} clusters
              </span>
            </div>
          </div>

          {selectedCell && (
            <div className="som-inspector">
              <div className="som-inspector-header">
                <div>
                  <span className="som-inspector-eyebrow">SELECTED NEURON</span>
                  <h4>
                    Unit ({selectedCell.row}, {selectedCell.col})
                    {activeSampleCell?.row === selectedCell.row &&
                      activeSampleCell?.col === selectedCell.col && (
                        <span className="som-active-pill">
                          <Target size={10} /> Active sample
                        </span>
                      )}
                  </h4>
                </div>
                <Badge>{roleBadge}</Badge>
              </div>

              <div className="som-kpi-grid">
                <div>
                  <small>Patches</small>
                  <strong>{formatNumber(selectedCell.hitCount)}</strong>
                  <span>{selectedCell.unlabeledCount} unlabeled</span>
                </div>
                <div>
                  <small>Boundary (U)</small>
                  <strong>{selectedCell.uValue.toFixed(2)}</strong>
                  <span>{selectedCell.uValue >= 0.62 ? 'High contrast' : 'Cohesive'}</span>
                </div>
                <div>
                  <small>Quant. error</small>
                  <strong>{selectedCell.quantizationError.toFixed(2)}</strong>
                  <span>Prototype fit</span>
                </div>
                <div>
                  <small>Uncertainty</small>
                  <strong>
                    {selectedCell.meanUncertainty != null
                      ? `${Math.round(selectedCell.meanUncertainty * 100)}%`
                      : '—'}
                  </strong>
                  <span>
                    {selectedCell.meanConfidence != null
                      ? `${Math.round(selectedCell.meanConfidence * 100)}% conf.`
                      : 'No model yet'}
                  </span>
                </div>
              </div>

              <div className="som-section">
                <div className="som-section-title">
                  <span>Spectral prototype</span>
                  <small>{som.bands} bands</small>
                </div>
                <div className="som-band-bars">
                  {selectedCell.bandProfile.slice(0, 8).map((val, idx) => (
                    <div key={idx} className="som-band-row">
                      <span className="som-band-label">B{idx + 1}</span>
                      <div className="som-band-track">
                        <i style={{ width: `${Math.max(4, Math.round(val * 100))}%` }} />
                      </div>
                      <span className="som-band-val">
                        {Number.isFinite(selectedCell.bandMeans[idx])
                          ? selectedCell.bandMeans[idx].toFixed(1)
                          : '0.0'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="som-section">
                <div className="som-section-title">
                  <span>Cluster composition</span>
                  <small>
                    {selectedCell.labeledCount}/{selectedCell.hitCount} labeled
                  </small>
                </div>
                {Object.keys(selectedCell.labelCounts).length > 0 ||
                Object.keys(selectedCell.predictionCounts).length > 0 ? (
                  <div className="som-composition-tags">
                    {Object.entries(selectedCell.labelCounts).map(([cls, count]) => (
                      <span key={`lbl-${cls}`} className="som-class-chip">
                        <Dot color={classColors.get(cls) ?? '#388e70'} />
                        {cls}: <strong>{count}</strong> labeled
                      </span>
                    ))}
                    {Object.entries(selectedCell.predictionCounts).map(([cls, count]) => (
                      <span key={`pred-${cls}`} className="som-class-chip predicted">
                        <Dot color={classColors.get(cls) ?? '#388e70'} />
                        {cls}: {count} pred.
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="som-muted-note">
                    {selectedCell.hitCount === 0
                      ? 'No dataset patches map directly to this interpolated bridge neuron.'
                      : 'No human labels in this cluster yet — a prime candidate for exploration.'}
                  </p>
                )}
              </div>

              {cellKnownSamples.length > 0 && (
                <div className="som-section">
                  <div className="som-section-title">
                    <span>Jump to sample on map</span>
                  </div>
                  <div className="som-sample-chips">
                    {cellKnownSamples.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        className={cn(
                          'som-sample-chip',
                          selectedSampleId === s.id && 'active',
                        )}
                        onClick={() => {
                          if (s.datasetId) selectDataset(s.datasetId);
                          selectSample(s.id);
                          if (view !== 'learning') setView('learning');
                        }}
                      >
                        {s.id}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="som-actions">
                <Button
                  size="sm"
                  disabled={queryBatch.isPending || selectedCell.unlabeledCount === 0}
                  onClick={() => queueFromNeuron(selectedCell)}
                >
                  {queryBatch.isPending ? (
                    <LoaderCircle size={14} className="spin" />
                  ) : (
                    <Target size={14} />
                  )}
                  {selectedCell.unlabeledCount > 0
                    ? `Queue neuron (${Math.min(12, selectedCell.unlabeledCount)})`
                    : 'Neuron fully labeled'}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={queryBatch.isPending || som.labeledPatches >= som.totalPatches}
                  onClick={queryFullSomBatch}
                >
                  <Sparkles size={14} />
                  Query SOM batch
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
