/**
 * Alert — the surface for a statement about the *evidence*, not styling flavour.
 * `warning` and `destructive` carry text the user must read before trusting a
 * number, so they are never collapsed into a colour-only cue.
 */
export const alertVariants = {
  default: 'alert',
  warning: 'alert alert-warning',
  destructive: 'alert alert-destructive',
  success: 'alert alert-success',
} as const;

export type AlertVariant = keyof typeof alertVariants;
