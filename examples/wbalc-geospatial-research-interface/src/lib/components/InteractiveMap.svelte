<script lang="ts">
  import { onMount } from 'svelte';
  import type * as Leaflet from 'leaflet';
  import 'leaflet/dist/leaflet.css';
  import { Crosshair, LocateFixed, Map as MapIcon, Maximize, Minimize, Minus, Plus } from '@lucide/svelte';
  import type { Basemap, ResearchState, Selection } from '../state.svelte';
  import { classes, samples, sensorDetails, type Model, type Observation, type Reviews, type XY } from '../data/research';
  import { boundary, mockReedOutlines, mockWaterOutline, placeLabels, sceneHeight, sceneImage, sceneMetersPerUnit, sceneToLonLat, sceneWidth, terrainImage } from '../data/scene';

  let { settings, observation, model, reviews, onselect, onbasemap }: {
    settings: ResearchState['map']; observation: Observation; model: Model; reviews: Reviews;
    onselect: (feature: Selection) => void; onbasemap: (basemap: Basemap) => void;
  } = $props();

  let surface: HTMLDivElement;
  let runtime = $state.raw<ReturnType<typeof setup> | null>(null);
  let scale = $state({ width: 60, label: '1 km' });
  let coordinate = $state<XY>(sceneToLonLat([sceneWidth / 2, sceneHeight / 2]));
  let expanded = $state(false);
  let failed = $state(false);

  onMount(() => {
    let active = true;
    import('leaflet').then(module => {
      if (active) runtime = setup(module.default ?? module, surface);
    }).catch(() => { if (active) failed = true; });
    return () => { active = false; runtime?.dispose(); };
  });

  $effect(() => { runtime?.refresh(settings, observation, model, reviews); });

  function setup(L: typeof Leaflet, element: HTMLDivElement) {
    const local = ([x, y]: XY): Leaflet.LatLngTuple => [sceneHeight - y, x];
    const bounds = L.latLngBounds(local([0, sceneHeight]), local([sceneWidth, 0]));
    const map = L.map(element, {
      crs: L.CRS.Simple, zoomControl: false, attributionControl: false,
      zoomAnimation: false, trackResize: false, inertia: false,
      zoomSnap: 0, zoomDelta: .56, maxBounds: bounds.pad(.07), maxBoundsViscosity: .88, wheelPxPerZoomLevel: 112,
    });
    let disposed = false;
    const home = local([sceneWidth / 2, sceneHeight / 2 - 2]);
    const coverZoom = () => Math.log2(Math.max(map.getSize().x / sceneWidth, map.getSize().y / sceneHeight) * 1.003);
    let homeZoom = coverZoom();
    map.setMinZoom(homeZoom - .24).setMaxZoom(homeZoom + 3.3).setView(home, homeZoom);

    L.imageOverlay(terrainImage, bounds, { pane: 'tilePane', alt: 'Schematic terrain basemap', className: 'terrain-overlay' }).addTo(map);
    const photo = L.imageOverlay(sceneImage, bounds, { pane: 'tilePane', alt: 'Locally generated satellite-style illustration', className: 'photo-overlay' });
    const outlines = L.layerGroup();
    const markers = L.layerGroup();
    const boundaryShape = L.polygon(boundary.map(local), { color: '#89e4de', weight: 1.4, opacity: .94, dashArray: '7 5', fill: false, smoothFactor: .5 });
    boundaryShape.on('click', () => onselect({ kind: 'boundary' })).on('add', () => makeSelectable(boundaryShape, 'Select study area boundary', { kind: 'boundary' }));

    let water: Leaflet.Polygon;
    let reeds: Leaflet.Polygon[] = [];
    let drawn = '';

    function makeSelectable(path: Leaflet.Polygon, label: string, selection: Selection) {
      const node = path.getElement();
      if (!node) return;
      node.setAttribute('role', 'button');
      node.setAttribute('aria-label', label);
      node.setAttribute('tabindex', '0');
      node.addEventListener('keydown', (event) => {
        const key = (event as KeyboardEvent).key;
        if (key === 'Enter' || key === ' ') { event.preventDefault(); event.stopPropagation(); onselect(selection); }
      });
    }

    function draw(item: Observation, activeModel: Model) {
      const key = `${item.date}/${activeModel.id}`;
      if (drawn === key) return;
      drawn = key;
      outlines.clearLayers();
      water = L.polygon(mockWaterOutline(item, activeModel).map(local), { color: '#73cafe', fillColor: '#298fee', smoothFactor: .6, className: 'area-shape water-shape' });
      water.on('click', () => onselect({ kind: 'water' })).on('add', () => makeSelectable(water, 'Select Open Water classification', { kind: 'water' }));
      outlines.addLayer(water);
      reeds = mockReedOutlines(item, activeModel).map((points, index) => {
        const shape = L.polygon(points.map(local), { color: classes.vegetation.line, fillColor: '#68d383', smoothFactor: .55, className: 'area-shape reed-shape' });
        shape.on('click', () => onselect({ kind: 'vegetation' }));
        if (index === 1) shape.on('add', () => makeSelectable(shape, 'Select Aquatic Vegetation classification', { kind: 'vegetation' }));
        outlines.addLayer(shape);
        return shape;
      });
    }

    const sampleMarkers = samples.map(sample => {
      const marker = L.marker(local(sample.point), {
        icon: L.divIcon({ className: 'reference-pin', html: '<span></span>', iconSize: [18, 18], iconAnchor: [9, 9] }),
        title: sample.id, keyboard: true, riseOnHover: true,
      });
      marker.bindTooltip(`${sample.id} / ${sample.location}`, { direction: 'top', offset: [0, -9], className: 'sample-tooltip' });
      marker.on('click', () => onselect({ kind: 'sample', id: sample.id }));
      markers.addLayer(marker);
      return { marker, sample };
    });

    placeLabels.forEach(label => {
      L.marker(local(label.point), {
        keyboard: false, interactive: false,
        icon: L.divIcon({ className: `cartographic-label ${label.tone}`, html: `<span>${label.text}</span>`, iconSize: [0, 0] }),
        zIndexOffset: -1100,
      }).addTo(map);
    });

    function show(layer: Leaflet.Layer, enabled: boolean) {
      if (enabled && !map.hasLayer(layer)) layer.addTo(map);
      else if (!enabled && map.hasLayer(layer)) map.removeLayer(layer);
    }

    function refresh(style: ResearchState['map'], item: Observation, activeModel: Model, labels: Reviews) {
      const opacity = style.opacity / 100;
      show(photo, style.layers.imagery && style.basemap === 'satellite');
      photo.getElement()?.classList.toggle('sar-overlay', item.sensor === 'Sentinel-1');
      draw(item, activeModel);
      show(outlines, style.layers.classification && opacity > 0);
      const focusedWater = style.selected?.kind === 'water';
      const focusedReeds = style.selected?.kind === 'vegetation';
      water.setStyle({ weight: focusedWater ? 1.65 : 1.2, opacity: opacity * (focusedWater ? 1 : .8), fillOpacity: opacity * .85 });
      reeds.forEach(shape => shape.setStyle({ weight: focusedReeds ? 1.8 : 1.1, opacity: opacity, fillOpacity: opacity * .78 }));
      show(boundaryShape, style.layers.boundary);
      boundaryShape.setStyle({ weight: style.selected?.kind === 'boundary' ? 2.4 : 1.4 });
      show(markers, style.layers.samples);
      sampleMarkers.forEach(({ marker, sample }) => {
        const node = marker.getElement();
        const reviewed = Boolean(labels[sample.id]);
        node?.classList.toggle('is-reviewed', reviewed);
        node?.classList.toggle('is-selected', style.selected?.kind === 'sample' && style.selected.id === sample.id);
        node?.setAttribute('aria-label', `Select sample ${sample.id}${reviewed ? ', reviewed' : ', pending'}`);
      });
    }

    function updateScale() {
      const metersPerPixel = sceneMetersPerUnit / map.options.crs!.scale(map.getZoom());
      const meters = [25, 50, 100, 250, 500, 1000, 1500, 2000, 3000, 5000].filter(item => item / metersPerPixel <= 93).pop() ?? 25;
      scale = { width: meters / metersPerPixel, label: meters < 1000 ? `${meters} m` : `${meters / 1000} km` };
    }

    function updateCoordinate(point?: Leaflet.LatLng) {
      if (disposed) return;
      point ??= map.getCenter();
      coordinate = sceneToLonLat([point.lng, sceneHeight - point.lat]);
    }

    const updatePointer = (event: Leaflet.LeafletMouseEvent) => updateCoordinate(event.latlng);
    const updateCenter = () => updateCoordinate();
    map.on('mousemove', updatePointer);
    map.on('moveend', updateCenter);
    map.on('zoomend', updateScale);
    element.addEventListener('mouseleave', updateCenter);
    updateScale();
    updateCoordinate();

    const resize = new ResizeObserver(() => {
      if (disposed || !element.clientWidth || !element.clientHeight) return;
      const offset = map.getZoom() - homeZoom;
      const center = map.getCenter();
      map.invalidateSize({ animate: false });
      const next = coverZoom();
      if (Math.abs(next - homeZoom) > .004) {
        homeZoom = next;
        map.setMinZoom(homeZoom - .24).setMaxZoom(homeZoom + 3.3);
        map.setView(center, homeZoom + offset, { animate: false });
      }
      updateScale();
    });
    resize.observe(element);

    const animate = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    return {
      refresh,
      zoom: (direction: 1 | -1) => map.setZoom(map.getZoom() + direction * .56),
      reset: () => map.setView(home, homeZoom, { animate }),
      dispose: () => {
        disposed = true;
        resize.disconnect();
        element.removeEventListener('mouseleave', updateCenter);
        map.off('mousemove', updatePointer).off('moveend', updateCenter).off('zoomend', updateScale).remove();
      },
    };
  }
</script>

<svelte:window onkeydown={(event) => { if (event.key === 'Escape') expanded = false; }} />

{#if expanded}<div class="map-dimmer" aria-hidden="true"></div>{/if}
<section class="map-shell surface" class:expanded aria-label="Classification map workspace">
  <div class="map-bar">
    <div class="map-title"><MapIcon size={16} strokeWidth={1.75} /><h2>Classification map</h2></div>
    <span class="map-bar-divider"></span>
    <span class="sensor-tag"><span></span>{sensorDetails[observation.sensor].product}</span>
    <div class="map-bar-actions">
      <select class="select basemap-select" aria-label="Basemap" value={settings.basemap} onchange={(event) => onbasemap(event.currentTarget.value as Basemap)}>
        <option value="satellite">Satellite</option>
        <option value="terrain">Terrain</option>
      </select>
      <button class="icon-button expand-button" aria-label={expanded ? 'Exit expanded map' : 'Expand map'} title={expanded ? 'Exit expanded map (Esc)' : 'Expand map'} onclick={() => { expanded = !expanded; }}>
        {#if expanded}<Minimize size={16} />{:else}<Maximize size={16} />{/if}
      </button>
    </div>
  </div>

  <div class="map-stage" class:map-loaded={!!runtime}>
    <div class="leaflet-surface" bind:this={surface} role="region" aria-label="Interactive simulated imagery map. Use arrow keys to pan or plus and minus to zoom."></div>
    {#if !runtime}<span class="map-loading">{failed ? 'Interactive map unavailable. Showing local illustration.' : 'Loading local map...'}</span>{/if}

    <div class="map-stamp"><span></span> SIMULATED IMAGERY</div>

    <div class="map-control-rail">
      <div class="north-arrow" aria-label="North is up" title="North is up"><span>N</span><svg width="15" height="18" viewBox="0 0 15 18" aria-hidden="true"><path d="M7.5 1.5 13 15l-5.5-3-5.5 3Z" fill="#e6edf2"/><path d="M7.5 1.5v10.5l5.5 3Z" fill="#8da9b3"/></svg></div>
      <div class="map-zoom">
        <button aria-label="Zoom in" title="Zoom in" disabled={!runtime} onclick={() => runtime?.zoom(1)}><Plus size={18} /></button>
        <button aria-label="Zoom out" title="Zoom out" disabled={!runtime} onclick={() => runtime?.zoom(-1)}><Minus size={18} /></button>
        <button aria-label="Reset map view" title="Reset map view" disabled={!runtime} onclick={() => runtime?.reset()}><LocateFixed size={16} /></button>
      </div>
    </div>

    <div class="map-legend" aria-label="Map legend">
      <h3>MAP LEGEND</h3>
      <div class:layer-muted={!settings.layers.classification}><span class="legend-swatch water"></span>Open Water</div>
      <div class:layer-muted={!settings.layers.classification}><span class="legend-swatch veg"></span>Aquatic Vegetation</div>
      <div class:layer-muted={!settings.layers.boundary}><span class="legend-swatch boundary"></span>Study area boundary</div>
      <div class:layer-muted={!settings.layers.samples}><span class="legend-swatch reference"></span>Reference sample</div>
    </div>
    <div class="scene-scale" aria-label={`Map scale ${scale.label}`} style:width={`${scale.width}px`}><span>{scale.label}</span><i></i></div>
  </div>

  <div class="map-status">
    <span class="map-coords"><Crosshair size={13} />{coordinate[1].toFixed(4)}&deg; N, {coordinate[0].toFixed(4)}&deg; E</span>
    <span class="status-divider"></span><span class="datum">WGS 84</span>
    <span class="map-local">Local basemap</span>
  </div>
</section>

<style>
  .map-shell { display: flex; flex-direction: column; height: clamp(484px, calc(100dvh - 246px), 850px); overflow: hidden; }
  .map-bar { min-height: 48px; padding: 0 11px 0 13px; display: flex; align-items: center; gap: 10px; flex: none; background: #121e2e; }
  .map-title { display: flex; gap: 8px; align-items: center; color: #aac0d9; white-space: nowrap; }
  .map-title h2 { font-size: 13px; font-weight: 640; letter-spacing: -.008em; color: var(--ink); margin: 0; }
  .map-bar-divider { flex: none; height: 17px; width: 1px; background: var(--border); margin-inline: 1px; }
  .sensor-tag { font: 10.5px var(--mono); color: #a0b6c8; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; }
  .sensor-tag span { width: 5px; height: 5px; background: var(--accent); border-radius: 50%; }
  .map-bar-actions { display: flex; align-items: center; gap: 7px; margin-left: auto; }
  .basemap-select { min-height: 30px; font-size: 11.5px; }
  .expand-button { border: 1px solid #304157; width: 30px; height: 30px; }
  .map-stage { flex: 1 1 auto; min-height: 0; position: relative; isolation: isolate; background: #23343c url('/maps/zarivar-satellite.jpg') center / cover no-repeat; border-top: 1px solid #314154; border-bottom: 1px solid #314154; }
  .map-stage.map-loaded { background-image: url('/maps/zarivar-terrain.svg'); }
  .leaflet-surface { position: absolute; inset: 0; background: transparent; cursor: grab; outline-offset: -3px; }
  .leaflet-surface:active { cursor: grabbing; }
  .leaflet-surface :global(.photo-overlay) { filter: saturate(1.02) brightness(.92); }
  .leaflet-surface :global(.photo-overlay.sar-overlay) { filter: grayscale(1) brightness(.87) contrast(1.36); }
  .leaflet-surface :global(.leaflet-interactive:focus-visible) { outline-offset: 4px; }
  .leaflet-surface :global(.area-shape) { transition: fill-opacity 110ms, stroke-opacity 110ms, stroke-width 110ms; }
  .leaflet-surface :global(.area-shape:hover) { filter: brightness(1.25); }
  .leaflet-surface :global(.cartographic-label > span) { position: absolute; transform: translate(-50%, -50%); font: 550 11px/1 Inter, sans-serif; color: #e5eceb; white-space: nowrap; text-shadow: 0 1px 3px #0a151a, 0 1px 4px #0a151a, 0 0 7px #0a151a; }
  .leaflet-surface :global(.cartographic-label.lake > span) { color: #e3f2ff; font-size: 14px; font-style: italic; font-weight: 540; letter-spacing: .025em; }
  .leaflet-surface :global(.cartographic-label.town > span) { color: #fff9e8; letter-spacing: .035em; font-size: 13px; }
  .leaflet-surface :global(.cartographic-label.terrain > span) { color: #d9e5d9; opacity: .85; text-transform: uppercase; font-size: 8.7px; letter-spacing: .13em; }
  .leaflet-surface :global(.reference-pin) { display: grid; place-items: center; }
  .leaflet-surface :global(.reference-pin span) { width: 9px; height: 9px; border: 1.6px solid #ffda78; border-radius: 2px; display: grid; place-items: center; background: #322e18; box-shadow: 0 0 0 1px #0e161c9c, 0 1px 5px #050a12c9; transition: transform 130ms, box-shadow 130ms; }
  .leaflet-surface :global(.reference-pin.is-reviewed span) { border-radius: 50%; background: #bd943e; width: 8px; height: 8px; border-color: #ffe4a4; }
  .leaflet-surface :global(.reference-pin:hover span), .leaflet-surface :global(.reference-pin.is-selected span) { transform: scale(1.28); box-shadow: 0 0 0 2.5px #ffd27855; }
  .leaflet-surface :global(.sample-tooltip) { background: #122134; border: 1px solid #567082; color: #edeee8; border-radius: 4px; font: 10px var(--mono); }
  .leaflet-surface :global(.sample-tooltip::before) { border-top-color: #567082; }
  .map-loading { position: absolute; left: 50%; top: 50%; z-index: 450; transform: translate(-50%, -50%); padding: 6px 8px; border-radius: 4px; background: #111d2be8; color: #e3edf0; font: 11px var(--mono); }
  .map-stamp, .map-legend, .map-control-rail, .scene-scale { position: absolute; z-index: 500; }
  .map-stamp { left: 12px; top: 12px; padding: 6px 7px; display: flex; gap: 6px; align-items: center; border: 1px solid #566c70; border-radius: 4px; color: #d2e3e5; font: 9px var(--mono); letter-spacing: .055em; background: #0c1924e8; pointer-events: none; }
  .map-stamp span { width: 5px; height: 5px; border-radius: 50%; background: #78e5cf; }
  .map-control-rail { top: 12px; right: 12px; display: grid; gap: 9px; }
  .north-arrow { border: 1px solid #5a7076; border-radius: 5px; background: #0d1821ed; display: grid; justify-items: center; align-content: center; min-height: 43px; gap: 1px; font: 10px/1 var(--mono); color: #d4e3e9; user-select: none; }
  .map-zoom { display: grid; background: #0d1824f2; border: 1px solid #526871; border-radius: 5px; overflow: hidden; }
  .map-zoom button { display: grid; place-items: center; width: 32px; height: 32px; color: #e6eff5; }
  .map-zoom button + button { border-top: 1px solid #40525b; }
  .map-zoom button:hover:not(:disabled) { background: #27414d; }
  .map-zoom button:focus-visible { outline-offset: -2px; }
  .map-legend { left: 12px; bottom: 12px; padding: 9px 11px 9px 10px; background: #0c1826ed; border: 1px solid #566a76; border-radius: 6px; box-shadow: 0 2px 9px #05101974; min-width: 153px; pointer-events: none; }
  .map-legend h3 { margin: 0 0 6px; font: 9px var(--mono); letter-spacing: .08em; color: #a3b9c9; }
  .map-legend div { display: flex; align-items: center; gap: 8px; min-height: 18px; color: #e3e9ef; white-space: nowrap; font-size: 10.5px; }
  .map-legend div.layer-muted { opacity: .4; }
  .legend-swatch { display: inline-block; flex: none; width: 10px; height: 9px; border-radius: 2px; }
  .legend-swatch.water { background: #3f9ef5; border: 1px solid #78c9fd; }
  .legend-swatch.veg { background: #62cb7d; border: 1px solid #9be49f; }
  .legend-swatch.boundary { height: 0; border-top: 1px dashed #9feee3; border-radius: 0; }
  .legend-swatch.reference { width: 8px; height: 8px; margin-inline: 1px; background: #352d18; border: 1px solid #ffd786; }
  .scene-scale { right: 15px; bottom: 14px; min-width: 41px; color: #fff; text-align: center; font: 10px/1.4 var(--mono); text-shadow: 0 1px 3px #05090b, 0 1px 4px #05090b; pointer-events: none; }
  .scene-scale i { display: block; height: 5px; border: 1.5px solid #e4edef; border-top: 0; box-shadow: 0 1px 3px #05090b; }
  .map-status { display: flex; align-items: center; flex: none; gap: 10px; min-height: 34px; padding-inline: 12px; color: #9caec4; font: 10px var(--mono); background: #111c2c; white-space: nowrap; }
  .map-coords { display: flex; align-items: center; gap: 6px; }
  .map-coords :global(svg) { color: #83a9bb; }
  .status-divider { width: 1px; height: 12px; background: var(--border); }
  .map-local { margin-left: auto; color: #95a8bc; }
  .map-dimmer { position: fixed; inset: 0; background: #060c14dd; z-index: 990; }
  .map-shell.expanded { position: fixed; inset: 14px; height: auto; z-index: 991; }
  :global(body:has(.map-shell.expanded)) { overflow: hidden; }
  @media (max-width: 1150px) { .map-bar { gap: 7px; } }
  @media (max-width: 600px) { .map-shell { height: max(435px, 61dvh); } .map-shell.expanded { height: auto; inset: 6px; } }
  @media (max-width: 460px) {
    .map-bar { padding-inline: 8px; gap: 6px; }
    .map-title { gap: 5px; }
    .map-title h2 { font-size: 11.5px; }
    .map-title :global(svg) { width: 14px; }
    .sensor-tag, .map-bar-divider { display: none; }
    .leaflet-surface :global(.cartographic-label.terrain > span) { display: none; }
    .map-control-rail { right: 8px; }
    .map-legend, .map-stamp { left: 8px; }
    .map-status { gap: 7px; font-size: 9px; padding-inline: 8px; }
  }
</style>