<script lang="ts">
  import { models, type ModelId } from '../data/research';
  let { label, value, onchange }: { label: string; value: ModelId; onchange: (id: ModelId) => void } = $props();
</script>

<label class="field">{label}<select class="select" aria-label={label} {value} onchange={(event) => onchange(event.currentTarget.value as ModelId)}>
  {#each models as model}<option value={model.id}>{model.name}</option>{/each}
</select></label>