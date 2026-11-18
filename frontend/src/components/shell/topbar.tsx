'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Bell,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  CloudCheck,
  FolderClosed,
  Menu,
  Search,
} from 'lucide-react';
import { useWorkspace } from '@/stores/workspace';
import { cn } from '@/lib/utils';
import type { Project } from '@/types';
export function Topbar({
  project,
  projects,
  onSelect,
  onHelp,
  onSettings,
}: {
  project: Project | null;
  projects: Project[];
  onSelect: (id: string) => void;
  onHelp: () => void;
  onSettings: () => void;
}) {
  const { drafts, setView, setSidebarOpen } = useWorkspace();
  const [menu, setMenu] = useState<'projects' | 'notifications' | null>(null);
  const [search, setSearch] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setMenu(null);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);
  const draftCount = Object.keys(drafts).length;
  return (
    <header className="topbar" ref={ref}>
      <div className="breadcrumbs">
        <button
          className="icon-button menu-toggle"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open navigation"
        >
          <Menu size={20} />
        </button>
        <FolderClosed size={16} className="breadcrumb-folder" />
        <button onClick={() => setView('projects')}>Projects</button>
        <ChevronRight size={14} />
        <div className="popover-anchor">
          <button
            className="project-breadcrumb"
            onClick={() => setMenu(menu === 'projects' ? null : 'projects')}
            aria-expanded={menu === 'projects'}
          >
            {project?.name ?? 'Your workspace'}
            <ChevronDown size={14} />
          </button>
          {menu === 'projects' && (
            <div className="popover project-popover">
              <div className="popover-search">
                <Search size={15} />
                <input
                  placeholder="Find a project…"
                  aria-label="Find a project"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="popover-label">YOUR PROJECTS</div>
              {projects
                .filter((p) => p.name.toLowerCase().includes(search.toLowerCase()))
                .map((p) => (
                  <button
                    key={p.id}
                    className={cn('popover-item', project?.id === p.id && 'selected')}
                    onClick={() => {
                      onSelect(p.id);
                      setMenu(null);
                      setSearch('');
                    }}
                  >
                    <FolderClosed size={15} />
                    <span>{p.name}</span>
                    {project?.id === p.id && <Check size={15} />}
                  </button>
                ))}
              {!projects.some((p) => p.name.toLowerCase().includes(search.toLowerCase())) && (
                <p className="popover-empty">No matching projects.</p>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="topbar-actions">
        <span className={cn('save-status', draftCount > 0 && 'unsaved')}>
          <CloudCheck size={15} />
          {draftCount
            ? `${draftCount} label${draftCount === 1 ? '' : 's'} to submit`
            : 'All changes saved'}
        </span>
        <span className="topbar-divider" />
        <button className="icon-button" aria-label="Open help" onClick={onHelp}>
          <CircleHelp size={18} />
        </button>
        <div className="popover-anchor">
          <button
            className="icon-button notification-button"
            onClick={() => setMenu(menu === 'notifications' ? null : 'notifications')}
            aria-label="Notifications"
            aria-expanded={menu === 'notifications'}
          >
            <Bell size={18} />
            <span />
          </button>
          {menu === 'notifications' && (
            <div className="popover notifications">
              <div className="notification-header">
                <strong>Workspace updates</strong>
                <CheckCheck size={16} />
              </div>
              <div className="notification-item">
                <span className="notification-icon">
                  <Check size={17} />
                </span>
                <div>
                  <strong>
                    {project?.accuracy ? 'Your model is ready' : 'Welcome to TerraLab'}
                  </strong>
                  <p>
                    {project?.accuracy
                      ? `${(project.accuracy * 100).toFixed(1)}% accuracy · ${project.modelVersion}`
                      : 'Upload your first GeoTIFF to get started.'}
                  </p>
                  <small>Current project status</small>
                </div>
              </div>
              {draftCount > 0 && (
                <div className="notification-item">
                  <span className="notification-icon amber">
                    <CloudCheck size={17} />
                  </span>
                  <div>
                    <strong>{draftCount} reviews ready to submit</strong>
                    <p>Your drafts are saved in this browser.</p>
                    <button
                      onClick={() => {
                        setView('learning');
                        setMenu(null);
                      }}
                    >
                      Continue labeling →
                    </button>
                  </div>
                </div>
              )}
              <div className="notification-footer">You’re all caught up.</div>
            </div>
          )}
        </div>
        <button
          className="avatar avatar-small"
          onClick={onSettings}
          aria-label="Workspace preferences"
        >
          JD
        </button>
      </div>
    </header>
  );
}
