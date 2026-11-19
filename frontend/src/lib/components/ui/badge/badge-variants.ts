/**
 * Status colours are semantic, not decorative:
 *
 * - `success`  the engine measured it and it passed (`status: ok`, verified artifact)
 * - `warning`  it exists but is limited (insufficient split, unaligned grid, stale)
 * - `muted`    not applicable / not established — the honest "we have nothing"
 * - `info`     neutral provenance (protocol kind, class count)
 * - `danger`   refused, tampered, failed
 */
export const badgeVariants = {
  default: 'badge',
  success: 'badge badge-success',
  warning: 'badge badge-warning',
  muted: 'badge badge-muted',
  info: 'badge badge-info',
  danger: 'badge badge-danger',
} as const;

export type BadgeVariant = keyof typeof badgeVariants;
