/**
 * Button variants — a plain variant map rather than `tailwind-variants`.
 *
 * The visual language here is CSS custom properties (`--accent`, `--border`, …),
 * not Tailwind utilities, so the "variants record" is the whole mechanism:
 * `variantOf` picks the class string and `cn` de-duplicates overrides.
 */
export const buttonVariants = {
  default: 'btn',
  primary: 'btn btn-primary',
  secondary: 'btn btn-secondary',
  ghost: 'btn btn-ghost',
  destructive: 'btn btn-destructive',
  link: 'btn-link',
} as const;

export const buttonSizes = {
  default: '',
  sm: 'btn-sm',
  icon: 'btn-icon',
} as const;

export type ButtonVariant = keyof typeof buttonVariants;
export type ButtonSize = keyof typeof buttonSizes;
