import type { ClassDefinition } from '@/types';

/** Deterministic display palette; RSAL classes are plain names. */
export const CLASS_COLORS = [
  '#5cbb96',
  '#e0a458',
  '#7d9bd4',
  '#c97b9b',
  '#9b8cd4',
  '#d4c95c',
  '#6bb8c9',
  '#d47b6b',
  '#8bc96b',
  '#b0b7c3',
  '#c9a0dc',
];

export const DEFAULT_CLASS_NAMES = ['open_water', 'emergent_vegetation', 'land'];

export function classesFromNames(names: string[]): ClassDefinition[] {
  return names.map((name, i) => ({
    id: name,
    name,
    color: CLASS_COLORS[i % CLASS_COLORS.length],
  }));
}

export function colorForClass(name: string, classes: ClassDefinition[]): string {
  return classes.find((c) => c.id === name)?.color ?? '#d8bd68';
}
