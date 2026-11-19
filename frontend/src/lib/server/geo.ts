/**
 * Server-side geo helpers for the label adapter.
 *
 * Shares `$lib/geo` with the browser so the adapter and the map can never
 * disagree about where a pixel is.
 */
export {
  applyAffine,
  approximateAreaKm2,
  assessGeoreferencing,
  cellWindow,
  datasetBounds,
  invertAffine,
  isAxisAligned,
  mapToPixel,
  normalizeCrs,
  ringArea,
  toWgs84,
} from '$lib/geo';
export type { Bounds, GeoContext, GeorefReason, PixelWindow, XY } from '$lib/geo';
