/**
 * `cn` — the class merger shadcn-svelte components expect.
 *
 * This workspace uses Svelte 5 runes plus plain CSS custom properties, so the
 * components below follow shadcn's *conventions* (variants map, `cn()`, tokens,
 * `$lib/components/ui/<name>/` layout) rather than importing the upstream
 * registry, which targets `tailwind-variants` and `bits-ui`. Adding a primitive
 * here stays a local, reviewable change.
 */
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Pick the variant class from a variant record, falling back to `default`. */
export function variantOf<K extends string>(
  variants: Record<K, string>,
  variant: K | undefined,
  fallback: K,
): string {
  return variants[variant ?? fallback] ?? variants[fallback];
}
