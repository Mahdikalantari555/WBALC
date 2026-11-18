'use client';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Crosshair,
  FileImage,
  Hand,
  Layers,
  LoaderCircle,
  MapPin,
  Maximize,
  Minus,
  MousePointer2,
  Plus,
  Redo2,
  Scan,
  Settings2,
  Shrink,
  Square,
  Undo2,
  VectorSquare,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { useWorkspace } from '@/stores/workspace';
import { renderRaster } from '@/lib/geotiff';
import { useMapField } from '@/hooks/use-projects';
import { api } from '@/lib/api';
import { methodLabel, UNCERTAINTY_RAMP } from '@/lib/overlay';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Dot, EmptyState } from '@/components/ui/common';
import type {
  BandMode,
  Dataset,
  DrawingTool,
  GeorefReason,
  MapExportFormat,
  Project,
  Sample,
  SampleGeometry,
  UncertaintyMethod,
} from '@/types';
import type { MapAction } from './leaflet-map';
const LeafletMap = dynamic(() => import('./leaflet-map'), {
  ssr: false,
  loading: () => (
    <div className="map-loading">
      <LoaderCircle className="spin" size={25} />
      <span>Finding your perspective…</span>
    </div>
  ),
});
/**
 * Why the map is in pixel space. Saying it out loud stops "the imagery is
 * warped" from being read as "the labels are wrong".
 */
const GEOREF_MESSAGES: Record<GeorefReason, string> = {
  'not-georeferenced': 'no CRS in the file · pixel space',
  'unsupported-crs': 'CRS not supported for basemap display · pixel space',
  'non-axis-aligned': 'reprojection is not affine · pixel space',
};
const tools: { id: DrawingTool; icon: typeof Hand; title: string }[] = [
  { id: 'pan', icon: Hand, title: 'Pan map' },
  { id: 'point', icon: MapPin, title: 'Draw point (P)' },
  { id: 'polygon', icon: VectorSquare, title: 'Draw polygon — double-click to finish' },
  { id: 'rectangle', icon: Square, title: 'Draw rectangle — click two corners' },
];
export function MapViewer({
  project,
  datasets,
  samples,
  busy = false,
}: {
  project: Project;
  datasets: Dataset[];
  samples: Sample[];
  busy?: boolean;
}) {
  const store = useWorkspace();
  const {
    selectedDatasetId,
    selectDataset,
    tool,
    setTool,
    activeClass,
    setActiveClass,
    bandMode,
    setBandMode,
    customBands,
    setCustomBands,
    opacity,
    setOpacity,
    showLabels,
    toggleLabels,
    showSuggestions,
    toggleSuggestions,
    showClassification,
    showUncertainty,
    toggleClassification,
    toggleUncertainty,
    classificationOpacity,
    uncertaintyOpacity,
    setClassificationOpacity,
    setUncertaintyOpacity,
    uncertaintyMethod,
    setUncertaintyMethod,
    hiddenClasses,
    toggleClassVisibility,
    drafts,
    saveDraft,
    removeDraft,
  } = store;
  const dataset = datasets.find((d) => d.id === selectedDatasetId) ?? datasets[0];
  const [expanded, setExpanded] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [bandsOpen, setBandsOpen] = useState(false);
  const [action, setAction] = useState<MapAction | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const command = (kind: MapAction['kind']) => setAction({ kind, nonce: Date.now() });
  const hasModel = !!project.modelVersion;
  const classification = useMapField(project.id, {
    layer: 'hard',
    method: uncertaintyMethod,
    datasetId: dataset?.id,
    enabled: showClassification && hasModel && !!dataset,
  });
  const uncertainty = useMapField(project.id, {
    layer: 'uncertainty',
    method: uncertaintyMethod,
    datasetId: dataset ? dataset.id : undefined,
    enabled: showUncertainty && hasModel && !!dataset,
  });
  useEffect(() => {
    const error = classification.error ?? uncertainty.error;
    if (error) toast.error(error.message);
  }, [classification.error, uncertainty.error]);
  const modelBandsMismatch =
    hasModel &&
    dataset &&
    (classification.data?.classes.length ?? 0) > 0 &&
    classification.error?.message.includes('bands');
  const raster = useQuery({
    queryKey: ['raster', dataset?.id, bandMode, customBands],
    // Shares the cached, range-reading handle with the review thumbnails, so
    // switching band modes does not re-download the scene.
    queryFn: () =>
      renderRaster({ url: dataset!.url, datasetId: dataset!.id }, bandMode, customBands),
    enabled: !!dataset,
    staleTime: Infinity,
    retry: 0,
  });
  useEffect(() => {
    if (raster.error) toast.error(raster.error.message);
  }, [raster.error]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const onDraw = (lat: number, lng: number, geometry: SampleGeometry) => {
    if (busy) {
      toast.info('Please wait until the current submission finishes.');
      return;
    }
    const label = project.classes.find((c) => c.id === activeClass) ?? project.classes[0];
    saveDraft({
      sampleId: `manual-${crypto.randomUUID()}`,
      label: label.id,
      status: 'labeled',
      note: '',
      lat,
      lng,
      geometry,
      datasetId: dataset?.id,
    });
    toast.success(`${label.name} sample added`, {
      description: 'Submit your labels to save this training sample.',
    });
  };
  const changeBands = (mode: BandMode) => {
    if ((mode === 'ndvi' || mode === 'false-color') && dataset && dataset.bands < 4) {
      toast.info('This view needs at least four spectral bands.', {
        description: 'Upload imagery with red and near-infrared bands for NIR and NDVI views.',
      });
      return;
    }
    setBandMode(mode);
    setBandsOpen(mode === 'custom');
  };
  if (!dataset)
    return (
      <div className="map-card map-empty">
        <EmptyState
          title="Your next discovery starts with a scene"
          description="Upload a GeoTIFF to explore its spectral bands and create your first training samples."
          action={
            <Button onClick={() => store.setView('datasets')}>
              <Plus size={16} />
              Add imagery
            </Button>
          }
        />
      </div>
    );
  const selected = samples.find((s) => s.id === store.selectedSampleId);
  const rasterUrl = raster.data ?? dataset.previewUrl;
  return (
    <div className={cn('map-card', expanded && 'is-expanded')} ref={cardRef}>
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
          <span>GeoTIFF · {dataset.crs}</span>
        </div>
        <span className="raster-ready">
          <span />
          Ready
        </span>
        <button
          className="icon-button"
          aria-label={expanded ? 'Exit expanded map' : 'Expand map'}
          title="Expand map"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <Shrink size={17} /> : <Maximize size={17} />}
        </button>
      </div>
      <div className="map-canvas-wrap">
        {rasterUrl && (
          <LeafletMap
            dataset={dataset}
            datasetIds={datasets.map((d) => d.id)}
            classification={showClassification ? classification.data ?? null : null}
            uncertainty={showUncertainty ? uncertainty.data ?? null : null}
            classificationOpacity={classificationOpacity}
            uncertaintyOpacity={uncertaintyOpacity}
            hiddenClasses={hiddenClasses}
            rasterUrl={rasterUrl}
            project={project}
            samples={samples}
            action={action}
            onDraw={onDraw}
          />
        )}
        {raster.isFetching && (
          <div className="raster-loading">
            <LoaderCircle className="spin" size={15} />
            Rendering spectral bands…
          </div>
        )}
        <div className="map-top-left">
          <div className="band-selector">
            <span className="rgb-icon">
              <i />
              <i />
              <i />
            </span>
            <select
              value={bandMode}
              onChange={(e) => changeBands(e.target.value as BandMode)}
              aria-label="Band combination"
            >
              <option value="true-color">True color (RGB)</option>
              <option value="false-color">False color (NIR)</option>
              <option value="ndvi">NDVI vegetation</option>
              <option value="custom">Custom RGB</option>
            </select>
          </div>
          {bandMode === 'custom' && (
            <button
              className="map-float-button"
              onClick={() => setBandsOpen(!bandsOpen)}
              aria-label="Configure RGB bands"
            >
              <Settings2 size={17} />
            </button>
          )}
        </div>
        {bandsOpen && (
          <div className="custom-bands floating-panel">
            <div className="floating-title">
              <strong>Custom RGB bands</strong>
              <button
                onClick={() => setBandsOpen(false)}
                className="icon-button"
                aria-label="Close band configuration"
              >
                <X size={14} />
              </button>
            </div>
            {['Red', 'Green', 'Blue'].map((name, i) => (
              <label key={name}>
                {name}
                <select
                  className="input"
                  value={Math.min(customBands[i], dataset.bands - 1)}
                  onChange={(e) => {
                    const next = [...customBands] as [number, number, number];
                    next[i] = Number(e.target.value);
                    setCustomBands(next);
                  }}
                >
                  {Array.from({ length: dataset.bands }, (_, b) => (
                    <option value={b} key={b}>
                      Band {b + 1}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        )}
        <div className="draw-toolbar">
          {tools.map(({ id, icon: Icon, title }) => (
            <button
              key={id}
              className={cn(tool === id && 'selected')}
              title={title}
              aria-label={title}
              aria-pressed={tool === id}
              onClick={() => setTool(id)}
            >
              <Icon size={18} strokeWidth={1.7} />
            </button>
          ))}
          <span />
          <button
            aria-label="Undo last drawn sample"
            title="Undo last drawn sample"
            onClick={() => {
              const last = Object.keys(drafts)
                .filter((id) => id.startsWith('manual-'))
                .pop();
              if (last) {
                removeDraft(last);
                toast.success('Last drawn sample removed.');
              }
              command('undo');
            }}
          >
            <Undo2 size={18} />
          </button>
        </div>
        <div className="map-top-right">
          <button
            className={cn('map-float-button', layersOpen && 'selected')}
            onClick={() => setLayersOpen(!layersOpen)}
            title="Map layers and opacity"
            aria-label="Map layers and opacity"
          >
            <Layers size={18} />
          </button>
          <button
            className="map-float-button"
            onClick={() => command('fit')}
            title="Fit dataset to view"
            aria-label="Fit dataset to view"
          >
            <Scan size={18} />
          </button>
        </div>
        {layersOpen && (
          <div className="layer-panel floating-panel">
            <div className="floating-title">
              <strong>Map layers</strong>
              <button
                className="icon-button"
                onClick={() => setLayersOpen(false)}
                aria-label="Close layers"
              >
                <X size={14} />
              </button>
            </div>
            <label>
              <input type="checkbox" checked={showSuggestions} onChange={toggleSuggestions} />
              <span>Model suggestions</span>
              <Dot color="#cfb96d" />
            </label>
            <label>
              <input type="checkbox" checked={showLabels} onChange={toggleLabels} />
              <span>Labeled samples</span>
              <Dot color="#3f9c70" />
            </label>
            <div className="opacity-label">
              <span>Raster opacity</span>
              <strong>{opacity}%</strong>
            </div>
            <input
              aria-label="Raster opacity"
              type="range"
              min={0}
              max={100}
              value={opacity}
              onChange={(e) => setOpacity(Number(e.target.value))}
            />

            <div className="layer-divider">
              <span>MODEL LAYERS</span>
              {hasModel && (
                <span className="layer-caption">
                  {(() => {
                    const field = classification.data ?? uncertainty.data;
                    const cellPx = field?.grid.patchSize ?? dataset.patchGrid?.patchSize ?? 32;
                    // A patch-cell field is one value per cell replicated over the
                    // cell's pixels; saying "pixel-level" there would overclaim.
                    return field?.resolution === 'pixel'
                      ? `pixel-level · 1 cell = ${cellPx} px`
                      : `patch cells · 1 cell = ${cellPx} px`;
                  })()}
                </span>
              )}
            </div>

            {!hasModel ? (
              <p className="layer-note">
                Train a model to see its classification and where it is unsure.
              </p>
            ) : modelBandsMismatch ? (
              <p className="layer-note">
                This model was trained on a different number of bands than this scene has.
              </p>
            ) : (
              <>
                <label>
                  <input
                    type="checkbox"
                    checked={showClassification}
                    onChange={toggleClassification}
                  />
                  <span>Classification</span>
                  {classification.isFetching && <LoaderCircle size={11} className="spin" />}
                </label>
                {showClassification && (
                  <>
                    <input
                      aria-label="Classification opacity"
                      type="range"
                      min={0}
                      max={100}
                      value={classificationOpacity}
                      onChange={(e) => setClassificationOpacity(Number(e.target.value))}
                    />
                    <div className="layer-classes">
                      {(classification.data?.classes ?? project.classes.map((c) => c.name)).map(
                        (name, index) => (
                          <button
                            key={name}
                            className={cn(
                              'layer-class',
                              !hiddenClasses.includes(name) && 'active',
                            )}
                            onClick={() => toggleClassVisibility(name)}
                            title={`${hiddenClasses.includes(name) ? 'Show' : 'Hide'} ${name}`}
                          >
                            <Dot
                              color={
                                classification.data?.colors?.[index] ??
                                project.classes[index]?.color ??
                                '#d8bd68'
                              }
                            />
                            {name}
                          </button>
                        ),
                      )}
                    </div>
                  </>
                )}

                <label>
                  <input type="checkbox" checked={showUncertainty} onChange={toggleUncertainty} />
                  <span>Uncertainty</span>
                  {uncertainty.isFetching && <LoaderCircle size={11} className="spin" />}
                </label>
                {showUncertainty && (
                  <>
                    <select
                      className="input layer-method"
                      aria-label="Uncertainty method"
                      value={uncertaintyMethod}
                      onChange={(e) => setUncertaintyMethod(e.target.value as UncertaintyMethod)}
                    >
                      <option value="entropy">Entropy</option>
                      <option value="margin">Margin</option>
                      <option value="least_confidence">Least confidence</option>
                    </select>
                    <input
                      aria-label="Uncertainty opacity"
                      type="range"
                      min={0}
                      max={100}
                      value={uncertaintyOpacity}
                      onChange={(e) => setUncertaintyOpacity(Number(e.target.value))}
                    />
                  </>
                )}

                {(classification.data?.stale || uncertainty.data?.stale) && (
                  <p className="layer-stale">
                    These maps come from iteration{' '}
                    {uncertainty.data?.modelIteration ?? classification.data?.modelIteration} —
                    a newer training run exists.
                  </p>
                )}

                {(showClassification || showUncertainty) && (
                  <div className="layer-export">
                    <span>Export {showUncertainty ? 'uncertainty' : 'classification'}</span>
                    <div>
                      {(['tif', 'png', 'csv'] as MapExportFormat[]).map((format) => (
                        <a
                          key={format}
                          className="layer-export-link"
                          href={api.mapExportUrl(project.id, {
                            layer: showUncertainty ? 'uncertainty' : 'hard',
                            format,
                            method: uncertaintyMethod,
                            datasetId: dataset.id,
                          })}
                        >
                          {format.toUpperCase()}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
        {tool !== 'pan' && (
          <div className="drawing-hint">
            <MousePointer2 size={13} />
            {tool === 'point'
              ? 'Click to add a labeled point'
              : tool === 'rectangle'
                ? 'Click two opposite corners'
                : 'Click to add vertices · double-click to finish'}
          </div>
        )}
        <div className="map-bottom-left">
          <div className="map-suggestion-badge">
            <span className="suggestion-ring" />
            Model suggestions<span>{samples.filter((s) => s.status === 'pending').length}</span>
          </div>
          <span className="map-coordinate">
            {(selected?.lat ?? 38.515).toFixed(4)}° N &nbsp;{' '}
            {Math.abs(selected?.lng ?? -121.67).toFixed(4)}° W
          </span>
        </div>
        <div className="map-zoom-controls">
          <button onClick={() => command('in')} title="Zoom in" aria-label="Zoom in">
            <Plus size={19} />
          </button>
          <button onClick={() => command('out')} title="Zoom out" aria-label="Zoom out">
            <Minus size={19} />
          </button>
          <button
            onClick={() => command('focus')}
            title="Locate selected sample"
            aria-label="Locate selected sample"
          >
            <Crosshair size={18} />
          </button>
        </div>
        <div className="map-attribution">
          {dataset.pixelSpace ? (
            <>
              Pixel space · no basemap
              <span className="georef-reason">{GEOREF_MESSAGES[dataset.georefReason ?? 'not-georeferenced']}</span>
            </>
          ) : (
            <>Basemap © Esri · Uploaded imagery</>
          )}
        </div>
      </div>
      <div className="class-legend">
        <span className="legend-heading">CLASSES</span>
        <div>
          {project.classes.map((c, i) => (
            <button
              className={cn(activeClass === c.id && 'active')}
              key={c.id}
              onClick={() => setActiveClass(c.id)}
              title={`Draw ${c.name} samples · ${i + 1}`}
            >
              <Dot color={c.color} />
              {c.name}
            </button>
          ))}
        </div>
        {showUncertainty && uncertainty.data && (
          <div className="uncertainty-legend">
            <span className="legend-heading">
              UNCERTAINTY · {methodLabel(uncertaintyMethod).toUpperCase()}
            </span>
            <div
              className="uncertainty-ramp"
              style={{
                background: `linear-gradient(90deg, ${UNCERTAINTY_RAMP.join(', ')})`,
              }}
            />
            <div className="uncertainty-scale">
              <span>{uncertainty.data.min.toFixed(2)} confident</span>
              <span>{uncertainty.data.max.toFixed(2)} unsure</span>
            </div>
            <span className="uncertainty-note">
              Colour stretched over this scene&apos;s range
            </span>
          </div>
        )}
        <span className="legend-count">
          {showClassification || showUncertainty
            ? `iter ${uncertainty.data?.modelIteration ?? classification.data?.modelIteration ?? project.iteration}`
            : `${project.classes.length} classes`}
        </span>
      </div>
      <div className="map-metadata">
        <span>
          <span className="online-dot" /> GeoTIFF
          <i /> {dataset.resolution} resolution
          <i />
          {dataset.crs}
        </span>
        <span>
          <Layers size={12} />
          {dataset.bands} bands
        </span>
      </div>
    </div>
  );
}
