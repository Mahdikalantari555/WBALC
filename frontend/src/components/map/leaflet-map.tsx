'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CircleMarker,
  ImageOverlay,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  Rectangle,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import L, { type LatLng, type LatLngBoundsExpression, type LatLngExpression } from 'leaflet';
import { useWorkspace } from '@/stores/workspace';
import { datasetGeoContext, overlayTransform } from '@/lib/geo';
import { fieldToDataUrl } from '@/lib/overlay';
import type { Bounds, Dataset, MapField, Project, Sample, SampleGeometry } from '@/types';
export type MapAction = { kind: 'in' | 'out' | 'fit' | 'focus' | 'undo'; nonce: number };
interface Props {
  dataset: Dataset;
  datasetIds: string[];
  classification: MapField | null;
  uncertainty: MapField | null;
  classificationOpacity: number;
  uncertaintyOpacity: number;
  hiddenClasses: string[];
  rasterUrl: string;
  project: Project;
  samples: Sample[];
  action: MapAction | null;
  onDraw: (lat: number, lng: number, geometry: SampleGeometry) => void;
}
const asLeaflet = (b: Bounds): [[number, number], [number, number]] => [
  [b[1], b[0]],
  [b[3], b[2]],
];
function Controller({
  dataset,
  action,
  selected,
}: {
  dataset: Dataset;
  action: MapAction | null;
  selected: Sample | undefined;
}) {
  const map = useMap();
  const previousDataset = useRef('');
  const fit = () => {
    const bounds = L.latLngBounds(asLeaflet(dataset.bounds));
    map.invalidateSize();
    map.setView(bounds.getCenter(), map.getBoundsZoom(bounds, true), { animate: false });
  };
  useEffect(() => {
    if (previousDataset.current !== dataset.id) {
      fit();
      previousDataset.current = dataset.id;
    }
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [dataset.id, map]);
  useEffect(() => {
    if (!action) return;
    if (action.kind === 'in') map.zoomIn();
    if (action.kind === 'out') map.zoomOut();
    if (action.kind === 'fit') fit();
    if (action.kind === 'focus' && selected) {
      if (selected.bbox)
        map.flyToBounds(
          [
            [selected.bbox[1], selected.bbox[0]],
            [selected.bbox[3], selected.bbox[2]],
          ],
          { padding: [80, 80], maxZoom: dataset.pixelSpace ? 6 : 19, duration: 0.6 },
        );
      else
        map.flyTo([selected.lat, selected.lng], Math.max(map.getZoom(), dataset.pixelSpace ? 2 : 14), {
          duration: 0.6,
        });
    }
  }, [action]);
  useEffect(() => {
    if (selected && !map.getBounds().contains([selected.lat, selected.lng]))
      map.panTo([selected.lat, selected.lng], { animate: true, duration: 0.4 });
  }, [selected?.id]);
  return null;
}
/**
 * The raster, painted through the same corner fit that positions every marker.
 *
 * For a north-up scene the fit is a plain scale, so this is equivalent to a
 * stretched image. For anything else (zone convergence, rotated transforms) the
 * image is warped sheared in the canvas instead of being fitted into an
 * axis-aligned rectangle that would put the imagery up to a few patches away
 * from the labels drawn on top of it.
 */
/**
 * A model-derived field painted one pixel per grid cell, then warped onto the
 * display bbox exactly like the imagery. Cells therefore sit on the same ground
 * as the patch footprints, at every zoom.
 */
function FieldOverlay({
  dataset,
  field,
  opacity,
  hiddenClassIndexes,
}: {
  dataset: Dataset;
  field: MapField;
  opacity: number;
  hiddenClassIndexes: number[];
}) {
  const visible = useMemo(() => {
    if (field.layer !== 'hard' || !hiddenClassIndexes.length) return field;
    const hidden = new Set(hiddenClassIndexes);
    return {
      ...field,
      valid: field.valid.map((row, r) =>
        row.map((ok, c) => ok && !hidden.has(Number(field.values[r][c]))),
      ),
    };
  }, [field, hiddenClassIndexes]);
  const source = useMemo(() => fieldToDataUrl(visible, 1), [visible]);
  if (!source) return null;
  return (
    <ImageOverlay
      url={source}
      bounds={asLeaflet(dataset.bounds)}
      opacity={opacity / 100}
      className={`field-overlay field-overlay-${field.layer}`}
      zIndex={field.layer === 'hard' ? 3 : 4}
    />
  );
}

function RasterOverlay({
  dataset,
  rasterUrl,
  opacity,
}: {
  dataset: Dataset;
  rasterUrl: string;
  opacity: number;
}) {
  const ctx = useMemo(() => datasetGeoContext(dataset), [dataset]);
  // No fit => the PNG is already in the display frame (pixel space).
  const matrix = useMemo(() => overlayTransform(ctx, 1, 1), [ctx]);
  const [warped, setWarped] = useState<{ key: string; url: string } | null>(null);
  const key = `${dataset.id}:${rasterUrl.length}:${rasterUrl.slice(-24)}`;

  useEffect(() => {
    if (!matrix) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch(rasterUrl);
        if (!response.ok) throw new Error('Raster unavailable');
        const bitmap = await createImageBitmap(await response.blob());
        const width = 1600;
        const height = Math.max(1, Math.round((1600 * dataset.height) / dataset.width));
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Canvas unavailable');
        context.imageSmoothingQuality = 'high';
        // Paint the source pixels through the corner fit, so the image and the
        // markers (placed with the same fit) stay aligned at every zoom.
        context.setTransform(
          matrix[0] * width,
          matrix[3] * height,
          matrix[1] * width,
          matrix[4] * height,
          matrix[2] * width,
          matrix[5] * height,
        );
        context.drawImage(bitmap, 0, 0, dataset.width, dataset.height);
        bitmap.close?.();
        if (!cancelled) setWarped({ key, url: canvas.toDataURL('image/png') });
      } catch {
        if (!cancelled) setWarped({ key, url: rasterUrl });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [matrix, rasterUrl, key, dataset.width, dataset.height]);

  const source = !matrix ? rasterUrl : warped?.key === key ? warped.url : null;
  if (!source) return null;
  return (
    <ImageOverlay url={source} bounds={asLeaflet(dataset.bounds)} opacity={opacity / 100} />
  );
}

function DrawControls({ onDraw, action }: { onDraw: Props['onDraw']; action: MapAction | null }) {
  const { tool, setTool, activeClass } = useWorkspace();
  const [points, setPoints] = useState<LatLng[]>([]);
  const [cursor, setCursor] = useState<LatLng | null>(null);
  const map = useMapEvents({
    click(e) {
      if (tool === 'pan') return;
      if (tool === 'point') {
        onDraw(e.latlng.lat, e.latlng.lng, {
          type: 'Point',
          coordinates: [e.latlng.lng, e.latlng.lat],
        });
        return;
      }
      if (tool === 'rectangle' && points.length === 1) {
        const first = points[0];
        const last = e.latlng;
        const ring = [
          [first.lng, first.lat],
          [last.lng, first.lat],
          [last.lng, last.lat],
          [first.lng, last.lat],
          [first.lng, first.lat],
        ];
        onDraw((first.lat + last.lat) / 2, (first.lng + last.lng) / 2, {
          type: 'Polygon',
          coordinates: [ring],
        });
        setPoints([]);
        setCursor(null);
        return;
      }
      setPoints((previous) => [...previous, e.latlng]);
    },
    mousemove(e) {
      if (tool !== 'pan') setCursor(e.latlng);
    },
    dblclick(e) {
      if (tool === 'polygon' && points.length >= 3) {
        L.DomEvent.stop(e.originalEvent);
        const ring = points.map((p) => [p.lng, p.lat]);
        ring.push(ring[0]);
        onDraw(
          points.reduce((a, p) => a + p.lat, 0) / points.length,
          points.reduce((a, p) => a + p.lng, 0) / points.length,
          { type: 'Polygon', coordinates: [ring] },
        );
        setPoints([]);
        setCursor(null);
      }
    },
  });
  useEffect(() => {
    // Reset in-progress drawing when the active tool changes (external sync).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPoints([]);
    setCursor(null);
    if (tool === 'pan') {
      map.dragging.enable();
      map.doubleClickZoom.enable();
      map.getContainer().style.cursor = 'grab';
    } else {
      map.doubleClickZoom.disable();
      if (tool === 'point') map.dragging.enable();
      else map.dragging.disable();
      map.getContainer().style.cursor = 'crosshair';
    }
  }, [tool, map, activeClass]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPoints([]);
        setCursor(null);
        setTool('pan');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setTool]);
  useEffect(() => {
    // Toolbar undo command arrives as an external action signal.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (action?.kind === 'undo') setPoints((p) => p.slice(0, -1));
  }, [action]);
  if (tool === 'rectangle' && points[0] && cursor)
    return (
      <Rectangle
        bounds={L.latLngBounds(points[0], cursor)}
        pathOptions={{
          color: '#fff',
          fillColor: '#5cbb96',
          fillOpacity: 0.2,
          weight: 2,
          dashArray: '5 4',
        }}
      />
    );
  if (tool === 'polygon' && points.length)
    return (
      <>
        <Polyline
          positions={[...points, ...(cursor ? [cursor] : [])]}
          pathOptions={{ color: '#fff', weight: 2, dashArray: '5 4' }}
        />
        {points.map((p, i) => (
          <CircleMarker
            key={i}
            center={p}
            radius={4}
            pathOptions={{ color: '#fff', fillColor: '#228268', fillOpacity: 1 }}
          />
        ))}
      </>
    );
  return null;
}
export default function LeafletMap({
  dataset,
  datasetIds,
  classification,
  uncertainty,
  classificationOpacity,
  uncertaintyOpacity,
  hiddenClasses,
  rasterUrl,
  project,
  samples,
  action,
  onDraw,
}: Props) {
  const { selectedSampleId, selectSample, drafts, opacity, showLabels, showSuggestions } =
    useWorkspace();
  const allSamples = useMemo(() => {
    const merged = samples.map((s) => ({
      ...s,
      ...(drafts[s.id] ? { label: drafts[s.id].label, status: drafts[s.id].status } : {}),
    }));
    Object.values(drafts)
      .filter(
        (d) =>
          !samples.some((s) => s.id === d.sampleId) && d.lat !== undefined && d.lng !== undefined,
      )
      .forEach((d) =>
        merged.push({
          id: d.sampleId,
          projectId: project.id,
          lat: d.lat!,
          lng: d.lng!,
          prediction: d.label ?? project.classes[0].id,
          confidence: 1,
          uncertainty: 0,
          status: d.status,
          label: d.label,
          note: d.note,
          iteration: project.iteration,
          batchIndex: 1000,
          geometry: d.geometry ?? null,
          source: 'manual',
        }),
      );
    return merged;
  }, [samples, drafts, project]);

  // Only draw what belongs to the dataset on screen. Samples of other scenes
  // carry coordinates from a different CRS/extent and would land on the wrong
  // ground — which is exactly the "point doesn't match the imagery" report.
  const visibleSamples = useMemo(
    () =>
      allSamples.filter(
        (s) => !s.datasetId || s.datasetId === dataset.id || datasetIds.length <= 1,
      ),
    [allSamples, dataset.id, datasetIds],
  );
  const selected = visibleSamples.find((s) => s.id === selectedSampleId);
  const [hovered, setHovered] = useState<string | null>(null);
  const bounds = dataset.bounds;
  return (
    <MapContainer
      key={dataset.id}
      center={[(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]}
      zoom={dataset.pixelSpace ? 0 : 12}
      crs={dataset.pixelSpace ? L.CRS.Simple : L.CRS.EPSG3857}
      minZoom={dataset.pixelSpace ? -4 : 2}
      maxZoom={21}
      zoomSnap={0.25}
      zoomControl={false}
      attributionControl={false}
      className="satellite-map"
      style={{ background: '#2e3b2b' }}
    >
      {!dataset.pixelSpace && (
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          maxZoom={19}
        />
      )}
      <RasterOverlay
        dataset={dataset}
        rasterUrl={rasterUrl}
        opacity={opacity}
      />
      {classification && (
        <FieldOverlay
          dataset={dataset}
          field={classification}
          opacity={classificationOpacity}
          hiddenClassIndexes={hiddenClasses.map((name) =>
            classification.classes.indexOf(name),
          )}
        />
      )}
      {uncertainty && (
        <FieldOverlay
          dataset={dataset}
          field={uncertainty}
          opacity={uncertaintyOpacity}
          hiddenClassIndexes={[]}
        />
      )}
      <Controller dataset={dataset} action={action} selected={selected} />
      <DrawControls onDraw={onDraw} action={action} />
      {visibleSamples
        .filter((s) => (s.status === 'pending' ? showSuggestions : showLabels))
        .map((sample) => {
          const isSelected = sample.id === selectedSampleId;
          const color =
            project.classes.find((c) => c.id === (sample.label ?? sample.prediction))?.color ??
            '#d8bd68';
          const positions =
            sample.geometry?.type === 'Polygon'
              ? (sample.geometry.coordinates as number[][][])[0].map(
                  ([lng, lat]) => [lat, lng] as LatLngExpression,
                )
              : null;
          const marker = L.divIcon({
            className: 'sample-marker',
            html: `<span class="marker-dot ${isSelected ? 'selected' : ''} ${sample.status === 'labeled' ? 'reviewed' : ''} ${sample.status === 'skipped' ? 'skipped' : ''}" style="--marker-color:${color}">${sample.status === 'labeled' ? '✓' : sample.status === 'skipped' ? '–' : String(sample.batchIndex + 1).padStart(2, '0')}</span>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15],
          });
          return (
            <span key={sample.id}>
              {positions && (
                <Polygon
                  positions={positions}
                  pathOptions={{ color, fillColor: color, fillOpacity: 0.22, weight: 2 }}
                  eventHandlers={{ click: () => selectSample(sample.id) }}
                />
              )}
              {/* The patch footprint: the same window the thumbnail crops, so
                  the two are directly comparable at any zoom. */}
              {sample.bbox && (isSelected || hovered === sample.id) && (
                <Rectangle
                  bounds={[
                    [sample.bbox[1], sample.bbox[0]],
                    [sample.bbox[3], sample.bbox[2]],
                  ]}
                  pathOptions={{
                    color: isSelected ? '#f3e8a0' : '#ffffff',
                    weight: isSelected ? 1.5 : 1,
                    fillColor: isSelected ? '#e8d277' : '#ffffff',
                    fillOpacity: isSelected ? 0.13 : 0.05,
                    dashArray: '5 4',
                  }}
                />
              )}
              <Marker
                position={[sample.lat, sample.lng]}
                icon={marker}
                zIndexOffset={isSelected ? 100 : 0}
                eventHandlers={{
                  click: () => selectSample(sample.id),
                  mouseover: () => setHovered(sample.id),
                  mouseout: () => setHovered((current) => (current === sample.id ? null : current)),
                }}
              >
                <Tooltip direction="top" offset={[0, -15]}>
                  {project.classes.find((c) => c.id === (sample.label ?? sample.prediction))?.name}{' '}
                  ·{' '}
                  {sample.status === 'pending'
                    ? `${Math.round(sample.confidence * 100)}% confidence`
                    : sample.status}
                </Tooltip>
              </Marker>
            </span>
          );
        })}
    </MapContainer>
  );
}
