import { describe, expect, it } from 'vitest';
import { normalizeStudyArea } from './study-area';

const ring = [[0, 0], [2, 0], [2, 1], [0, 0]];

describe('study-area GeoJSON intake', () => {
  it('accepts bare Polygon and MultiPolygon geometries', () => {
    expect(normalizeStudyArea({ type: 'Polygon', coordinates: [ring] })).toEqual({
      geometry: { type: 'Polygon', coordinates: [ring] }, crs: 'EPSG:4326',
    });
    const multi = { type: 'MultiPolygon', coordinates: [[ring], [[[3, 0], [4, 0], [4, 1], [3, 0]]]] };
    expect(normalizeStudyArea(multi).geometry).toEqual(multi);
  });

  it('accepts Feature and combines a polygon FeatureCollection into MultiPolygon', () => {
    const feature = { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } };
    expect(normalizeStudyArea(feature).geometry).toEqual(feature.geometry);
    const featureWithCrs = {
      ...feature, crs: { type: 'name', properties: { name: 'urn:ogc:def:crs:EPSG::32721' } },
    };
    expect(normalizeStudyArea(featureWithCrs).crs).toBe('EPSG:32721');
    const collection = {
      type: 'FeatureCollection',
      crs: { type: 'name', properties: { name: 'urn:ogc:def:crs:EPSG::32638' } },
      features: [
        feature,
        { type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: [[[[3, 0], [4, 0], [4, 1], [3, 0]]]] } },
      ],
    };
    const result = normalizeStudyArea(collection);
    expect(result.geometry.type).toBe('MultiPolygon');
    expect((result.geometry.coordinates as unknown[]).length).toBe(2);
    expect(result.crs).toBe('EPSG:32638');
    const childCrsCollection = { type: 'FeatureCollection', features: [featureWithCrs] };
    expect(normalizeStudyArea(childCrsCollection).crs).toBe('EPSG:32721');
    expect(() => normalizeStudyArea({ ...childCrsCollection, crs: 'EPSG:4326' })).toThrow();
  });

  it('rejects invalid and non-polygon features with a clear validation failure', () => {
    expect(() => normalizeStudyArea({ type: 'Point', coordinates: [1, 2] })).toThrow();
    expect(() => normalizeStudyArea({ type: 'FeatureCollection', features: [] })).toThrow();
    expect(() => normalizeStudyArea({ type: 'Polygon', coordinates: [[[0, 0], [1, 1]]] })).toThrow();
    expect(() => normalizeStudyArea({ type: 'Polygon', coordinates: [[[0, 0], ['1', 0], [1, 1], [0, 0]]] })).toThrow();
    expect(() => normalizeStudyArea({ type: 'Polygon', coordinates: [[[0, 0], [1, 0, 4], [1, 1], [0, 0]]] })).toThrow();
  });
});
