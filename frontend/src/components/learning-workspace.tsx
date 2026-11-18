'use client';
import { useState } from 'react';
import {
  ArrowUpRight,
  CheckCheck,
  History,
  Keyboard,
  Leaf,
  LoaderCircle,
  Sparkles,
} from 'lucide-react';
import { toast } from 'sonner';
import { useDatasets, useSamples, useSaveLabels, useTrain } from '@/hooks/use-projects';
import { useWorkspace } from '@/stores/workspace';
import { Button } from './ui/button';
import { ErrorState, Skeleton } from './ui/common';
import { MetricCards } from './metric-cards';
import { MapViewer } from './map/map-viewer';
import { SampleReview } from './sample-review';
import { QueryBatchDialog } from './workspace-dialogs';
import { AnalyticsPreview } from './analytics';
import { SomExplorer } from './som-explorer';
import type { Project } from '@/types';
export function LearningWorkspace({
  project,
  onShortcuts,
}: {
  project: Project;
  onShortcuts: () => void;
}) {
  const {
    data: datasets,
    isLoading: datasetsLoading,
    error: datasetsError,
    refetch: retryDatasets,
  } = useDatasets(project.id);
  const {
    data: samples,
    isLoading: samplesLoading,
    error: samplesError,
    refetch: retrySamples,
  } = useSamples(project.id);
  const [queryOpen, setQueryOpen] = useState(false);
  const [stage, setStage] = useState<'idle' | 'saving' | 'training' | 'complete'>('idle');
  const save = useSaveLabels(project.id);
  const train = useTrain(project.id);
  const { drafts, clearDrafts, setView, selectSample } = useWorkspace();
  const pending = samples?.filter((s) => s.status === 'pending').length ?? 0;
  const submit = async () => {
    const labels = Object.values(drafts);
    try {
      const shouldTrain =
        labels.some((l) => l.status === 'labeled') ||
        (!project.modelVersion && samples?.some((s) => s.saved && s.status === 'labeled'));
      if (labels.length) {
        setStage('saving');
        await save.mutateAsync(labels);
        clearDrafts();
      }
      if (shouldTrain) {
        setStage('training');
        const result = await train.mutateAsync();
        toast.success(`Iteration ${result.iteration.number} complete`, {
          description: `${(result.iteration.accuracy * 100).toFixed(1)}% model accuracy on real training data. Query your next batch to keep learning.`,
        });
        selectSample(null);
      } else toast.success('Review decisions saved. Query a new batch when you’re ready.');
      setStage('idle');
    } catch {
      setStage('idle');
    }
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span />
            HUMAN-IN-THE-LOOP
          </div>
          <h1>Active learning</h1>
          <p>A little guidance from you. A big leap for your model.</p>
        </div>
        <div className="heading-actions">
          <Button variant="outline" onClick={() => setView('analytics')}>
            <History size={15} />
            Iteration history
          </Button>
          <Button
            onClick={() => setQueryOpen(true)}
            disabled={stage === 'saving' || stage === 'training'}
          >
            <Sparkles size={16} />
            Query next batch
          </Button>
        </div>
      </div>
      <MetricCards project={project} pendingCount={pending} />
      <div className="section-heading workspace-section-heading">
        <div>
          <h2>Labeling workspace</h2>
          <span className="model-status">
            <span />
            {stage === 'saving' || stage === 'training' ? 'Model training' : 'Model ready'}
          </span>
        </div>
        <button className="text-button keyboard-button" onClick={onShortcuts}>
          <Keyboard size={15} />
          Keyboard shortcuts<span>?</span>
        </button>
      </div>
      {datasetsError || samplesError ? (
        <ErrorState
          message={(datasetsError ?? samplesError)!.message}
          onRetry={() => {
            retryDatasets();
            retrySamples();
          }}
        />
      ) : datasetsLoading || samplesLoading ? (
        <div className="labeling-grid">
          <Skeleton className="workspace-skeleton" />
          <Skeleton className="workspace-skeleton" />
        </div>
      ) : (
        <div className="labeling-grid">
          <MapViewer
            project={project}
            datasets={datasets ?? []}
            samples={samples ?? []}
            busy={stage === 'saving' || stage === 'training'}
          />
          <SampleReview
            project={project}
            samples={samples ?? []}
            datasets={datasets ?? []}
            onSubmit={submit}
            stage={stage}
            onQuery={() => setQueryOpen(true)}
          />
        </div>
      )}
      <div className="session-footer">
        <span>
          <Leaf size={13} />
          Every label helps your model see the bigger picture.
        </span>
        <span>
          <CheckCheck size={13} />
          {Object.keys(drafts).length ? 'Drafts saved locally' : 'Workspace up to date'}
        </span>
      </div>
      <SomExplorer project={project} compact />
      <AnalyticsPreview project={project} />
      <QueryBatchDialog project={project} open={queryOpen} onOpenChange={setQueryOpen} />
    </>
  );
}
