'use client';

import { useState } from 'react';
import { Satellite, Trash2, UploadCloud } from 'lucide-react';
import { useDeleteScene, useScenes, useUploadScene } from '@/hooks/use-projects';
import { errorMessage, formatBytes } from '@/lib/utils';
import type { Project, SceneMetadata, SatelliteSensor } from '@/types';
import { Button } from './ui/button';
import { EmptyState, ErrorState, Skeleton } from './ui/common';

function resolution(scene: SceneMetadata): string {
  if (scene.resolutionX == null || scene.resolutionY == null) return 'Unknown';
  const unit = scene.crs?.includes('4326') ? '°' : 'CRS units';
  return `${scene.resolutionX.toLocaleString()} × ${scene.resolutionY.toLocaleString()} ${unit}`;
}

function acquisitionDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : 'Acquisition date unknown';
}

export function SceneCollection({ project }: { project: Project }) {
  const { data: scenes = [], isLoading, error, refetch } = useScenes(project.id);
  const upload = useUploadScene(project.id);
  const remove = useDeleteScene(project.id);
  const [file, setFile] = useState<File | null>(null);
  const [sensor, setSensor] = useState<SatelliteSensor>('Sentinel-2');
  const [date, setDate] = useState('');
  const [platform, setPlatform] = useState('');
  const [productType, setProductType] = useState('');
  const [productLevel, setProductLevel] = useState('');
  const [polarization, setPolarization] = useState('');
  const [mode, setMode] = useState('');
  const [orbit, setOrbit] = useState<'ascending' | 'descending' | ''>('');
  const [relativeOrbit, setRelativeOrbit] = useState('');
  const [baseline, setBaseline] = useState('');
  const [bandResolutions, setBandResolutions] = useState('');
  const [validationError, setValidationError] = useState('');

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setValidationError('');
    if (!file) return setValidationError('Choose a GeoTIFF scene to upload.');
    if (!/\.tiff?$/i.test(file.name)) return setValidationError('Select a .tif or .tiff GeoTIFF file.');
    if (file.size > 512 * 1024 * 1024) return setValidationError('The file exceeds the 512 MB upload limit.');
    if (sensor === 'Sentinel-1' && polarization && !/^(VV|VH|HH|HV)(,(VV|VH|HH|HV))*$/i.test(polarization.replaceAll(' ', '')))
      return setValidationError('Polarization must be a comma-separated combination of VV, VH, HH, and HV.');

    let resolutionJson: string | undefined;
    if (sensor === 'Sentinel-2' && bandResolutions.trim()) {
      try {
        const entries = bandResolutions.split(',').map((part) => {
          const [name, value] = part.split('=').map((item) => item.trim());
          const parsed = Number(value);
          if (!name || !Number.isFinite(parsed) || parsed <= 0) throw new Error();
          return [name, parsed] as const;
        });
        resolutionJson = JSON.stringify(Object.fromEntries(entries));
      } catch {
        return setValidationError('Band resolutions must look like B02=10,B11=20 with positive values.');
      }
    }

    try {
      await upload.mutateAsync({
        file,
        metadata: {
          sensor,
          ...(date ? { acquisitionDateTime: new Date(date).toISOString() } : {}),
          ...(platform.trim() ? { platform: platform.trim() } : {}),
          ...(productType.trim() ? { productType: productType.trim() } : {}),
          ...(productLevel.trim() ? { productLevel: productLevel.trim() } : {}),
          ...(sensor === 'Sentinel-1' && polarization.trim() ? { polarization: polarization.replaceAll(' ', '') } : {}),
          ...(sensor === 'Sentinel-1' && mode.trim() ? { acquisitionMode: mode.trim() } : {}),
          ...(sensor === 'Sentinel-1' && orbit ? { orbitDirection: orbit } : {}),
          ...(sensor === 'Sentinel-1' && relativeOrbit ? { relativeOrbit } : {}),
          ...(sensor === 'Sentinel-2' && baseline.trim() ? { processingBaseline: baseline.trim() } : {}),
          ...(resolutionJson ? { nativeBandResolutions: resolutionJson } : {}),
        },
      });
      setFile(null);
      setDate('');
      setPlatform('');
      setProductType('');
      setProductLevel('');
      setPolarization('');
      setMode('');
      setOrbit('');
      setRelativeOrbit('');
      setBaseline('');
      setBandResolutions('');
      const input = document.getElementById(`scene-file-${project.id}`) as HTMLInputElement | null;
      if (input) input.value = '';
    } catch (cause) {
      setValidationError(errorMessage(cause));
    }
  };

  const deleteScene = async (scene: SceneMetadata) => {
    if (!window.confirm(`Delete ${scene.sourceFilename}? Other scenes and this project will be kept.`)) return;
    try {
      await remove.mutateAsync(scene.id);
    } catch (cause) {
      setValidationError(errorMessage(cause));
    }
  };

  return (
    <section className="scene-foundation" aria-labelledby="scene-foundation-title">
      <div className="scene-heading">
        <div>
          <div className="eyebrow"><span />MULTI-TEMPORAL DATA</div>
          <h2 id="scene-foundation-title">Scene collection</h2>
          <p>Register independent Sentinel acquisitions. Native source grids are preserved; scenes are not aligned automatically.</p>
        </div>
        <span className="scene-count"><Satellite size={15} />{scenes.length} scenes</span>
      </div>

      <form className="scene-upload-form" onSubmit={submit}>
        <div className="scene-upload-grid">
          <label className="field-label">GeoTIFF scene
            <input id={`scene-file-${project.id}`} className="input" type="file" accept=".tif,.tiff,image/tiff" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <label className="field-label">Sensor
            <select className="input" value={sensor} onChange={(event) => setSensor(event.target.value as SatelliteSensor)}>
              <option value="Sentinel-1">Sentinel-1 (SAR)</option>
              <option value="Sentinel-2">Sentinel-2 (multispectral)</option>
            </select>
          </label>
          <label className="field-label">Acquisition date &amp; time <span className="optional">Optional</span>
            <input className="input" type="datetime-local" value={date} onChange={(event) => setDate(event.target.value)} />
          </label>
          <label className="field-label">Platform <span className="optional">Optional</span>
            <input className="input" placeholder="e.g. Sentinel-2A" value={platform} onChange={(event) => setPlatform(event.target.value)} />
          </label>
          <label className="field-label">Product type <span className="optional">Optional</span>
            <input className="input" placeholder={sensor === 'Sentinel-1' ? 'e.g. GRD' : 'e.g. S2MSI2A'} value={productType} onChange={(event) => setProductType(event.target.value)} />
          </label>
          <label className="field-label">Product level <span className="optional">Optional</span>
            <input className="input" placeholder={sensor === 'Sentinel-2' ? 'e.g. L2A' : 'e.g. Level-1'} value={productLevel} onChange={(event) => setProductLevel(event.target.value)} />
          </label>
          {sensor === 'Sentinel-1' ? <>
            <label className="field-label">Polarization <span className="optional">Optional</span>
              <input className="input" placeholder="VV,VH" value={polarization} onChange={(event) => setPolarization(event.target.value)} />
            </label>
            <label className="field-label">Acquisition mode <span className="optional">Optional</span>
              <input className="input" placeholder="IW" value={mode} onChange={(event) => setMode(event.target.value)} />
            </label>
            <label className="field-label">Orbit direction <span className="optional">Optional</span>
              <select className="input" value={orbit} onChange={(event) => setOrbit(event.target.value as typeof orbit)}>
                <option value="">Not specified</option><option value="ascending">Ascending</option><option value="descending">Descending</option>
              </select>
            </label>
            <label className="field-label">Relative orbit <span className="optional">Optional</span>
              <input className="input" type="number" min="1" max="999" value={relativeOrbit} onChange={(event) => setRelativeOrbit(event.target.value)} />
            </label>
          </> : <>
            <label className="field-label">Processing baseline <span className="optional">Optional</span>
              <input className="input" placeholder="e.g. 05.10" value={baseline} onChange={(event) => setBaseline(event.target.value)} />
            </label>
            <label className="field-label">Native band resolutions <span className="optional">Optional</span>
              <input className="input" placeholder="B02=10,B11=20" value={bandResolutions} onChange={(event) => setBandResolutions(event.target.value)} />
            </label>
          </>}
        </div>
        {validationError && <p className="scene-error" role="alert">{validationError}</p>}
        <div className="scene-form-footer">
          <span>GeoTIFF only · source raster is stored unchanged · date may be left unknown</span>
          <Button type="submit" disabled={upload.isPending}><UploadCloud size={16} />{upload.isPending ? 'Registering…' : 'Upload scene'}</Button>
        </div>
      </form>

      {isLoading ? <div className="scene-loading"><Skeleton /><Skeleton /></div> : error ?
        <ErrorState message={error.message} onRetry={() => void refetch()} /> : scenes.length === 0 ?
          <EmptyState title="No scenes registered yet" description="Upload a preprocessed Sentinel-1 or Sentinel-2 GeoTIFF to start this study's scene collection." /> :
          <div className="scene-list" role="list" aria-label="Project scenes, ordered by acquisition time">
            {scenes.map((scene) => <article className="scene-row" role="listitem" key={scene.id}>
              <div className="scene-primary">
                <div className="scene-title-line"><strong>{scene.sourceFilename}</strong><span className="scene-sensor">{scene.sensor}</span></div>
                <time dateTime={scene.acquisitionDateTime ?? undefined}>{acquisitionDate(scene.acquisitionDateTime)}</time>
                <small>{scene.platform ?? 'Platform not specified'}{scene.productLevel ? ` · ${scene.productLevel}` : ''}</small>
              </div>
              <div className="scene-metadata">
                <span><b>{scene.bandCount}</b> bands</span>
                <span>{scene.crs ?? 'CRS unavailable'}</span>
                <span>{resolution(scene)}</span>
                <span>{scene.width} × {scene.height}</span>
              </div>
              <details className="scene-details">
                <summary>Inspect metadata</summary>
                <dl>
                  <dt>Band names</dt><dd>{scene.bandNames?.filter(Boolean).join(', ') || 'Not provided by source'}</dd>
                  <dt>Native band resolution</dt><dd>{scene.nativeBandResolutions ? Object.entries(scene.nativeBandResolutions).map(([band, value]) => `${band}: ${value}`).join(', ') : 'Not provided'}</dd>
                  <dt>Product type</dt><dd>{scene.productType ?? 'Not specified'}{scene.processingBaseline ? ` · baseline ${scene.processingBaseline}` : ''}</dd>
                  <dt>Polarization / orbit</dt><dd>{scene.polarization?.join(', ') ?? '—'}{scene.orbitDirection ? ` · ${scene.orbitDirection}` : ''}{scene.relativeOrbit ? ` · relative ${scene.relativeOrbit}` : ''}</dd>
                  <dt>Data types</dt><dd>{scene.bandDtypes?.join(', ') || 'Unknown'}</dd>
                  <dt>NoData</dt><dd>{scene.nodataValues?.map((value) => value ?? 'none').join(', ') ?? 'Not reported'}</dd>
                  <dt>Validity mask</dt><dd>{scene.hasValidityMask ? 'GDAL validity mask present' : 'No explicit mask reported'}</dd>
                  <dt>Affine transform</dt><dd>{scene.transform?.map((value) => Number(value.toPrecision(8))).join(', ') ?? 'Unavailable'}</dd>
                  <dt>Storage</dt><dd>{formatBytes(scene.sizeBytes)} · {scene.productReference}</dd>
                </dl>
              </details>
              <Button variant="ghost" aria-label={`Delete ${scene.sourceFilename}`} disabled={remove.isPending} onClick={() => void deleteScene(scene)}><Trash2 size={16} /></Button>
            </article>)}
          </div>}
      <p className="scene-order-note">Scenes with known acquisition times appear newest first; scenes with unknown dates follow. Duplicate dates and irregular intervals are supported.</p>
    </section>
  );
}
