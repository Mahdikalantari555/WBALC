'use client';
import dynamic from 'next/dynamic';
import { useRef, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import {
  Box,
  Check,
  ChevronRight,
  Database,
  Download,
  Eye,
  FileImage,
  FileJson,
  Layers,
  LoaderCircle,
  Map,
  Plus,
  Ruler,
  Search,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { useDatasets, useDeleteDataset, useSaveLabels, useUpload } from '@/hooks/use-projects';
import { SceneCollection } from './scene-collection';
import { forgetDataset } from '@/lib/geotiff';
import { parseLabels } from '@/lib/import-labels';
import { useRasterPreview } from '@/lib/use-raster';
import { cn, downloadJSON, errorMessage, formatBytes, formatNumber } from '@/lib/utils';
import { useWorkspace } from '@/stores/workspace';
import { Button } from './ui/button';
import { Badge, EmptyState, ErrorState, Skeleton } from './ui/common';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import type { Dataset, Project } from '@/types';
const DeckPreview = dynamic(() => import('./map/deck-preview'), {
  ssr: false,
  loading: () => (
    <div className="deck-loading">
      <LoaderCircle className="spin" size={24} />
      Preparing the raster inspector…
    </div>
  ),
});
type UploadItem = { id: string; name: string; progress: number; stage: string; error?: string };
export function DatasetManager({ project }: { project: Project }) {
  const { data: datasets = [], isLoading, error, refetch } = useDatasets(project.id);
  const upload = useUpload(project.id);
  const remove = useDeleteDataset(project.id);
  const saveLabels = useSaveLabels(project.id);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [search, setSearch] = useState('');
  const [inspecting, setInspecting] = useState<Dataset | null>(null);
  const [deleting, setDeleting] = useState<Dataset | null>(null);
  const [threeD, setThreeD] = useState(false);
  const [importing, setImporting] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  const { selectDataset, setView, selectedDatasetId } = useWorkspace();
  const inspectorPreview = useRasterPreview(inspecting);
  const busy = uploads.some((u) => u.progress < 100 && !u.error);
  const onDrop = async (files: File[]) => {
    const items = files.map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      progress: 0,
      stage: 'Reading spectral data…',
    }));
    setUploads((old) => [...items, ...old]);
    for (let i = 0; i < files.length; i++) {
      const file = files[i],
        id = items[i].id;
      const update = (patch: Partial<UploadItem>) =>
        setUploads((old) => old.map((item) => (item.id === id ? { ...item, ...patch } : item)));
      try {
        update({ progress: 5, stage: 'Uploading GeoTIFF…' });
        await upload.mutateAsync({
          file,
          onProgress: (progress) =>
            update({
              progress: Math.max(5, progress),
              stage:
                progress < 95
                  ? 'Uploading GeoTIFF…'
                  : progress === 100
                    ? 'Ready to explore'
                    : 'Reading geospatial metadata…',
            }),
        });
        toast.success(`${file.name} is ready to explore.`);
      } catch (e) {
        update({ error: errorMessage(e), stage: 'Upload failed' });
      }
    }
  };
  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: { 'image/tiff': ['.tif', '.tiff'] },
    multiple: true,
    maxSize: 100 * 1024 * 1024,
    disabled: busy,
    onDropRejected: (rejections) =>
      rejections.forEach((r) =>
        toast.error(
          `${r.file.name}: ${r.errors[0].code === 'file-too-large' ? 'Files must be under 100 MB.' : 'Choose a .tif or .tiff file.'}`,
        ),
      ),
  });
  const importFile = async (file: File) => {
    setImporting(true);
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('Label files must be under 10 MB.');
      const target = datasets.find((d) => d.id === selectedDatasetId) ?? datasets[0];
      if (!target) throw new Error('Upload a GeoTIFF before importing labels.');
      if (target.pixelSpace)
        throw new Error(
          'Label import needs georeferenced imagery (WGS84 coordinates). This scene has no CRS.',
        );
      const labels = parseLabels(await file.text(), file.name, project.classes).map((l) => ({
        ...l,
        datasetId: target.id,
      }));
      await saveLabels.mutateAsync(labels);
      toast.success(`${labels.length} training labels imported.`, {
        description: 'They’re saved to your project and visible on the map.',
      });
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setImporting(false);
      if (importRef.current) importRef.current.value = '';
    }
  };
  const viewOnMap = (dataset: Dataset) => {
    selectDataset(dataset.id);
    setView('learning');
  };
  return (
    <>
      <SceneCollection project={project} />
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span />
            YOUR WINDOW TO THE WORLD
          </div>
          <h1>Dataset library</h1>
          <p>Bring your imagery. Find a new perspective.</p>
        </div>
        <div className="heading-actions">
          <Button variant="outline" disabled={importing} onClick={() => importRef.current?.click()}>
            {importing ? <LoaderCircle className="spin" size={15} /> : <FileJson size={15} />}Import
            labels
          </Button>
          <Button onClick={open} disabled={busy}>
            <Plus size={16} />
            Upload imagery
          </Button>
        </div>
      </div>
      <input
        ref={importRef}
        type="file"
        accept=".geojson,.json,.csv"
        className="sr-only"
        aria-label="Import GeoJSON or CSV labels"
        onChange={(e) => {
          if (e.target.files?.[0]) importFile(e.target.files[0]);
        }}
      />
      <div className="dataset-summary">
        <div>
          <span className="summary-icon green">
            <FileImage size={21} />
          </span>
          <div>
            <strong>{datasets.length}</strong>
            <span>Satellite scenes</span>
          </div>
        </div>
        <div>
          <span className="summary-icon purple">
            <Layers size={21} />
          </span>
          <div>
            <strong>{datasets.reduce((a, d) => a + d.bands, 0)}</strong>
            <span>Spectral bands</span>
          </div>
        </div>
        <div>
          <span className="summary-icon blue">
            <Database size={21} />
          </span>
          <div>
            <strong>{formatBytes(datasets.reduce((a, d) => a + d.size, 0))}</strong>
            <span>Total dataset size</span>
          </div>
        </div>
        <div>
          <span className="summary-icon amber">
            <Ruler size={21} />
          </span>
          <div>
            <strong>{datasets[0]?.resolution ?? '—'}</strong>
            <span>Ground resolution</span>
          </div>
        </div>
      </div>
      <div
        {...getRootProps()}
        className={cn('upload-dropzone', isDragActive && 'drag-active', busy && 'busy')}
      >
        <input {...getInputProps()} aria-label="Upload GeoTIFF files" />
        <span className="upload-icon">
          <UploadCloud size={27} />
        </span>
        <h3>
          {isDragActive
            ? 'A new perspective. Drop it here.'
            : busy
              ? 'Bringing your imagery into focus…'
              : 'Drag your satellite imagery here'}
        </h3>
        <p>
          or <span>browse files</span> to add them to your dataset
        </p>
        <div className="upload-formats">
          <span>GeoTIFF</span>
          <i />
          Single or multi-band
          <i />
          Up to 100 MB per file
        </div>
      </div>
      {uploads.length > 0 && (
        <div className="upload-list">
          {uploads.map((item) => (
            <div className={cn('upload-item', item.error && 'has-error')} key={item.id}>
              <span className="file-icon">
                <FileImage size={20} />
              </span>
              <div>
                <strong>{item.name}</strong>
                <div className="upload-progress-label">
                  <span>{item.error ?? item.stage}</span>
                  {!item.error && <span>{item.progress}%</span>}
                </div>
                {item.progress < 100 && !item.error && (
                  <div className="progress-track">
                    <span style={{ width: `${item.progress}%` }} />
                  </div>
                )}
              </div>
              {item.progress === 100 ? (
                <span className="upload-success">
                  <Check size={19} />
                </span>
              ) : item.error ? (
                <button
                  className="icon-button"
                  aria-label="Dismiss failed upload"
                  onClick={() => setUploads((u) => u.filter((x) => x.id !== item.id))}
                >
                  <X size={17} />
                </button>
              ) : (
                <LoaderCircle size={17} className="spin" />
              )}
            </div>
          ))}
        </div>
      )}
      <div className="section-heading dataset-section-heading">
        <div>
          <h2>Your imagery</h2>
          <Badge>{datasets.length} scenes</Badge>
        </div>
        <div className="search-field">
          <Search size={15} />
          <input
            aria-label="Search datasets"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search imagery…"
          />
        </div>
      </div>
      {isLoading ? (
        <Skeleton className="dataset-table-skeleton" />
      ) : error ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : datasets.length === 0 ? (
        <div className="table-empty">
          <EmptyState
            title="Room for a whole new world"
            description="Upload your first GeoTIFF to start exploring spectral bands and creating training labels."
          />
        </div>
      ) : (
        <div className="dataset-table-card table-scroll">
          <table className="data-table dataset-table">
            <thead>
              <tr>
                <th>Filename</th>
                <th>Dimensions</th>
                <th>Bands</th>
                <th>Resolution</th>
                <th>Coordinate system</th>
                <th>Size</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {datasets
                .filter((d) => d.name.toLowerCase().includes(search.toLowerCase()))
                .map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      <button
                        className="dataset-name"
                        onClick={() => {
                          setInspecting(dataset);
                          setThreeD(false);
                        }}
                      >
                        <span
                          className="dataset-thumbnail"
                          style={{
                            backgroundImage: dataset.previewUrl
                              ? `url("${dataset.previewUrl}")`
                              : undefined,
                          }}
                        >
                          {!dataset.previewUrl && <FileImage size={20} />}
                        </span>
                        <span>
                          <strong>{dataset.name}</strong>
                          <small>GeoTIFF · Ready to explore</small>
                        </span>
                      </button>
                    </td>
                    <td>
                      {formatNumber(dataset.width)} × {formatNumber(dataset.height)}
                      <small>pixels</small>
                    </td>
                    <td>
                      <Badge>{dataset.bands} bands</Badge>
                    </td>
                    <td>{dataset.resolution}</td>
                    <td>
                      <code>{dataset.crs}</code>
                    </td>
                    <td>{formatBytes(dataset.size)}</td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="icon-button"
                          onClick={() => viewOnMap(dataset)}
                          aria-label={`View ${dataset.name} on map`}
                          title="View on map"
                        >
                          <Map size={16} />
                        </button>
                        <button
                          className="icon-button"
                          onClick={() => {
                            setInspecting(dataset);
                            setThreeD(false);
                          }}
                          aria-label={`Inspect ${dataset.name}`}
                          title="Inspect metadata"
                        >
                          <Eye size={16} />
                        </button>
                        <button
                          className="icon-button danger-hover"
                          onClick={() => setDeleting(dataset)}
                          aria-label={`Delete ${dataset.name}`}
                          title="Remove dataset"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          {!datasets.some((d) => d.name.toLowerCase().includes(search.toLowerCase())) && (
            <div className="table-no-results">No imagery matches “{search}”.</div>
          )}
          <div className="dataset-table-footer">
            <span>
              {datasets.filter((d) => d.name.toLowerCase().includes(search.toLowerCase())).length}{' '}
              of {datasets.length} scenes
            </span>
            <span>
              <span className="online-dot" />
              All imagery indexed
            </span>
          </div>
        </div>
      )}
      <div className="import-help">
        <span>
          <FileJson size={21} />
        </span>
        <div>
          <h4>Already have ground-truth labels?</h4>
          <p>
            Import GeoJSON points or polygons, or a CSV with <code>latitude</code>,{' '}
            <code>longitude</code>, and <code>class</code> columns. Up to 1,000 samples per import.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => importRef.current?.click()}
          disabled={importing}
        >
          Import samples
          <ChevronRight size={14} />
        </Button>
      </div>
      <Dialog
        open={!!inspecting}
        onOpenChange={(open) => {
          if (!open) setInspecting(null);
        }}
      >
        <DialogContent className="dataset-inspector">
          <DialogHeader>
            <DialogTitle>{inspecting?.name}</DialogTitle>
            <DialogDescription>
              Explore your scene’s spatial and spectral metadata.
            </DialogDescription>
          </DialogHeader>
          {inspecting && (
            <>
              <div className="inspector-toolbar">
                <Badge>GeoTIFF raster</Badge>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setThreeD(!threeD)}
                  disabled={!inspectorPreview.data || inspecting.pixelSpace}
                  title={
                    inspecting.pixelSpace
                      ? '3D globe view needs a georeferenced scene'
                      : 'Toggle 3D raster view'
                  }
                >
                  <Box size={14} />
                  {threeD ? '2D preview' : '3D raster view'}
                </Button>
              </div>
              {threeD ? (
                <DeckPreview dataset={inspecting} imageUrl={inspectorPreview.data ?? null} />
              ) : inspectorPreview.data ? (
                <img
                  className="inspector-image"
                  src={inspectorPreview.data}
                  alt={`${inspecting.name} satellite raster`}
                />
              ) : (
                <div className="no-preview">
                  {inspectorPreview.isLoading ? (
                    <LoaderCircle size={30} className="spin" />
                  ) : (
                    <FileImage size={36} />
                  )}
                  <p>
                    {inspectorPreview.isLoading
                      ? 'Rendering spectral preview…'
                      : (inspectorPreview.error?.message ??
                        'No browser preview is available for this raster.')}
                  </p>
                </div>
              )}
              <dl className="metadata-grid">
                {[
                  [
                    'Dimensions',
                    `${formatNumber(inspecting.width)} × ${formatNumber(inspecting.height)} px`,
                  ],
                  ['Spectral bands', String(inspecting.bands)],
                  ['Resolution', inspecting.resolution],
                  ['Coordinate system', inspecting.crs],
                  ['File size', formatBytes(inspecting.size)],
                  [
                    'Georeferenced',
                    inspecting.pixelSpace
                      ? 'No · displayed in pixel space'
                      : 'Yes · WGS84 bounds available',
                  ],
                ].map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              <div className="dialog-footer">
                <Button
                  variant="outline"
                  onClick={() => downloadJSON(inspecting, `${inspecting.id}-metadata.json`)}
                >
                  <Download size={15} />
                  Export metadata
                </Button>
                <Button
                  onClick={() => {
                    viewOnMap(inspecting);
                    setInspecting(null);
                  }}
                >
                  <Map size={15} />
                  Open on map
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <span className="dialog-icon danger">
              <Trash2 size={23} />
            </span>
            <DialogTitle>Remove this scene?</DialogTitle>
            <DialogDescription>
              {deleting?.name} will be permanently removed, along with its stored file, training
              labels, and prediction exports. Iteration history is kept.
            </DialogDescription>
          </DialogHeader>
          <div className="dialog-footer">
            <Button variant="outline" onClick={() => setDeleting(null)}>
              Keep scene
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={async () => {
                if (!deleting) return;
                try {
                  await remove.mutateAsync(deleting.id);
                  forgetDataset(deleting.id);
                  toast.success('Scene removed from your dataset.');
                  setDeleting(null);
                } catch {
                  /* Mutation displays the error. */
                }
              }}
            >
              {remove.isPending ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <Trash2 size={15} />
              )}
              Remove scene
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
