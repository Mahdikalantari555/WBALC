/**
 * Near-date grouping: acquisitions that fall within `NEAR_DAYS` of each other
 * form one epoch. Sensor fusion is expected to operate at feature level on
 * such groups, so the map treats them as one date step rather than scattering
 * every acquisition on its own.
 */
import type { SceneView } from './types';

export const NEAR_DAYS = 3;

/** Chronological epochs; consecutive acquisitions closer than `nearDays` share one group. */
export function groupEpochs(scenes: SceneView[], nearDays: number = NEAR_DAYS): SceneView[][] {
  const dated = scenes
    .filter(candidate => Boolean(candidate.acquisitionDateTime))
    .slice()
    .sort((a, b) => (a.acquisitionDateTime! < b.acquisitionDateTime! ? -1 : 1));
  const groups: SceneView[][] = [];
  for (const candidate of dated) {
    const last = groups[groups.length - 1];
    const previous = last?.[last.length - 1];
    const gapDays = previous
      ? (Date.parse(candidate.acquisitionDateTime!) - Date.parse(previous.acquisitionDateTime!)) / 86_400_000
      : Number.POSITIVE_INFINITY;
    if (!last || gapDays > nearDays) groups.push([candidate]);
    else last.push(candidate);
  }
  return groups;
}

/** "2025-06-01 → 2025-06-03", or the single date when the epoch spans one day. */
export function epochLabel(group: SceneView[]): string {
  const first = group[0].acquisitionDateTime!.slice(0, 10);
  const last = group[group.length - 1].acquisitionDateTime!.slice(0, 10);
  return first === last ? first : `${first} → ${last}`;
}

/** The scene of an epoch the map should show: keep the current one, prefer Sentinel-2, else earliest. */
export function primaryScene(group: SceneView[], currentId?: string | null): SceneView {
  return group.find(candidate => candidate.id === currentId)
    ?? group.find(candidate => candidate.sensor === 'Sentinel-2')
    ?? group[0];
}
