'use client';
import { useMemo, useState } from 'react';
import { DeckGL } from '@deck.gl/react';
import { BitmapLayer } from '@deck.gl/layers';
import type { Dataset } from '@/types';
export default function DeckPreview({
  dataset,
  imageUrl,
}: {
  dataset: Dataset;
  imageUrl: string | null;
}) {
  const [error, setError] = useState(false);
  const bounds = dataset.bounds;
  const layers = useMemo(
    () =>
      imageUrl
        ? [
            new BitmapLayer({
              id: 'geotiff-raster',
              image: imageUrl,
              bounds,
              opacity: 1,
              pickable: true,
            }),
          ]
        : [],
    [imageUrl, bounds],
  );
  if (!imageUrl)
    return (
      <div className="webgl-fallback">
        <p>Rendering the raster preview…</p>
      </div>
    );
  if (error || dataset.pixelSpace)
    return (
      <div className="webgl-fallback">
        <img src={imageUrl} alt={`${dataset.name} raster preview`} />
        <p>
          {dataset.pixelSpace
            ? 'This scene has no coordinate system — showing the 2D raster preview.'
            : 'WebGL is unavailable. Showing the 2D raster preview.'}
        </p>
      </div>
    );
  const span = Math.max(bounds[2] - bounds[0], 1e-6);
  const zoom = Math.min(18, Math.max(1, Math.log2(360 / span) - 1));
  return (
    <div className="deck-preview">
      <DeckGL
        initialViewState={{
          longitude: (bounds[0] + bounds[2]) / 2,
          latitude: (bounds[1] + bounds[3]) / 2,
          zoom,
          pitch: 30,
          bearing: 0,
        }}
        controller
        layers={layers}
        onError={() => setError(true)}
        getTooltip={({ coordinate }) =>
          coordinate ? `${coordinate[1].toFixed(5)}°, ${coordinate[0].toFixed(5)}°` : null
        }
      />
      <span className="deck-hint">Drag to pan · scroll to zoom · Shift + drag to tilt</span>
    </div>
  );
}
