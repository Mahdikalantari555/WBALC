'use client';
import { useCallback, useEffect, useRef } from 'react';
import { ImageOverlay, MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import type { Bounds, Dataset } from '@/types';

export type SomMapAction = { kind: 'in' | 'out' | 'fit'; nonce: number };

interface SomClusterMapProps {
  dataset: Dataset;
  rasterUrl: string | null;
  clusterOverlayUrl: string | null;
  baseOpacity: number;
  clusterOpacity: number;
  showClusters: boolean;
  action: SomMapAction | null;
}

const asLeaflet = (b: Bounds): [[number, number], [number, number]] => [
  [b[1], b[0]],
  [b[3], b[2]],
];

function MapController({
  dataset,
  action,
}: {
  dataset: Dataset;
  action: SomMapAction | null;
}) {
  const map = useMap();
  const previousDataset = useRef('');

  const fit = useCallback(() => {
    const bounds = L.latLngBounds(asLeaflet(dataset.bounds));
    map.invalidateSize();
    map.setView(bounds.getCenter(), map.getBoundsZoom(bounds, true), { animate: false });
  }, [dataset.bounds, map]);

  useEffect(() => {
    if (previousDataset.current !== dataset.id) {
      fit();
      previousDataset.current = dataset.id;
    }
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [dataset.id, fit, map]);

  useEffect(() => {
    if (!action) return;
    if (action.kind === 'in') map.zoomIn();
    if (action.kind === 'out') map.zoomOut();
    if (action.kind === 'fit') fit();
  }, [action, fit, map]);

  return null;
}

export default function SomClusterMap({
  dataset,
  rasterUrl,
  clusterOverlayUrl,
  baseOpacity,
  clusterOpacity,
  showClusters,
  action,
}: SomClusterMapProps) {
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
      className="satellite-map som-leaflet-map"
      style={{ background: '#263329' }}
    >
      {!dataset.pixelSpace && (
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          maxZoom={19}
        />
      )}
      {rasterUrl && (
        <ImageOverlay
          key={`base-${dataset.id}-${rasterUrl.slice(-24)}`}
          url={rasterUrl}
          bounds={asLeaflet(bounds)}
          opacity={baseOpacity / 100}
        />
      )}
      {showClusters && clusterOverlayUrl && (
        <ImageOverlay
          key={`som-${dataset.id}-${clusterOverlayUrl.slice(-28)}`}
          url={clusterOverlayUrl}
          bounds={asLeaflet(bounds)}
          opacity={clusterOpacity / 100}
        />
      )}
      <MapController dataset={dataset} action={action} />
    </MapContainer>
  );
}
