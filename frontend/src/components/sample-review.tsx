'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CornerDownLeft,
  Grid2X2,
  List,
  LoaderCircle,
  MapPin,
  MessageSquarePlus,
  ScanLine,
  SkipForward,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { useDeleteLabel } from '@/hooks/use-projects';
import { renderPatch } from '@/lib/geotiff';
import { useWorkspace } from '@/stores/workspace';
import { cn } from '@/lib/utils';
import { Button } from './ui/button';
import { Badge, Dot, EmptyState, Kbd } from './ui/common';
import type { BandMode, Dataset, Project, Sample } from '@/types';
interface Props {
  project: Project;
  samples: Sample[];
  datasets: Dataset[];
  onSubmit: () => void;
  stage: 'idle' | 'saving' | 'training' | 'complete';
  onQuery: () => void;
}
/**
 * The patch the model actually classified, read from that patch's pixel window
 * of the sample's own dataset. No scaled whole-image background, no CSS
 * positioning: what you see is the crop.
 */
function SamplePatch({
  sample,
  dataset,
  bandMode,
  onClick,
}: {
  sample: Sample;
  dataset: Dataset | undefined;
  bandMode: BandMode;
  onClick?: () => void;
}) {
  const [context, setContext] = useState(false);
  const window = useMemo(() => {
    if (!dataset || !sample.window) return null;
    if (!context) return sample.window;
    const pad = dataset.patchGrid?.patchSize ?? 32;
    return {
      x0: Math.max(0, sample.window.x0 - pad),
      y0: Math.max(0, sample.window.y0 - pad),
      x1: Math.min(dataset.width, sample.window.x1 + pad),
      y1: Math.min(dataset.height, sample.window.y1 + pad),
    };
  }, [dataset, sample.window, context]);

  const preview = useQuery({
    queryKey: ['patch', dataset?.id, window, bandMode],
    queryFn: () =>
      renderPatch(dataset!.url, dataset!.id, window!, bandMode, undefined, context ? 132 : 96),
    enabled: !!dataset && !!window,
    staleTime: Infinity,
    retry: 0,
  });

  const centre = sample.pixel
    ? { x: sample.pixel.x + (sample.window ? (sample.window.x1 - sample.window.x0) / 2 : 0),
        y: sample.pixel.y + (sample.window ? (sample.window.y1 - sample.window.y0) / 2 : 0) }
    : null;

  return (
    <div className="sample-patch-wrap">
      <button
        className="sample-patch"
        onClick={onClick}
        aria-label="Locate this sample on the map"
      >
        {preview.data && (
          <img className="sample-patch-image" src={preview.data} alt="" aria-hidden="true" />
        )}
        {!preview.data && (
          <span className="patch-loading">
            <LoaderCircle size={14} className="spin" />
          </span>
        )}
        {!context && <span className="patch-crosshair" />}
        <span className="patch-corner">
          <ScanLine size={14} />
        </span>
        <span className="patch-coordinate">
          <MapPin size={10} />
          {sample.window
            ? `x ${Math.round(sample.window.x0)}–${Math.round(sample.window.x1)} · y ${Math.round(sample.window.y0)}–${Math.round(sample.window.y1)} px`
            : centre
              ? `x ${Math.round(centre.x)}, y ${Math.round(centre.y)} px`
              : 'no patch footprint'}
        </span>
      </button>
      <div className="patch-caption">
        <span title="The sample's dataset — thumbnails always read from it, never from the dataset the map happens to show.">
          {dataset?.name ?? 'No dataset'}
        </span>
        <button
          className="patch-context"
          onClick={() => setContext((value) => !value)}
          aria-pressed={context}
          title={context ? 'Show the patch only' : 'Show the patch with one patch of context'}
        >
          {context ? 'Patch only' : 'With context'}
        </button>
      </div>
    </div>
  );
}
export function SampleReview({ project, samples, datasets, onSubmit, stage, onQuery }: Props) {
  const {
    selectedSampleId,
    selectSample,
    drafts,
    saveDraft,
    setActiveClass,
    setTool,
    selectedDatasetId,
    bandMode,
  } = useWorkspace();
  const current = samples.filter(
    (s) => s.source === 'query' && (s.iteration === project.iteration || s.status === 'pending'),
  );
  const queue = current.length ? current : samples.filter((s) => s.source === 'query').slice(-12);
  const active = samples.find((s) => s.id === selectedSampleId) ?? queue[0];
  const index = Math.max(
    0,
    queue.findIndex((s) => s.id === active?.id),
  );
  const dataset = datasets.find((d) => d.id === selectedDatasetId) ?? datasets[0];
  const [chosenClass, setChosenClass] = useState('');
  const [note, setNote] = useState('');
  const [noteOpen, setNoteOpen] = useState(false);
  const [batchMode, setBatchMode] = useState(false);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const deleteLabel = useDeleteLabel(project.id);
  const busy = stage === 'saving' || stage === 'training';
  const reviewed = queue.filter((s) => drafts[s.id] || s.status !== 'pending').length;
  const draftCount = Object.keys(drafts).length;
  const savedTrainable =
    !project.modelVersion && samples.some((s) => s.saved && s.status === 'labeled');
  const hasTrainable = Object.values(drafts).some((d) => d.status === 'labeled') || savedTrainable;
  const canSubmit = draftCount > 0 || savedTrainable;
  useEffect(() => {
    if (!selectedSampleId && queue[0]) selectSample(queue[0].id);
  }, [selectedSampleId, queue, selectSample]);
  useEffect(() => {
    if (!active) return;
    const draft = drafts[active.id];
    const label = draft?.label ?? active.label ?? active.prediction;
    // Sync the class picker to the newly selected sample (external selection).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setChosenClass(label);
    setActiveClass(label);
    setNote(draft?.note ?? active.note);
    setNoteOpen(!!(draft?.note ?? active.note));
  }, [active?.id]);
  const move = (direction: number) => {
    if (queue.length) selectSample(queue[(index + direction + queue.length) % queue.length].id);
  };
  const nextUnreviewed = () => {
    for (let n = 1; n < queue.length; n++) {
      const item = queue[(index + n) % queue.length];
      if (!drafts[item.id] && item.status === 'pending') {
        selectSample(item.id);
        return;
      }
    }
    toast.success('Batch reviewed. Ready for your next iteration.');
  };
  const accept = () => {
    if (!active || busy) return;
    saveDraft({
      sampleId: active.id,
      label: chosenClass || active.prediction,
      status: 'labeled',
      note,
      lat: active.lat,
      lng: active.lng,
      geometry: active.geometry,
      datasetId: active.datasetId,
      pixel: active.pixel,
    });
    nextUnreviewed();
  };
  const skip = () => {
    if (!active || busy) return;
    saveDraft({
      sampleId: active.id,
      label: null,
      status: 'skipped',
      note: note || 'Hard sample — revisit later.',
      datasetId: active.datasetId,
      pixel: active.pixel,
    });
    nextUnreviewed();
  };
  const choose = (id: string) => {
    setChosenClass(id);
    setActiveClass(id);
  };
  useEffect(() => {
    const handle = (e: KeyboardEvent) => {
      if (
        document.querySelector('[role="dialog"]') ||
        ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes((e.target as HTMLElement).tagName) ||
        e.metaKey ||
        e.ctrlKey ||
        busy
      )
        return;
      if (e.key >= '1' && e.key <= '9') {
        const c = project.classes[Number(e.key) - 1];
        if (c) {
          e.preventDefault();
          choose(c.id);
        }
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        accept();
      }
      if (e.key.toLowerCase() === 's') {
        e.preventDefault();
        skip();
      }
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        move(1);
      }
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        move(-1);
      }
      if (e.key.toLowerCase() === 'n') {
        e.preventDefault();
        setNoteOpen(true);
        setTimeout(() => noteRef.current?.focus(), 0);
      }
      if (e.key.toLowerCase() === 'p') {
        e.preventDefault();
        setTool('point');
      }
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  });
  const acceptAll = () => {
    queue
      .filter((s) => s.status === 'pending' && !drafts[s.id] && s.prediction)
      .forEach((s) =>
        saveDraft({
          sampleId: s.id,
          label: s.prediction,
          status: 'labeled',
          note: 'Batch accepted prediction',
          datasetId: s.datasetId,
          pixel: s.pixel,
        }),
      );
    toast.success('Batch predictions accepted. Review any label before submitting.');
    setBatchMode(false);
  };
  const prediction = project.classes.find((c) => c.id === active?.prediction);
  const currentDraft = active ? drafts[active.id] : undefined;
  return (
    <aside className="review-card">
      <div className="review-header">
        <h3>
          Sample review <Badge>{queue.length} in batch</Badge>
        </h3>
        <button
          className={cn('icon-button', batchMode && 'active')}
          title={batchMode ? 'Individual review' : 'Batch labeling mode'}
          aria-label={batchMode ? 'Individual review' : 'Batch labeling mode'}
          onClick={() => setBatchMode(!batchMode)}
        >
          {batchMode ? <List size={17} /> : <Grid2X2 size={16} />}
        </button>
      </div>
      {queue.length > 0 && (
        <div className="batch-progress">
          <div>
            <span>Batch progress</span>
            <strong>
              {reviewed}
              <span> / {queue.length} reviewed</span>
            </strong>
          </div>
          <div className="progress-track">
            <span style={{ width: `${(reviewed / queue.length) * 100}%` }} />
          </div>
        </div>
      )}
      {!active ? (
        <div className="review-empty">
          <EmptyState
            title="A fresh perspective awaits"
            description="Query a batch to find the samples that need your expertise."
            action={
              <Button size="sm" variant="outline" onClick={onQuery}>
                <Sparkles size={15} />
                Query samples
              </Button>
            }
          />
        </div>
      ) : batchMode ? (
        <div className="batch-review">
          <div className="batch-review-heading">
            <span>Review the whole picture</span>
            <Button
              size="sm"
              variant="secondary"
              onClick={acceptAll}
              disabled={busy || reviewed === queue.length}
            >
              <Check size={13} />
              Accept all
            </Button>
          </div>
          <div className="batch-samples">
            {queue.map((sample, i) => (
              <div className={cn('batch-sample', drafts[sample.id] && 'reviewed')} key={sample.id}>
                <button
                  className="batch-sample-number"
                  onClick={() => {
                    selectSample(sample.id);
                    setBatchMode(false);
                  }}
                >
                  {String(i + 1).padStart(2, '0')}
                </button>
                <div>
                  <strong>{Math.round(sample.confidence * 100)}% confidence</strong>
                  <select
                    aria-label={`Class for sample ${i + 1}`}
                    value={drafts[sample.id]?.label ?? sample.label ?? sample.prediction}
                    onChange={(e) =>
                      saveDraft({
                        sampleId: sample.id,
                        label: e.target.value,
                        status: 'labeled',
                        note: sample.note,
                        datasetId: sample.datasetId,
                        pixel: sample.pixel,
                      })
                    }
                  >
                    {project.classes.map((c) => (
                      <option value={c.id} key={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  className="icon-button"
                  aria-label={`Accept sample ${i + 1}`}
                  onClick={() =>
                    saveDraft({
                      sampleId: sample.id,
                      label: drafts[sample.id]?.label ?? sample.prediction,
                      status: 'labeled',
                      note: sample.note,
                      datasetId: sample.datasetId,
                      pixel: sample.pixel,
                    })
                  }
                >
                  <CircleCheck size={18} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="review-body">
          <div className="sample-navigation">
            <div>
              <span className="sample-id" title={active.id}>
                Sample {String(index + 1).padStart(2, '0')}
              </span>
              {(currentDraft || active.status !== 'pending') && (
                <span className="sample-reviewed" title="Reviewed">
                  <CircleCheck size={13} />
                </span>
              )}
              {active.saved && (
                <button
                  className="icon-button danger-hover"
                  title="Delete the saved label for this sample"
                  aria-label="Delete saved label"
                  disabled={busy || deleteLabel.isPending}
                  onClick={async () => {
                    try {
                      await deleteLabel.mutateAsync(active.id);
                      toast.success('Saved label deleted. The sample is pending again.');
                    } catch {
                      /* Mutation displays the error. */
                    }
                  }}
                >
                  {deleteLabel.isPending ? (
                    <LoaderCircle size={13} className="spin" />
                  ) : (
                    <Trash2 size={13} />
                  )}
                </button>
              )}
            </div>
            <div>
              <span>
                {index + 1} <i>/ {queue.length || 1}</i>
              </span>
              <button className="icon-button" onClick={() => move(-1)} aria-label="Previous sample">
                <ChevronLeft size={16} />
              </button>
              <button className="icon-button" onClick={() => move(1)} aria-label="Next sample">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
          <SamplePatch
            sample={active}
            dataset={datasets.find((d) => d.id === active.datasetId) ?? dataset}
            bandMode={bandMode}
            onClick={() => {
              selectSample(active.id);
              toast.info('Sample selected on the map. Use the crosshair control to zoom to it.');
            }}
          />
          <div className="prediction-row">
            <div>
              <span className="small-label">MODEL PREDICTION</span>
              <strong>
                <Dot color={prediction?.color ?? '#c5ad52'} />
                {prediction?.name ?? 'Unclassified'}
              </strong>
            </div>
            <span className="confidence-badge">
              {Math.round(active.confidence * 100)}% confidence
            </span>
          </div>
          <div className="uncertainty-row">
            <span>
              Uncertainty score{' '}
              <span
                title="Higher uncertainty means this sample is more informative for the model."
                className="info-circle"
              >
                i
              </span>
            </span>
            <span>
              <span className="uncertainty-bars">
                <i />
                <i />
                <i />
                <i />
              </span>
              {active.uncertainty.toFixed(2)}
              <strong>{active.uncertainty > 0.7 ? 'High' : 'Moderate'}</strong>
            </span>
          </div>
          <div className="assign-heading">
            <span>Assign a class</span>
            <span>
              Use keys <Kbd>1–{Math.min(project.classes.length, 9)}</Kbd>
            </span>
          </div>
          <div className="class-choices">
            {project.classes.map((c, i) => (
              <button
                key={c.id}
                disabled={busy}
                className={cn('class-choice', chosenClass === c.id && 'selected')}
                onClick={() => choose(c.id)}
              >
                <Dot color={c.color} />
                <span>{c.name}</span>
                {chosenClass === c.id ? (
                  <Check size={13} />
                ) : (
                  <span className="class-shortcut">{i + 1}</span>
                )}
              </button>
            ))}
          </div>
          {noteOpen ? (
            <div className="sample-note">
              <textarea
                ref={noteRef}
                className="input"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                maxLength={1000}
                placeholder="What should we know about this sample?"
                rows={2}
                aria-label="Sample note"
              />
              <button
                className="icon-button"
                onClick={() => setNoteOpen(false)}
                aria-label="Close note"
              >
                <X size={13} />
              </button>
            </div>
          ) : (
            <button
              className="add-note"
              onClick={() => {
                setNoteOpen(true);
                setTimeout(() => noteRef.current?.focus(), 0);
              }}
            >
              <MessageSquarePlus size={14} />
              {note ? 'Edit sample note' : 'Add a note'}
              <span>Optional</span>
            </button>
          )}
          <div className="review-actions">
            <Button
              variant="outline"
              onClick={skip}
              disabled={busy}
              title="Mark as hard and skip (S)"
            >
              <SkipForward size={14} />
              Skip
            </Button>
            <Button variant="secondary" className="accept-button" onClick={accept} disabled={busy}>
              <Check size={15} />
              {currentDraft?.status === 'labeled' ? 'Update label' : 'Accept label'}
              <CornerDownLeft size={13} />
            </Button>
          </div>
        </div>
      )}
      <div className="submit-section">
        {busy ? (
          <>
            <div className="training-stage">
              <LoaderCircle className="spin" size={15} />
              <span>
                {stage === 'saving'
                  ? 'Saving your human insight…'
                  : 'Training the next model…'}
              </span>
            </div>
            <div className="progress-track training-track">
              <span style={{ width: stage === 'saving' ? '30%' : '78%' }} />
            </div>
          </>
        ) : (
          <Button className="submit-button" onClick={onSubmit} disabled={!canSubmit}>
            <Sparkles size={15} />
            {hasTrainable || !draftCount ? 'Submit labels & retrain' : 'Save review decisions'}
            <ArrowRight size={15} />
          </Button>
        )}
        <p>
          {busy
            ? 'Keep this workspace open. We’re on it.'
            : draftCount
              ? `${draftCount} review${draftCount === 1 ? '' : 's'} ready to submit`
              : 'Your expertise makes the difference.'}
        </p>
      </div>
    </aside>
  );
}
