'use client';
import {
  ArrowUpRight,
  ChartNoAxesCombined,
  ChevronsUpDown,
  CircleHelp,
  Database,
  FolderPlus,
  Grid2x2,
  LayoutGrid,
  Leaf,
  Moon,
  Plus,
  ScanLine,
  Settings2,
  Sparkles,
  Sun,
  X,
} from 'lucide-react';
import { useWorkspace } from '@/stores/workspace';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { Project, WorkspaceView } from '@/types';
const links: { id: WorkspaceView; label: string; icon: typeof LayoutGrid }[] = [
  { id: 'projects', label: 'Overview', icon: LayoutGrid },
  { id: 'datasets', label: 'Datasets', icon: Database },
  { id: 'unsupervised', label: 'Unsupervised SOM', icon: Grid2x2 },
  { id: 'learning', label: 'Active learning', icon: ScanLine },
  { id: 'analytics', label: 'Analytics', icon: ChartNoAxesCombined },
];
export function Brand() {
  return (
    <div className="brand">
      <span className="brand-symbol">
        <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <path d="M16 3 29 10.5 16 18 3 10.5 16 3Z" fill="currentColor" />
          <path
            d="m3 16 13 7.5L29 16"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="m3 22 13 7.5L29 22"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span>
        terralab<span className="brand-period">.</span>
      </span>
    </div>
  );
}
export function Sidebar({
  projects,
  onCreate,
  onSelect,
  onHelp,
  onSettings,
  pendingCount,
}: {
  projects: Project[];
  onCreate: () => void;
  onSelect: (id: string) => void;
  onHelp: () => void;
  onSettings: () => void;
  pendingCount: number;
}) {
  const { view, setView, projectId, theme, toggleTheme, sidebarOpen, setSidebarOpen } =
    useWorkspace();
  return (
    <>
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside className={cn('sidebar', sidebarOpen && 'is-open')}>
        <div className="brand-row">
          <Brand />
          <button
            className="mobile-close icon-button"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>
        <button className="workspace-switcher" onClick={onSettings}>
          <span className="workspace-avatar">
            <Leaf size={17} />
          </span>
          <span>
            <strong>Earth observation</strong>
            <small>Personal workspace</small>
          </span>
          <ChevronsUpDown size={14} />
        </button>
        <div className="nav-section-label">WORKSPACE</div>
        <nav className="main-nav" aria-label="Main navigation">
          {links.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setView(id)}
              className={cn('nav-link', view === id && 'active')}
              aria-current={view === id ? 'page' : undefined}
            >
              <Icon size={18} strokeWidth={1.7} />
              <span>{label}</span>
              {id === 'learning' && pendingCount > 0 && (
                <span className="nav-count">{pendingCount}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="nav-section-label projects-label">
          <span>YOUR PROJECTS</span>
          <button className="icon-button small" onClick={onCreate} aria-label="Create project">
            <Plus size={15} />
          </button>
        </div>
        <nav className="project-nav" aria-label="Projects">
          {projects.map((project, i) => (
            <button
              key={project.id}
              className={cn('project-link', projectId === project.id && 'selected')}
              onClick={() => onSelect(project.id)}
              title={project.name}
            >
              <span
                className="project-dot"
                style={{ background: ['#5f9e85', '#b7a3cf', '#d6b16e'][i % 3] }}
              />
              <span>{project.name}</span>
              {projectId === project.id && <span className="project-selected-dot" />}
            </button>
          ))}
          <button className="new-project-link" onClick={onCreate}>
            <Plus size={15} /> New project
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="insight-card">
            <span className="insight-icon">
              <Sparkles size={17} />
            </span>
            <h4>
              A little human insight.
              <br />A smarter model.
            </h4>
            <p>Better labels. Better understanding.</p>
            <button onClick={onHelp}>
              Explore the workflow <ArrowUpRight size={14} />
            </button>
            <div className="insight-orbit" aria-hidden="true" />
          </div>
          <button className="support-link" onClick={onHelp}>
            <CircleHelp size={17} />
            Help & getting started
            <ArrowUpRight size={14} />
          </button>
          <div className="theme-row">
            <span className="demo-dot" />
            RSAL workspace
            <button
              className="icon-button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
              title={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
            >
              {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            </button>
          </div>
          <button className="profile" onClick={onSettings}>
            <span className="avatar">JD</span>
            <span>
              <strong>Jamie Davis</strong>
              <small>Research workspace</small>
            </span>
            <Settings2 size={16} />
          </button>
        </div>
      </aside>
    </>
  );
}
