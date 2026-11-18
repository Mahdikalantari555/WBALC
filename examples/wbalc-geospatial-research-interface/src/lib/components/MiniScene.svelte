<script lang="ts">
  import { mockReedOutlines, mockWaterOutline, shapePoints, boundary, sceneImage, sceneWidth, sceneHeight } from '../data/scene';
  import { classes, latest, type ErrorSite, type Model, type Observation, type Sample } from '../data/research';

  const uid = $props.id();
  let { observation = latest, model, reference, sample, errors = [], highlight, mode = 'prediction', label = 'Simulated Zarivar Lake classification' }: {
    observation?: Observation; model?: Model; reference?: Observation; sample?: Sample; errors?: ErrorSite[];
    highlight?: string | null; mode?: 'prediction' | 'change' | 'errors' | 'raw'; label?: string;
  } = $props();

  const view = $derived(sample ? `${sample.point[0] - 220} ${sample.point[1] - 148} 440 296` : '0 0 1536 1024');
  const water = $derived(shapePoints(mockWaterOutline(observation, model)));
  const reeds = $derived(mockReedOutlines(observation, model).map(shapePoints));
  const previous = $derived(reference ? shapePoints(mockWaterOutline(reference, model)) : water);
</script>

<svg class="mini-scene" role="img" aria-label={label} viewBox={view} preserveAspectRatio="xMidYMid slice">
  <title>{label}</title>
  <rect width={sceneWidth} height={sceneHeight} fill="#21363d" />
  <image href={sceneImage} width={sceneWidth} height={sceneHeight} class:sar={observation.sensor === 'Sentinel-1'} />
  {#if mode !== 'raw'}
    <polygon points={shapePoints(boundary)} fill="none" stroke="#7be4d6" stroke-width="2.8" stroke-dasharray="12 9" opacity=".88" />
    <polygon points={water} fill="#298fee" stroke="#76ceff" stroke-width="2.8" fill-opacity={mode === 'change' || mode === 'errors' ? .37 : .69} />
    {#each reeds as reed}
      <polygon points={reed} fill={classes.vegetation.color} stroke={classes.vegetation.line} stroke-width="2" fill-opacity={mode === 'change' ? .26 : .7} />
    {/each}
  {/if}
  {#if mode === 'change' && reference}
    <defs>
      <mask id={`${uid}-old`} maskUnits="userSpaceOnUse" width={sceneWidth} height={sceneHeight}><rect width={sceneWidth} height={sceneHeight} fill="white"/><polygon points={previous} fill="black"/></mask>
      <mask id={`${uid}-new`} maskUnits="userSpaceOnUse" width={sceneWidth} height={sceneHeight}><rect width={sceneWidth} height={sceneHeight} fill="white"/><polygon points={water} fill="black"/></mask>
    </defs>
    <polygon points={water} fill="#5ff2b3" mask={`url(#${uid}-old)`} />
    <polygon points={previous} fill="#ffb465" mask={`url(#${uid}-new)`} />
  {/if}
  {#if mode === 'errors'}
    {#each errors as site}
      <circle cx={site.point[0]} cy={site.point[1]} r={site.id === highlight ? 22 : 12} fill="#362113" stroke={site.id === highlight ? '#fff4d8' : '#ffc478'} stroke-width={site.id === highlight ? 5 : 3.5} />
      <circle cx={site.point[0]} cy={site.point[1]} r="4" fill="#ffd79b" />
    {/each}
  {/if}
  {#if sample}
    {@const [x, y] = sample.point}
    <rect x={x - 38} y={y - 38} width="76" height="76" fill="#f2cb7e" fill-opacity=".09" stroke="#ffe3a0" stroke-width="1.8" stroke-dasharray="4 4" />
    <path d={`M${x - 26} ${y - 38}H${x - 38}V${y - 26} M${x + 26} ${y - 38}H${x + 38}V${y - 26} M${x - 38} ${y + 26}V${y + 38}H${x - 26} M${x + 38} ${y + 26}V${y + 38}H${x + 26} M${x - 7} ${y}h14 M${x} ${y - 7}v14`} stroke="#fff1ce" stroke-width="2" fill="none" />
  {/if}
</svg>

<style>
  .mini-scene { display: block; width: 100%; height: 100%; background: #22353d; }
  image { filter: brightness(.84) saturate(1.04); }
  image.sar { filter: grayscale(1) brightness(.82) contrast(1.42); }
</style>