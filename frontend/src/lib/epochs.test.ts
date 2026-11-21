import { describe, expect, it } from 'vitest';
import { NEAR_DAYS, epochLabel, groupEpochs, primaryScene } from './epochs';
import type { SceneView } from './types';

function scene(id: string, date: string, sensor = 'Sentinel-2'): SceneView {
  return {
    id, projectId: '1', sensor, acquisitionDateTime: date,
  } as SceneView;
}

const zarivar = [
  scene('6', '2025-01-02T07:42:29Z'),
  scene('10', '2025-01-04T14:52:52Z', 'Sentinel-1'),
  scene('7', '2025-03-13T07:36:19Z'),
  scene('11', '2025-03-11T03:02:28Z', 'Sentinel-1'),
  scene('8', '2025-06-01T07:36:19Z'),
  scene('12', '2025-06-03T00:00:00Z', 'Sentinel-1'),
  scene('9', '2025-09-04T07:36:31Z'),
  scene('13', '2025-09-02T00:00:00Z', 'Sentinel-1'),
];

describe('groupEpochs', () => {
  it('sticks near-date acquisitions together across sensors', () => {
    const groups = groupEpochs(zarivar);
    expect(groups.length).toBe(4);
    expect(groups[0].map(s => s.id)).toEqual(['6', '10']);
    expect(groups[1].map(s => s.id)).toEqual(['11', '7']);
    expect(groups[2].map(s => s.id)).toEqual(['8', '12']);
    expect(groups[3].map(s => s.id)).toEqual(['13', '9']);
  });

  it('labels single-day and multi-day epochs differently', () => {
    const [group] = groupEpochs([scene('1', '2025-06-01T00:00:00Z'), scene('2', '2025-06-03T00:00:00Z', 'Sentinel-1')]);
    expect(epochLabel(group)).toBe('2025-06-01 → 2025-06-03');
    const [single] = groupEpochs([scene('1', '2025-06-01T00:00:00Z')]);
    expect(epochLabel(single)).toBe('2025-06-01');
  });

  it('keeps undated scenes out of the timeline', () => {
    const groups = groupEpochs([scene('1', '2025-06-01T00:00:00Z'), scene('2', '', 'Sentinel-1')]);
    expect(groups.length).toBe(1);
    expect(groups[0].length).toBe(1);
  });

  it('splits acquisitions further apart than the near-date window', () => {
    const groups = groupEpochs([scene('1', '2025-06-01T00:00:00Z'), scene('2', '2025-06-10T00:00:00Z')]);
    expect(groups.length).toBe(2);
  });

  it('prefers the current scene, then Sentinel-2, then the earliest', () => {
    const group = groupEpochs(zarivar)[0];
    expect(primaryScene(group, '10').id).toBe('10');
    expect(primaryScene(group).id).toBe('6');
    const s1Only = groupEpochs([scene('a', '2025-06-01T00:00:00Z', 'Sentinel-1'), scene('b', '2025-06-02T00:00:00Z', 'Sentinel-1')]);
    expect(primaryScene(s1Only[0]).id).toBe('a');
  });

  it('keeps the documented near-date window', () => {
    expect(NEAR_DAYS).toBe(3);
  });
});
