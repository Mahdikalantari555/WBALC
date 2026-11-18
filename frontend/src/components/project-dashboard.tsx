'use client';
import { useState } from 'react';
import {
  ArrowRight,
  ArrowUpRight,
  FolderClosed,
  Layers,
  MapPin,
  Plus,
  Search,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react';
import { Button } from './ui/button';
import { Badge, EmptyState } from './ui/common';
import { cn, formatNumber } from '@/lib/utils';
import type { Project } from '@/types';
export function ProjectDashboard({
  projects,
  onCreate,
  onSelect,
}: {
  projects: Project[];
  onCreate: () => void;
  onSelect: (id: string) => void;
}) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('recent');
  const visible = projects
    .filter(
      (p) =>
        (filter === 'all' || p.status === filter) &&
        `${p.name} ${p.description}`.toLowerCase().includes(search.toLowerCase()),
    )
    .sort((a, b) =>
      sort === 'name'
        ? a.name.localeCompare(b.name)
        : new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span />A WORLD OF POSSIBILITIES
          </div>
          <h1>Your projects</h1>
          <p>From pixels to insight. Pick up where you left off.</p>
        </div>
        <Button onClick={onCreate}>
          <Plus size={17} />
          Create project
        </Button>
      </div>
      <div className="overview-banner">
        <div className="overview-banner-icon">
          <Layers size={29} />
        </div>
        <div>
          <h2>Big-picture thinking. Pixel-level precision.</h2>
          <p>Your expertise and machine learning, working better together.</p>
        </div>
        <div className="overview-total">
          <strong>{formatNumber(projects.reduce((a, p) => a + p.labeledCount, 0))}</strong>
          <span>human-powered labels</span>
        </div>
        <div className="banner-orbits" />
      </div>
      <div className="project-toolbar">
        <div className="filter-tabs">
          {[
            { id: 'all', name: 'All projects' },
            { id: 'in_progress', name: 'In progress' },
            { id: 'unlabeled', name: 'Unlabeled' },
            { id: 'completed', name: 'Completed' },
          ].map((t) => (
            <button
              key={t.id}
              className={cn(filter === t.id && 'active')}
              onClick={() => setFilter(t.id)}
            >
              {t.name}
              {t.id === 'all' && <span>{projects.length}</span>}
            </button>
          ))}
        </div>
        <div className="project-filters">
          <div className="search-field">
            <Search size={15} />
            <input
              placeholder="Search projects…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search projects"
            />
          </div>
          <select
            className="input sort-select"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            aria-label="Sort projects"
          >
            <option value="recent">Most recent</option>
            <option value="name">Name A–Z</option>
          </select>
        </div>
      </div>
      <div className="project-grid">
        {visible.map((project, i) => (
          <article className="project-card" key={project.id}>
            <button
              className={cn('project-cover', `cover-${i % 3}`)}
              onClick={() => onSelect(project.id)}
              aria-label={`Open ${project.name}`}
            >
              <span className="project-cover-grid" />
              <span className="project-location">
                <MapPin size={12} />
                Your area of interest
              </span>
              <span className="project-cover-classes">
                <Layers size={12} />
                {project.classes.length} classes
              </span>
            </button>
            <div className="project-card-body">
              <div className="project-card-status">
                <Badge className={`status-${project.status}`}>
                  <span />
                  {project.status === 'in_progress'
                    ? 'In progress'
                    : project.status === 'completed'
                      ? 'Completed'
                      : 'Unlabeled'}
                </Badge>
                <span>Research project</span>
              </div>
              <button className="project-card-title" onClick={() => onSelect(project.id)}>
                <h3>{project.name}</h3>
                <ArrowUpRight size={17} />
              </button>
              <p>{project.description || 'A new perspective, waiting to be explored.'}</p>
              <div className="project-card-metrics">
                <div>
                  <small>Labeled samples</small>
                  <strong>
                    {formatNumber(project.labeledCount)}{' '}
                    <span>/ {formatNumber(project.totalSamples)}</span>
                  </strong>
                </div>
                <div>
                  <small>Accuracy</small>
                  <strong>
                    {project.accuracy ? `${(project.accuracy * 100).toFixed(1)}%` : '—'}
                  </strong>
                </div>
              </div>
              <div className="project-progress">
                <span
                  style={{
                    width: `${project.totalSamples ? (project.labeledCount / project.totalSamples) * 100 : 0}%`,
                  }}
                />
              </div>
              <div className="project-card-footer">
                <span>Iteration {String(project.iteration).padStart(2, '0')}</span>
                <button onClick={() => onSelect(project.id)}>
                  Open workspace <ArrowRight size={13} />
                </button>
              </div>
            </div>
          </article>
        ))}
        {filter === 'all' && !search && (
          <button className="create-project-card" onClick={onCreate}>
            <span>
              <Plus size={25} />
            </span>
            <h3>Explore something new</h3>
            <p>
              Start with a question.
              <br />
              Build a new perspective.
            </p>
            <strong>
              Create a project <ArrowUpRight size={14} />
            </strong>
          </button>
        )}
      </div>
      {visible.length === 0 && (
        <EmptyState
          title="No projects found"
          description="Try a different search or create a project for your next discovery."
          action={
            <Button
              variant="outline"
              onClick={() => {
                setSearch('');
                setFilter('all');
              }}
            >
              Reset filters
            </Button>
          }
        />
      )}
      <p className="projects-footer">
        <Sparkles size={14} />
        The next great insight starts with a single label.
      </p>
    </>
  );
}
