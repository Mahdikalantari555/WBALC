export const inputVariants = {
  default: 'input',
  narrow: 'input input-narrow',
} as const;

export type InputVariant = keyof typeof inputVariants;
