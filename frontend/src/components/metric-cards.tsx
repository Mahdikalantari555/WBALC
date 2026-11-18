'use client';
import { Crosshair, Repeat2, Tags, TrendingUp } from 'lucide-react';
import { useMetrics } from '@/hooks/use-projects';
import { formatNumber } from '@/lib/utils';
import { Trend } from './ui/common';
import type { Project } from '@/types';
function Sparkline({ purple = false }: { purple?: boolean }) {
  return (
    <svg className="sparkline" viewBox="0 0 92 35" fill="none" aria-hidden="true">
      <path
        d="M1 32 13 27 23 29 34 18 44 21 55 12 65 15 77 6 90 3V35H1Z"
        fill={purple ? '#eee9f8' : '#e9f4ee'}
      />
      <path
        d="M1 32 13 27 23 29 34 18 44 21 55 12 65 15 77 6 90 3"
        stroke={purple ? '#a58ac7' : '#6ca98b'}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
export function MetricCards({
  project,
  pendingCount = 12,
}: {
  project: Project;
  pendingCount?: number;
}) {
  const { data } = useMetrics(project.id);
  const previous =
    data?.curve.length && data.curve.length > 1 ? data.curve[data.curve.length - 2] : undefined;
  const improvement = previous ? ((project.accuracy - previous.accuracy) * 100).toFixed(1) : null;
  const progress = project.totalSamples ? (project.labeledCount / project.totalSamples) * 100 : 0;
  return (
    <div className="metric-grid">
      <article className="metric-card">
        <div className="metric-label">
          <span>Model accuracy</span>
          <span className="metric-icon green">
            <Crosshair size={16} />
          </span>
        </div>
        <div className="metric-value">
          {project.accuracy ? (project.accuracy * 100).toFixed(1) : '—'}
          {project.accuracy > 0 && <span>%</span>}
          <Sparkline />
        </div>
        <div className="metric-detail">
          {improvement ? (
            <>
              <Trend>{improvement}%</Trend>
              <span>vs. last iteration</span>
            </>
          ) : (
            <span>Ready for your first model</span>
          )}
        </div>
      </article>
      <article className="metric-card">
        <div className="metric-label">
          <span>Macro F1 score</span>
          <span className="metric-icon purple">
            <TrendingUp size={16} />
          </span>
        </div>
        <div className="metric-value">
          {project.f1 ? project.f1.toFixed(3) : '—'}
          <Sparkline purple />
        </div>
        <div className="metric-detail">
          {previous ? (
            <>
              <Trend>{(project.f1 - previous.f1).toFixed(3)}</Trend>
              <span>vs. last iteration</span>
            </>
          ) : (
            <span>Balanced across all classes</span>
          )}
        </div>
      </article>
      <article className="metric-card">
        <div className="metric-label">
          <span>Labeled samples</span>
          <span className="metric-icon blue">
            <Tags size={16} />
          </span>
        </div>
        <div className="metric-value">
          {formatNumber(project.labeledCount)}
          <span className="metric-denominator">/ {formatNumber(project.totalSamples)}</span>
        </div>
        <div className="metric-detail sample-progress-detail">
          <div className="mini-progress">
            <span style={{ width: `${Math.min(100, progress)}%` }} />
          </div>
          <span>{progress.toFixed(0)}% of dataset</span>
        </div>
      </article>
      <article className="metric-card">
        <div className="metric-label">
          <span>Current iteration</span>
          <span className="metric-icon amber">
            <Repeat2 size={16} />
          </span>
        </div>
        <div className="metric-value">
          {String(project.iteration).padStart(2, '0')}
          <span className="iteration-badge">
            <span />
            {pendingCount ? 'Labeling in progress' : 'Ready to query'}
          </span>
        </div>
        <div className="metric-detail">
          <span>
            {pendingCount ? (
              <>
                <strong>{pendingCount} samples</strong> in the current batch
              </>
            ) : (
              'Query a batch to keep learning'
            )}
          </span>
        </div>
      </article>
    </div>
  );
}
