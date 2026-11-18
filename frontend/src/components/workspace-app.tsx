'use client';
import { useEffect, useState } from 'react';
import { useProjects, useSamples } from '@/hooks/use-projects';
import { useWorkspace } from '@/stores/workspace';
import { Sidebar } from './shell/sidebar';
import { Topbar } from './shell/topbar';
import { LearningWorkspace } from './learning-workspace';
import { ProjectDashboard } from './project-dashboard';
import { DatasetManager } from './datasets';
import { Analytics } from './analytics';
import { UnsupervisedSom } from './unsupervised-som';
import { CreateProjectDialog, HelpDialog, PreferencesDialog } from './workspace-dialogs';
import { ErrorState, Skeleton } from './ui/common';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
export function WorkspaceApp() {
  const { data: projects = [], isLoading, error, refetch } = useProjects();
  const { view, projectId, setProject, setView, drafts } = useWorkspace();
  const project = projects.find((p) => p.id === projectId) ?? projects[0] ?? null;
  const { data: samples = [] } = useSamples(project?.id ?? '');
  const [dialog, setDialog] = useState<'create' | 'help' | 'shortcuts' | 'settings' | null>(null);
  const [pendingSwitch, setPendingSwitch] = useState<{ id: string; datasets: boolean } | null>(
    null,
  );
  const switchProject = (id: string, toDatasets = false) => {
    if (id !== projectId && Object.keys(drafts).length) {
      setPendingSwitch({ id, datasets: toDatasets });
      return;
    }
    if (id !== projectId) setProject(id);
    else setView('learning');
    if (toDatasets) setView('datasets');
  };
  const closeDialog = (open: boolean) => {
    if (!open) setDialog(null);
  };
  useEffect(() => {
    if (projects.length && !projects.some((p) => p.id === projectId)) setProject(projects[0].id);
  }, [projects, projectId, setProject]);
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' });
    document.title = `${{ learning: 'Active learning', unsupervised: 'Unsupervised SOM', projects: 'Your projects', datasets: 'Dataset library', analytics: 'Model analytics' }[view]} · TerraLab`;
  }, [view, projectId]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        e.key === '?' &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement).tagName)
      ) {
        e.preventDefault();
        setDialog('shortcuts');
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  const pendingCount = samples.filter((s) => s.status === 'pending').length;
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to workspace
      </a>
      <Sidebar
        projects={projects}
        onCreate={() => setDialog('create')}
        onSelect={(id) => switchProject(id)}
        onHelp={() => setDialog('help')}
        onSettings={() => setDialog('settings')}
        pendingCount={pendingCount}
      />
      <div className="main-shell">
        <Topbar
          project={project}
          projects={projects}
          onSelect={(id) => switchProject(id)}
          onHelp={() => setDialog('help')}
          onSettings={() => setDialog('settings')}
        />
        <main className="main-content" id="main-content">
          {isLoading ? (
            <WorkspaceSkeleton />
          ) : error ? (
            <ErrorState message={error.message} onRetry={() => refetch()} />
          ) : view === 'projects' ? (
            <ProjectDashboard
              projects={projects}
              onCreate={() => setDialog('create')}
              onSelect={(id) => switchProject(id)}
            />
          ) : project ? (
            <div className="view-transition" key={`${project.id}-${view}`}>
              {view === 'learning' ? (
                <LearningWorkspace project={project} onShortcuts={() => setDialog('shortcuts')} />
              ) : view === 'unsupervised' ? (
                <UnsupervisedSom project={project} />
              ) : view === 'datasets' ? (
                <DatasetManager project={project} />
              ) : (
                <Analytics project={project} />
              )}
            </div>
          ) : (
            <ProjectDashboard
              projects={projects}
              onCreate={() => setDialog('create')}
              onSelect={(id) => switchProject(id)}
            />
          )}
          <footer className="app-footer">
            <span>Made for a better understanding of our planet.</span>
            <span>
              TerraLab <i />
              Human insight. Earth intelligence.
            </span>
          </footer>
        </main>
      </div>
      <CreateProjectDialog
        open={dialog === 'create'}
        onOpenChange={closeDialog}
        onCreated={(id) => switchProject(id, true)}
      />
      <HelpDialog
        open={dialog === 'help' || dialog === 'shortcuts'}
        onOpenChange={closeDialog}
        shortcuts={dialog === 'shortcuts'}
      />
      <PreferencesDialog open={dialog === 'settings'} onOpenChange={closeDialog} />
      <Dialog
        open={!!pendingSwitch}
        onOpenChange={(open) => {
          if (!open) setPendingSwitch(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Keep your human insight?</DialogTitle>
            <DialogDescription>
              You have {Object.keys(drafts).length} unsubmitted reviews. Submit them before
              switching projects, or discard these drafts to continue.
            </DialogDescription>
          </DialogHeader>
          <div className="dialog-footer">
            <Button
              variant="outline"
              onClick={() => {
                setPendingSwitch(null);
                setView('learning');
              }}
            >
              Keep labeling
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (pendingSwitch) {
                  setProject(pendingSwitch.id);
                  if (pendingSwitch.datasets) setView('datasets');
                  setPendingSwitch(null);
                }
              }}
            >
              Discard & switch
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
export function WorkspaceSkeleton() {
  return (
    <div className="workspace-loading" aria-label="Loading your workspace" aria-busy="true">
      <Skeleton className="heading-skeleton" />
      <Skeleton className="subtitle-skeleton" />
      <div className="metric-grid">
        {[0, 1, 2, 3].map((n) => (
          <Skeleton key={n} className="metric-skeleton" />
        ))}
      </div>
      <Skeleton className="section-title-skeleton" />
      <div className="labeling-grid">
        <Skeleton className="workspace-skeleton" />
        <Skeleton className="workspace-skeleton" />
      </div>
    </div>
  );
}
