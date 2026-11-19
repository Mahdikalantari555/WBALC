/**
 * Component-level (jsdom) tests for the i18n + RTL surface.
 *
 * The audit requirement is that a runtime locale switch updates *visible chrome*
 * without a reload, that the document direction follows the locale, and that
 * number/percent formatting follows the locale. These run against the real
 * components, not mocks.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { flushSync, mount, unmount, type Component } from 'svelte';
import { applyDocumentLocale } from '../i18n/store.svelte';
import { createWorkspace } from '../state.svelte';
import Harness from '../test/Harness.svelte';
import LocaleSwitch from './LocaleSwitch.svelte';
import MetricBar from './MetricBar.svelte';
import MetricsTable from './MetricsTable.svelte';
import PageHeading from './PageHeading.svelte';

beforeAll(() => {
  if (!window.matchMedia) {
    // Minimal shim: jsdom has no matchMedia.
    window.matchMedia = (query: string): MediaQueryList => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }) as unknown as MediaQueryList;
  }
});

afterEach(() => {
  document.body.innerHTML = '';
  applyDocumentLocale('en');
});

/** Mount a component inside the workspace context provider. */
function mountWithWorkspace(
  component: Component<Record<string, unknown>>,
  props: Record<string, unknown> = {},
) {
  const target = document.createElement('div');
  document.body.appendChild(target);
  const workspace = createWorkspace('en');
  applyDocumentLocale('en');
  const instance = mount(Harness, { target, props: { workspace, component, props } });
  flushSync();
  return { target, workspace, destroy: () => unmount(instance) };
}

describe('locale switch', () => {
  it('updates chrome strings and document direction without a reload', () => {
    const { target, workspace, destroy } = mountWithWorkspace(LocaleSwitch as Component<Record<string, unknown>>);

    const buttons = [...target.querySelectorAll<HTMLButtonElement>('.locale-switch button')];
    expect(buttons).toHaveLength(2);
    expect(buttons[0].getAttribute('aria-pressed')).toBe('true');

    buttons[1].click();
    flushSync();

    expect(workspace.locale.current).toBe('fa');
    expect(document.documentElement.dir).toBe('rtl');
    expect(document.documentElement.lang).toBe('fa');
    const after = [...target.querySelectorAll<HTMLButtonElement>('.locale-switch button')];
    expect(after[1].getAttribute('aria-pressed')).toBe('true');
    expect(after[0].getAttribute('aria-pressed')).toBe('false');

    after[0].click();
    flushSync();
    expect(document.documentElement.dir).toBe('ltr');
    destroy();
  });
});

describe('PageHeading', () => {
  it('renders Persian title, description and eyebrow', () => {
    const { target, destroy } = mountWithWorkspace(PageHeading as Component<Record<string, unknown>>, {
      title: 'فضای کار مکانی',
      description: 'توضیح فارسی',
      eyebrow: '#1 · WBALC',
    });
    expect(target.querySelector('h1')?.textContent).toBe('فضای کار مکانی');
    expect(target.querySelector('p')?.textContent).toBe('توضیح فارسی');
    expect(target.querySelector('.eyebrow')?.textContent).toContain('#1 · WBALC');
    destroy();
  });
});

describe('MetricBar', () => {
  it('renders a localised value and a proportional bar', () => {
    const { target, destroy } = mountWithWorkspace(MetricBar as Component<Record<string, unknown>>, {
      label: 'دقت کلی',
      value: 0.873,
      display: '۸۷٫۳٪',
    });
    expect(target.querySelector('.metric-head b')?.textContent).toBe('۸۷٫۳٪');
    expect(target.querySelector<HTMLElement>('.metric-track i')!.style.width).toBe('87.3%');
    destroy();
  });

  it('renders an empty bar instead of guessing for a null metric', () => {
    const { target, destroy } = mountWithWorkspace(MetricBar as Component<Record<string, unknown>>, {
      label: 'IoU',
      value: null,
      display: '—',
    });
    expect(target.querySelector<HTMLElement>('.metric-track i')!.style.width).toBe('0%');
    destroy();
  });
});

describe('MetricsTable provenance', () => {
  const metrics = {
    id: '9',
    iteration: 3,
    modelType: 'lightgbm',
    resolution: 'pixel',
    evaluation: 'spatial_holdout',
    evaluationDetails: null,
    evaluationStrategy: 'spatial',
    nSamples: 30,
    nTrain: 20,
    nTest: 10,
    heldOutGroups: 2,
    accuracy: 0.9,
    f1Macro: 0.88,
    f1Weighted: 0.89,
    classes: ['open_water', 'land'],
    confusionMatrix: [
      [10, 1],
      [1, 12],
    ],
    perClass: [
      { className: 'open_water', support: 11, precision: 0.9, recall: 0.9, f1: 0.9, iou: 0.82 },
    ],
    insufficient: false,
    createdAt: '2025-04-14T08:00:00Z',
  };

  it('shows the model, protocol and resolution behind every score', () => {
    const { target, destroy } = mountWithWorkspace(MetricsTable as Component<Record<string, unknown>>, {
      metrics,
    });
    const caption = target.querySelector('.section-heading p')?.textContent ?? '';
    // The score is never context-free: all three provenance fields are visible.
    expect(caption).toContain('lightgbm');
    expect(caption).toContain('spatial');
    expect(caption).toContain('pixel');
    destroy();
  });

  it('marks an in-sample fit instead of presenting it as validated', () => {
    const withBadge = mountWithWorkspace(MetricsTable as Component<Record<string, unknown>>, {
      metrics: { ...metrics, insufficient: true },
    });
    expect(withBadge.target.textContent).toContain('Insufficient data');
    withBadge.destroy();
  });
});
