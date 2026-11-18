<script lang="ts">
  import { untrack } from 'svelte';
  import { Crosshair, Layers, Map as MapIcon, Maximize, Minimize, Minus, Plus, RotateCcw } from '@lucide/svelte';
  import { applyAffine, assessGeoreferencing, datasetBounds as wgsBounds, cellWindow, toWgs84 } from '$lib/geo';
  import { renderClassOverlay, renderUncertaintyOverlay, classColors } from '$lib/palette';
  import { renderRaster } from '$lib/raster';
  import { getWorkspace, type Selection } from '$lib/state.svelte';
  import { useT } from '$lib/t.svelte';
  import type { DatasetView, LabelView, MapFieldView } from '$lib/types';

  let {
    dataset,
    hard,
    uncertainty,
    labels,
    onselect,
  }: {
    dataset: DatasetView;
    hard: MapFieldView | null;
    uncertainty: MapFieldView | null;
    labels: LabelView[];
    onselect: (feature: Selection) => void;
  } = $props();

  const workspace = getWorkspace();
  const { t, percent, number } = useT();

  let host: HTMLDivElement;
  let expanded = $state(false);
  let imagery = $state<string | null>(null);
  let imageryError = $state<string | null>(null);
  let imageryLoading = $state(false);
  let pointer = $state<{ x: number; y: number } | null>(null);

  // Leaflet is imported lazily so the map library stays out of the first paint.
  let runtime = $state.raw<null | {
    setImagery: (url: string | null) => void;
    setClass: (url: string | null) => void;
    setUncertainty: (url: string | null) => void;
    setLabels: (labels: LabelView[]) => void;
    refreshStyles: () => void;
    zoom: (direction: 1 | -1) => void;
    reset: () => void;
    dispose: () => void;
  }>(null);
  let mapFailed = $state(false);

  const geo = $derived(
    assessGeoreferencing({
      crsCode: dataset.crs,
      transform: dataset.transform,
      width: dataset.width,
      height: dataset.height,
    }),
  );

  const colors = $derived(classColors(hard?.classes ?? workspace.project?.classes ?? []));

  /** Raster preview: real bytes through the adapter, rendered in the browser. */
  $effect(() => {
    const d = dataset;
    const mode = workspace.map.bandMode;
    untrack(() => {
      imageryLoading = true;
      imageryError = null;
      renderRaster(d.url, d.id, mode)
        .then((url) => {
          imagery = url;
        })
        .catch((error) => {
          imagery = null;
          imageryError = error instanceof Error ? error.message : String(error);
        })
        .finally(() => {
          imageryLoading = false;
        });
    });
  });

  const classOverlay = $derived.by(() => {
    if (!hard || typeof document === 'undefined') return null;
    const palette = hard.classes.map((name, index) => colors[name] ?? Object.values(colors)[index] ?? '#4aa9ff');
    return renderClassOverlay(hard.values, hard.valid, palette);
  });

  const uncertaintyOverlay = $derived.by(() => {
    if (!uncertainty || typeof document === 'undefined') return null;
    return renderUncertaintyOverlay(uncertainty.values, uncertainty.valid, uncertainty.min, uncertainty.max);
  });

  $effect(() => {
    if (!host || runtime) return;
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
    runtime?.setClass(workspace.map.layers.classification ? classOverlay : null);
  });
  $effect(() => {
    runtime?.setUncertainty(workspace.map.layers.uncertainty ? uncertaintyOverlay : null);
  });
  $effect(() => {
    runtime?.setLabels(workspace.map.layers.samples ? labels : []);
  });
  $effect(() => {
    // Opacity and selection are style-only changes: no re-render of the images.
    void workspace.map.opacity;
    void workspace.map.selected;
    void workspace.map.layers.classification;
    void workspace.map.layers.uncertainty;
    runtime?.refreshStyles();
  });

  /**
   * Build the Leaflet map. Two coordinate systems are supported, and they are
   * never mixed: a WGS84 overlay when the dataset has a usable CRS (4326/3857,
   * north-up affine), pixel space with `CRS.Simple` otherwise.
   */
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
        ? L.map(host, {
            zoomControl: false,
            attributionControl: false,
            minZoom: 2,
            maxZoom: 19,
            worldCopyJump: true,
          })
        : L.map(host, {
            crs: L.CRS.Simple,
            zoomControl: false,
            attributionControl: false,
            zoomSnap: 0,
            zoomDelta: 0.5,
            wheelPxPerZoomLevel: 110,
          });

    const bounds =
      mode === 'map' && box
        ? L.latLngBounds([box[1], box[0]], [box[3], box[2]])
        : L.latLngBounds([0, 0], [dataset.height, dataset.width]);

    if (mode === 'map' && box) {
      map.fitBounds(bounds, { animate: false });
    } else {
      const cover = () =>
        Math.log2(
          Math.max(map.getSize().x / dataset.width, map.getSize().y / dataset.height) * 1.002,
        );
      map.setMaxBounds(bounds.pad(0.08));
      map.setView([dataset.height / 2, dataset.width / 2], cover());
    }

    const pane = (name: string, z: number, interactive = false) => {
      const created = map.createPane(name);
      created.style.zIndex = String(z);
      created.style.pointerEvents = interactive ? 'auto' : 'none';
      return name;
    };
    const imageryPane = pane('wbalc-imagery', 210);
    const classPane = pane('wbalc-class', 240);
    const uncertaintyPane = pane('wbalc-uncertainty', 250);
    const labelPane = pane('wbalc-labels', 280, true);

    let imageryLayer: import('leaflet').ImageOverlay | null = null;
    let classLayer: import('leaflet').ImageOverlay | null = null;
    let uncertaintyLayer: import('leaflet').ImageOverlay | null = null;
    const labelLayer = L.layerGroup().addTo(map);
    const cellLayer = L.layerGroup().addTo(map);

    function overlay(url: string, opacity: number, paneName: string) {
      return L.imageOverlay(url, bounds, {
        opacity,
        pane: paneName,
        interactive: false,
        className: 'wbalc-overlay',
      });
    }

    function setImagery(url: string | null) {
      if (imageryLayer) {
        map.removeLayer(imageryLayer);
        imageryLayer = null;
      }
      if (!url) return;
      imageryLayer = overlay(url, 1, imageryPane).addTo(map);
    }

    function setClass(url: string | null) {
      if (classLayer) {
        map.removeLayer(classLayer);
        classLayer = null;
      }
      if (!url) return;
      classLayer = overlay(url, 0.8, classPane).addTo(map);
      styleClass();
    }

    function setUncertainty(url: string | null) {
      if (uncertaintyLayer) {
        map.removeLayer(uncertaintyLayer);
        uncertaintyLayer = null;
      }
      if (!url) return;
      uncertaintyLayer = overlay(url, 0.72, uncertaintyPane).addTo(map);
      styleUncertainty();
    }

    function styleClass() {
      classLayer?.setOpacity(
        (workspace.map.opacity / 100) * (workspace.map.layers.classification ? 1 : 0),
      );
    }

    function styleUncertainty() {
      uncertaintyLayer?.setOpacity(
        (workspace.map.opacity / 100) * (workspace.map.layers.uncertainty ? 1 : 0),
      );
    }

    function refreshStyles() {
      styleClass();
      styleUncertainty();
      cellLayer.clearLayers();
      const selected = workspace.map.selected;
      if (selected?.kind !== 'cell') return;
      const field = workspace.map.layers.uncertainty ? uncertainty : hard;
      if (!field) return;
      const window = cellWindow(field.grid, selected.row, selected.col, dataset.width, dataset.height);
      const rect =
        mode === 'map'
          ? cellPolygon(field, window)
          : L.rectangle(
              [
                [window.y0, window.x0],
                [window.y1, window.x1],
              ],
              { color: '#ffe3a0', weight: 2, fill: false, interactive: false },
            );
      if (rect) cellLayer.addLayer(rect);
    }

    /** Cell outline in WGS84, when the dataset can be projected. */
    function cellPolygon(field: MapFieldView, window: { x0: number; y0: number; x1: number; y1: number }) {
      const t = dataset.transform;
      const ctx = {
        crsCode: dataset.crs,
        transform: t,
        width: dataset.width,
        height: dataset.height,
      };
      if (!t || dataset.georefReason !== null) return null;
      const corners: [number, number][] = [];
      for (const [col, row] of [
        [window.x0, window.y0],
        [window.x1, window.y0],
        [window.x1, window.y1],
        [window.x0, window.y1],
      ]) {
        // Corners of the cell in the dataset CRS, then to WGS84 for the basemap.
        const [mx, my] = applyAffine(t, col, row);
        const wgs = toWgs84(ctx, mx, my);
        if (!wgs) return null;
        corners.push([wgs[1], wgs[0]]);
      }
      void field;
      return L.polygon(corners, { color: '#ffe3a0', weight: 2, fill: false, interactive: false });
    }

    /** Sample markers: real label anchors, clickable and keyboard reachable. */
    let labelSignature = '';
    function setLabels(items: LabelView[]) {
      const signature = items.map((item) => `${item.sampleId}:${item.className}`).join('|');
      if (signature === labelSignature) return;
      labelSignature = signature;
      labelLayer.clearLayers();
      for (const item of items) {
        if (!item.center) continue;
        const [lon, lat] = item.center;
        const position: [number, number] =
          mode === 'map' ? [lat, lon] : [dataset.height - lat, lon];
        const color = colors[item.className] ?? '#f3be67';
        const marker = L.marker(position, {
          pane: labelPane,
          keyboard: true,
          riseOnHover: true,
          icon: L.divIcon({
            className: 'wbalc-sample-pin',
            html: `<span style="--pin:${color}"></span>`,
            iconSize: [16, 16],
            iconAnchor: [8, 8],
          }),
          title: `${item.sampleId} · ${item.className}`,
          alt: `${item.sampleId}, ${item.className}`,
        });
        marker.on('click', () => onselect({ kind: 'sample', sampleId: item.sampleId }));
        labelLayer.addLayer(marker);
      }
    }

    const onMove = (event: import('leaflet').LeafletMouseEvent) => {
      if (mode === 'map') {
        pointer = { x: event.latlng.lng, y: event.latlng.lat };
      } else {
        pointer = { x: Math.round(event.latlng.lng), y: Math.round(dataset.height - event.latlng.lat) };
      }
    };
    map.on('mousemove', onMove);

    const resize = new ResizeObserver(() => {
      if (!host.clientWidth) return;
      map.invalidateSize({ animate: false });
    });
    resize.observe(host);

    return {
      setImagery,
      setClass,
      setUncertainty,
      setLabels,
      refreshStyles,
      zoom: (direction: 1 | -1) => map.setZoom(map.getZoom() + direction * 0.6),
      reset: () => {
        if (mode === 'map' && box) map.fitBounds(bounds, { animate: true });
        else map.setView([dataset.height / 2, dataset.width / 2], map.getZoom(), { animate: true });
      },
      dispose: () => {
        resize.disconnect();
        map.off('mousemove', onMove).remove();
      },
    };
  }
</script>

<svelte:window
  onkeydown={(event) => {
    if (event.key === 'Escape') expanded = false;
  }}
/>

{#if expanded}<div class="map-dimmer" aria-hidden="true"></div>{/if}
<section class="map-shell surface" class:expanded aria-label={t('map.title')}>
  <div class="map-bar">
    <div class="map-title"><MapIcon size={16} strokeWidth={1.75} /><h2>{t('map.title')}</h2></div>
    <span class="map-bar-divider"></span>
    <span class="badge-muted">{geo.mode === 'map' ? t('map.mapSpace') : t('map.pixelSpace')}</span>
    <span class="badge-live">{dataset.name}</span>
    <div class="map-bar-actions">
      <div class="segments" role="group" aria-label={t('map.bandMode')}>
        {#each [['true-color', t('map.band.trueColor')], ['false-color', t('map.band.falseColor')], ['ndvi', t('map.band.ndvi')]] as [value, label]}
          <button
            aria-pressed={workspace.map.bandMode === value}
            class:chosen={workspace.map.bandMode === value}
            onclick={() => {
              workspace.map.bandMode = value as 'true-color' | 'false-color' | 'ndvi';
            }}>{label}</button>
        {/each}
      </div>
      <button
        class="icon-button"
        title={expanded ? t('map.collapse') : t('map.expand')}
        aria-label={expanded ? t('map.collapse') : t('map.expand')}
        onclick={() => {
          expanded = !expanded;
        }}>{#if expanded}<Minimize size={16} />{:else}<Maximize size={16} />{/if}</button
      >
    </div>
  </div>

  <div class="map-canvas-wrap">
    <div class="map-canvas" bind:this={host}></div>

    <div class="map-controls">
      <button class="icon-button" aria-label={t('map.zoomIn')} title={t('map.zoomIn')} onclick={() => runtime?.zoom(1)}><Plus size={16} /></button>
      <button class="icon-button" aria-label={t('map.zoomOut')} title={t('map.zoomOut')} onclick={() => runtime?.zoom(-1)}><Minus size={16} /></button>
      <button class="icon-button" aria-label={t('map.resetView')} title={t('map.resetView')} onclick={() => runtime?.reset()}><RotateCcw size={15} /></button>
    </div>

    {#if imageryLoading && !imagery}
      <div class="map-notice"><span class="spinner"></span>{t('common.loading')}</div>
    {:else if imageryError}
      <div class="map-notice error"><strong>{t('map.rasterFailed')}</strong><span>{imageryError}</span></div>
    {:else if mapFailed}
      <div class="map-notice error"><span>{t('map.rasterFailed')}</span></div>
    {/if}

    {#if pointer}
      <div class="map-readout mono ltr-numeric">
        {#if geo.mode === 'map'}
          {number(pointer.y, 5)}°, {number(pointer.x, 5)}°
        {:else}
          x {pointer.x} · y {pointer.y}
        {/if}
      </div>
    {/if}

    <div class="map-legend">
      {#if workspace.map.layers.classification && hard}
        <span class="section-label"><Layers size={12} /> {t('map.layer.classification')}</span>
        <div class="chip-row">
          {#each hard.classes as name}
            <span class="chip" style:--chip-color={colors[name]}><i></i>{name}</span>
          {/each}
        </div>
      {:else if workspace.map.layers.uncertainty && uncertainty}
        <span class="section-label"><Crosshair size={12} /> {t('map.layer.uncertainty')}</span>
        <div class="legend-ramp">
          <span class="mono ltr-numeric">{percent(uncertainty.min)}</span>
          <i class="ramp-bar"></i>
          <span class="mono ltr-numeric">{percent(uncertainty.max)}</span>
        </div>
      {/if}
      {#if hard && hard.stale}
        <p class="legend-note">{t('map.stale')}</p>
      {/if}
    </div>
  </div>
</section>

<style>
  .map-shell { overflow: hidden; display: flex; flex-direction: column; }
  .map-shell.expanded { position: fixed; inset: 14px; z-index: 400; margin: 0; }
  .map-dimmer { position: fixed; inset: 0; background: #040a12d9; z-index: 390; }
  .map-bar { display: flex; align-items: center; gap: 9px; padding: 8px 11px; border-bottom: 1px solid var(--line); flex-wrap: wrap; min-height: 46px; }
  .map-title { display: flex; align-items: center; gap: 7px; color: #9ab1c9; }
  .map-title h2 { margin: 0; font-size: 13px; font-weight: 600; color: var(--ink); }
  .map-bar-divider { width: 1px; height: 17px; background: var(--border); }
  .map-bar-actions { display: flex; align-items: center; gap: 7px; margin-inline-start: auto; }
  .map-canvas-wrap { position: relative; flex: 1; min-height: 0; }
  .map-canvas { height: clamp(340px, 52vh, 620px); background: #0a1320; }
  .map-shell.expanded .map-canvas { height: calc(100vh - 120px); }
  .map-controls { position: absolute; inset-block-start: 11px; inset-inline-start: 11px; display: grid; gap: 4px; z-index: 5; }
  .map-controls .icon-button { background: #0e1a29e6; border: 1px solid #3d5568; width: 29px; height: 29px; }
  .map-notice { position: absolute; inset-block-start: 11px; inset-inline-end: 11px; display: flex; align-items: center; gap: 7px; padding: 6px 9px; border-radius: 5px; background: #0e1a29ec; border: 1px solid #3d5568; font-size: 11px; color: var(--muted); z-index: 6; max-width: 60%; }
  .map-notice.error { border-color: #7a4a3a; color: #f4d3c4; flex-direction: column; align-items: flex-start; }
  .map-readout { position: absolute; inset-block-end: 11px; inset-inline-end: 11px; padding: 3px 7px; border-radius: 4px; background: #0b1522df; border: 1px solid #35485a; color: #cfe0ee; font-size: 10.5px; z-index: 5; }
  .map-legend { position: absolute; inset-block-end: 11px; inset-inline-start: 11px; display: grid; gap: 5px; padding: 8px 10px; border-radius: 6px; background: #0b1522e6; border: 1px solid #35485a; max-width: min(340px, 62%); z-index: 5; }
  .legend-ramp { display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--faint); }
  .ramp-bar { display: block; width: 110px; height: 6px; border-radius: 4px; background: linear-gradient(to right, #2c4a63, #3f7f86, #68b9a6, #c6c07a, #e39a5f); }
  .legend-note { margin: 0; font-size: 10px; color: var(--warn); }
  .spinner { width: 11px; height: 11px; border-radius: 50%; border: 2px solid #3d5568; border-top-color: var(--accent); animation: spin 700ms linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 700px) {
    .map-bar { gap: 6px; }
    .map-bar-divider, .badge-live { display: none; }
    .map-legend { max-width: calc(100% - 22px); }
  }
  /* Scoped to the Leaflet panes this component creates. */
  :global(.wbalc-overlay) { image-rendering: pixelated; }
  :global(.wbalc-sample-pin span) {
    display: block;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--pin, #f3be67);
    border: 2px solid #04202b;
    box-shadow: 0 0 0 2px #ffffff26;
  }
  :global(.wbalc-sample-pin:focus-visible span) { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
