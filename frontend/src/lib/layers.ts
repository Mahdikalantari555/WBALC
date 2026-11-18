/** Vocabulary shared by the map layers, the adapter and the exports. */
export const UNCERTAINTY_METHODS = ['entropy', 'margin', 'least_confidence'] as const;
export type UncertaintyMethod = (typeof UNCERTAINTY_METHODS)[number];

export const MAP_LAYERS = ['hard', 'uncertainty', 'probability'] as const;

export function isUncertaintyMethod(value: unknown): value is UncertaintyMethod {
  return typeof value === 'string' && (UNCERTAINTY_METHODS as readonly string[]).includes(value);
}
