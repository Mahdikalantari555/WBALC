<script lang="ts">
  /**
   * Active-learning context map: the sample's own dataset with its
   * classification field underneath, one pin per proposed sample, and a
   * distinct target marker that tracks the focused sample. The reviewer sees
   * the scene-wide classification first, then the map zooms to the target and
   * marks the exact pixel/cell a proposal refers to.
   */
  import { onMount } from 'svelte';
  import { Layers } from '@lucide/svelte';
  import {
    applyAffine,
    assessGeoreferencing,
    datasetBounds as wgsBounds,
    toWgs84,
  } from '$lib/geo';
  import { classColors, renderClassOverlay } from '$lib/palette';
  import { renderRaster } from '$lib/raster';
  import { api } from '$lib/client/api';
  import { useT } from '$lib/t.svelte';
  import type { DatasetView, MapFieldView, QuerySampleView } from '$lib/types';

  let {
    dataset,
    runId,
    samples,
    sample,
    onpick,
  }: {
    dataset: DatasetView;
    /** Latest training run id: a new run invalidates the cached field. */
    runId: string | null;
    samples: QuerySampleView[];
    sample: QuerySampleView | null;
    onpick: (sampleId: string) => void;
  } = $props();

  const { t, percent } = useT();

  const geo = $derived(
    assessGeoreferencing({
      crsCode: dataset.crs,
      transform: dataset.transform,
      width: dataset.width,
      height: dataset.height,
    }),
  );

  let imagery = $state<string | null>(null);
  let imageryFailed = $state(false);
  // One field per dataset+run for the session; failures are not cached.
  const fieldCache = new Map<string, MapFieldView | null>();
  let field = $state<MapFieldView | null>(null);
  let fieldFailed = $state(false);
  let fieldLoading = $state(false);

  $effect(() => {
    const source = dataset;
    let active = true;
    imagery = null;
    imageryFailed = false;
    renderRaster(source.url, source.id, 'true-color', 1200, source.bandNames)
      .then((url) => {
        if (active) imagery = url;
      })
      .catch(() => {
        if (active) imageryFailed = true;
      });
    return () => {
      active = false;
    };
  });

  // The classification field for this dataset (latest run). The field endpoint
  // infers per dataset, so any date can carry its own classification.
  $effect(() => {
    const source = dataset;
    const run = runId ?? 'none';
    let active = true;
    const cacheKey = `${source.id}:${run}`;
    const cached = fieldCache.get(cacheKey);
    if (cached !== undefined) {
      field = cached;
      fieldFailed = false;
      fieldLoading = false;
      return;
    }
    fieldLoading = true;
    fieldFailed = false;
    field = null;
    api
      .mapField(String(source.projectId), {
        layer: 'hard',
        method: 'entropy',
        datasetId: String(source.id),
        acceptUnverifiedSchema: false,
      })
      .then((result) => {
        if (!active) return;
        fieldCache.set(cacheKey, result);
        field = result;
      })
      .catch(() => {
        if (!active) return;
        // Band-schema mismatches and unclassified rasters stay muted: the
        // context map is orientation aid, not the primary product.
        fieldCache.set(cacheKey, null);
        fieldFailed = true;
      })
      .finally(() => {
        if (active) fieldLoading = false;
      });
    return () => {
      active = false;
    };
  });

  const colors = $derived(classColors(field?.classes ?? []));
  const classOverlay = $derived.by(() => {
    if (!field || typeof document === 'undefined') return null;
    const palette = field.classes.map((name, index) => colors[name] ?? Object.values(colors)[index] ?? 'var(--info)');
    return renderClassOverlay(field.values, field.valid, palette);
  });

  /** WGS84 [lat, lon] of a sample centre, or pixel-space fallback. */
  function targetLatLng(item: QuerySampleView): [number, number] | null {
    const box = wgsBounds({
      crsCode: dataset.crs,
      transform: dataset.transform,
      width: dataset.width,
      height: dataset.height,
    });
    if (geo.mode === 'map' && box && dataset.transform) {
      const centre = item.geo ?? null;
      if (!centre) return null;
      const wgs = toWgs84(
        { crsCode: dataset.crs, transform: dataset.transform, width: dataset.width, height: dataset.height },
        centre[0],
        centre[1],
      );
      return wgs ? [wgs[1], wgs[0]] : null;
    }
    // Pixel space: CRS.Simple y grows upward while raster rows grow downward.
    const [col, row] = item.center;
    return [dataset.height - row, col];
  }

  let host: HTMLDivElement;
  let runtime = $state.raw<null | {
    setImagery: (url: string | null) => void;
    setClass: (url: string | null) => void;
    setPins: (items: QuerySampleView[], focused: QuerySampleView | null) => void;
    focusTarget: (item: QuerySampleView | null) => void;
    dispose: () => void;
  }>(null);
  let mapFailed = $state(false);

  onMount(() => {
    let disposed = false;
    import('leaflet')
      .then((module) => {
        if (disposed) return;
        runtime = setup(module.default);
      })
      .catch(() => {
        if (!disposed) mapFailed = true;
      });
    return () => {
      disposed = true;
      runtime?.dispose();
      runtime = null;
    };
  });

  $effect(() => {
    runtime?.setImagery(imagery);
  });
  $effect(() => {
    runtime?.setClass(classOverlay);
  });
  $effect(() => {
    runtime?.setPins(samples, sample ?? null);
  });
  $effect(() => {
    runtime?.focusTarget(sample ?? null);
  });

  function setup(L: typeof import('leaflet')) {
    const mode = geo.mode;
    const box = wgsBounds({
      crsCode: dataset.crs,
      transform: dataset.transform,
      width: dataset.width,
      height: dataset.height,
    });

    const map =
      mode === 'map' && box
        ? L.map(host, { zoomControl: false, attributionControl: false, minZoom: 2, maxZoom: 19, worldCopyJump: true })
        : L.map(host, {
            crs: L.CRS.Simple,
            zoomControl: false,
            attributionControl: false,
            zoomSnap: 0,
            wheelPxPerZoomLevel: 110,
          });

    if (mode === 'map' && box) {
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
    }

    const bounds =
      mode === 'map' && box
        ? L.latLngBounds([box[1], box[0]], [box[3], box[2]])
        : L.latLngBounds([0, 0], [dataset.height, dataset.width]);

    if (mode === 'map' && box) {
      map.fitBounds(bounds, { animate: false });
    } else {
      const cover = () =>
        Math.log2(Math.max(map.getSize().x / dataset.width, map.getSize().y / dataset.height) * 1.002);
      map.setView([dataset.height / 2, dataset.width / 2], cover());
    }

    const pane = (name: string, z: number, interactive = false) => {
      const created = map.createPane(name);
      created.style.zIndex = String(z);
      created.style.pointerEvents = interactive ? 'auto' : 'none';
      return name;
    };
    const imageryPane = pane('alctx-imagery', 210);
    const classPane = pane('alctx-class', 240);
    const pinPane = pane('alctx-pins', 280, true);
    const targetPane = pane('alctx-target', 290, true);

    function overlay(url: string, opacity: number, paneName: string) {
      return L.imageOverlay(url, bounds, { opacity, pane: paneName, interactive: false, className: 'wbalc-overlay' });
    }
    let imageryLayer: import('leaflet').ImageOverlay | null = null;
    let classLayer: import('leaflet').ImageOverlay | null = null;

    const pinLayer = L.layerGroup().addTo(map);
    let targetMarker: import('leaflet').Marker | null = null;
    let targetRect: import('leaflet').Layer | null = null;
    let pinSignature = '';

    function setImagery(url: string | null) {
      if (imageryLayer) map.removeLayer(imageryLayer);
      imageryLayer = url ? overlay(url, 1, imageryPane).addTo(map) : null;
    }

    function setClass(url: string | null) {
      if (classLayer) map.removeLayer(classLayer);
      classLayer = url ? overlay(url, 0.55, classPane).addTo(map) : null;
    }

    /** The focused sample's exact pixel window, drawn in the active space. */
    function targetOutline(item: QuerySampleView): import('leaflet').Layer | null {
      const window = item.window;
      if (mode !== 'map' || !dataset.transform || dataset.georefReason !== null) {
        return L.rectangle(
          [
            [window.y0, window.x0],
            [window.y1, window.x1],
          ],
          { color: 'var(--warn)', weight: 2, fill: false, interactive: false, pane: targetPane },
        );
      }
      const ctx = { crsCode: dataset.crs, transform: dataset.transform, width: dataset.width, height: dataset.height };
      const corners: [number, number][] = [];
      for (const [col, row] of [
        [window.x0, window.y0],
        [window.x1, window.y0],
        [window.x1, window.y1],
        [window.x0, window.y1],
      ]) {
        const [mx, my] = applyAffine(dataset.transform, col, row);
        const wgs = toWgs84(ctx, mx, my);
        if (!wgs) return null;
        corners.push([wgs[1], wgs[0]]);
      }
      return L.polygon(corners, { color: 'var(--warn)', weight: 2, fill: false, interactive: false, pane: targetPane });
    }

    function setPins(items: QuerySampleView[], focused: QuerySampleView | null) {
      const signature = items.map((item) => item.sampleId).join('|') + `#${focused?.sampleId ?? ''}`;
      if (signature === pinSignature) return;
      pinSignature = signature;
      pinLayer.clearLayers();
      for (const item of items) {
        const position = targetLatLng(item);
        if (!position) continue;
        if (focused && item.sampleId === focused.sampleId) continue;
        const color = colors[item.prediction ?? ''] ?? 'var(--info)';
        pinLayer.addLayer(
          L.marker(position, {
            pane: pinPane,
            icon: L.divIcon({
              className: 'alctx-pin',
              html: `<span style="--pin:${color}"></span>`,
              iconSize: [12, 12],
              iconAnchor: [6, 6],
            }),
            title: `${item.sampleId} · ${item.prediction ?? '—'}`,
            alt: item.sampleId,
          }).on('click', () => onpick(item.sampleId)),
        );
      }
    }

    function focusTarget(item: QuerySampleView | null) {
      if (targetMarker) {
        map.removeLayer(targetMarker);
        targetMarker = null;
      }
      if (targetRect) {
        map.removeLayer(targetRect);
        targetRect = null;
      }
      if (!item) return;
      const position = targetLatLng(item);
      if (!position) return;
      targetMarker = L.marker(position, {
        pane: targetPane,
        keyboard: false,
        icon: L.divIcon({
          className: 'alctx-target',
          html: '<span></span>',
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        }),
        title: item.sampleId,
        alt: item.sampleId,
      }).addTo(map);
      targetRect = targetOutline(item);
      if (targetRect) map.addLayer(targetRect);
      // Overview first, then the zoom: the reviewer keeps their bearings while
      // the map closes in on the exact pixel the proposal refers to.
      if (mode === 'map') {
        map.flyTo(position, Math.max(map.getZoom(), 15), { duration: 0.8 });
      } else {
        const span = Math.max(item.window.x1 - item.window.x0, item.window.y1 - item.window.y0);
        const zoom = Math.log2(map.getSize().x / Math.max(span * 24, 48));
        map.flyTo(position, Math.max(map.getZoom(), zoom), { duration: 0.8 });
      }
    }

    const container = host;
    const resize = new ResizeObserver(() => {
      if (!container.isConnected || !container.clientWidth) return;
      map.invalidateSize({ animate: false });
    });
    resize.observe(container);

    return {
      setImagery,
      setClass,
      setPins,
      focusTarget,
      dispose: () => {
        resize.disconnect();
        map.remove();
      },
    };
  }
</script>

<section class="surface context-map" aria-label={t('learning.contextMap')}>
  <div class="context-bar">
    <Layers size={14} strokeWidth={1.75} />
    <h3>{t('learning.contextMap')}</h3>
    <span class="context-note">
      {#if sample}
        <span class="mono ltr-numeric">r{sample.row} · c{sample.col}</span>
        {#if sample.uncertainty != null}<span class="mono ltr-numeric">· {percent(sample.uncertainty)}</span>{/if}
      {/if}
    </span>
  </div>
  <div class="context-canvas" bind:this={host}></div>
  {#if imageryFailed || mapFailed}
    <div class="context-note-float error">{t('map.rasterFailed')}</div>
  {:else if fieldLoading}
    <div class="context-note-float">{t('common.loading')}</div>
  {:else if fieldFailed}
    <div class="context-note-float">{t('learning.contextUnavailable')}</div>
  {/if}
</section>

<style>
  .context-map { position: relative; overflow: hidden; display: flex; flex-direction: column; }
  .context-bar { display: flex; align-items: center; gap: 7px; padding: 8px 11px; border-bottom: 1px solid var(--line); color: var(--faint); }
  .context-bar h3 { margin: 0; font-size: 12px; font-weight: 600; color: var(--ink); }
  .context-note { margin-inline-start: auto; display: flex; gap: 8px; font-size: 10.5px; color: var(--muted); }
  .context-canvas { height: clamp(240px, 30vw, 360px); background: var(--plot-bg); isolation: isolate; }
  .context-note-float { inset-block-start: 42px; inset-inline-end: 10px; padding: 4px 8px; border-radius: 4px; background: #0b1522df; border: 1px solid var(--control-border); color: var(--muted); font-size: 10.5px; z-index: 6; }
  .context-note-float.error { color: var(--danger-fg); }
  :global(.alctx-pin span) {
    display: block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--pin, var(--info));
    border: 2px solid var(--plot-bg);
    box-shadow: 0 0 0 1px #ffffff40;
    cursor: pointer;
  }
  /* The target: a ring + centre dot, unmistakable among the proposal pins. */
  :global(.alctx-target span) {
    display: block;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    border: 3px solid var(--warn);
    background: color-mix(in srgb, var(--warn) 22%, transparent);
    box-shadow: 0 0 0 2px #ffffff55, 0 0 12px var(--warn);
  }
  :global(.alctx-target span)::after {
    content: '';
    position: absolute;
    inset: 50%;
    width: 4px;
    height: 4px;
    margin: -2px;
    border-radius: 50%;
    background: var(--ink);
  }
</style>
