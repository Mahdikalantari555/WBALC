'use client';
import { useQuery } from '@tanstack/react-query';
import { renderRaster } from '@/lib/geotiff';
import type { Dataset } from '@/types';

/**
 * True-colour PNG of the whole scene, rendered in the browser from the original
 * GeoTIFF. Shares the cached, range-reading dataset handle with the map and the
 * review thumbnails, so a dataset is parsed once per session.
 */
export function useRasterPreview(dataset: Dataset | null | undefined) {
  return useQuery({
    queryKey: ['raster-preview', dataset?.id],
    queryFn: () => renderRaster({ url: dataset!.url, datasetId: dataset!.id }),
    enabled: !!dataset,
    staleTime: Infinity,
    retry: 0,
  });
}
