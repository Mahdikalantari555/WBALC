'use client';
import { useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  Download,
  History,
  TrendingUp,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useMetrics } from '@/hooks/use-projects';
import { api } from '@/lib/api';
import { useWorkspace } from '@/stores/workspace';
import { downloadCSV, downloadJSON, formatNumber } from '@/lib/utils';
import { Button } from './ui/button';
import { Badge, Dot, EmptyState, ErrorState, Skeleton } from './ui/common';
import { MetricCards } from './metric-cards';
import { SomExplorer } from './som-explorer';
import type {
  Iteration,
  MapExportFormat,
  MapLayer,
  Metrics,
  Project,
} from '@/types';

/** An export row as the adapter reports it. */
interface ExportRow {
  id: number;
  type: string;
  dataset_name?: string | null;
  iteration?: number | null;
  method?: string | null;
  stale?: boolean;
  created_at?: string;
}

const LAYER_NAMES: Record<string, string> = {
  hard: 'Classification',
  uncertainty: 'Uncertainty',
  probability: 'Probabilities',
};
const tooltipStyle = {
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 9,
  fontSize: 11,
  color: 'var(--text)',
  boxShadow: '0 4px 20px #0000000a',
};
function LearningCurve({ metrics, compact = false }: { metrics: Metrics; compact?: boolean }) {
  const [range, setRange] = useState('all');
  const curve = range === 'all' ? metrics.curve : metrics.curve.slice(-Number(range));
  const data = curve.map((it) => ({
    iteration: `${it.number}`,
    accuracy: Number((it.accuracy * 100).toFixed(1)),
    f1: Number((it.f1 * 100).toFixed(1)),
    labeled: it.labeledCount,
  }));
  const improvement = metrics.curve.length
    ? ((metrics.accuracy - metrics.curve[0].accuracy) * 100).toFixed(1)
    : '0';
  return (
    <article className="chart-card learning-curve-card">
      <div className="chart-card-heading">
        <div>
          <h3>Learning curve</h3>
          <p>A smarter model with every iteration.</p>
        </div>
        {compact ? (
          <span className="chart-improvement">
            <TrendingUp size={13} />+{improvement}%
          </span>
        ) : (
          <select
            className="chart-select"
            value={range}
            onChange={(e) => setRange(e.target.value)}
            aria-label="Learning curve range"
          >
            <option value="all">All iterations</option>
            <option value="5">Last 5 iterations</option>
            <option value="3">Last 3 iterations</option>
          </select>
        )}
      </div>
      <div className="chart-legend">
        <span>
          <i className="line-key" />
          Accuracy
        </span>
        <span>
          <i className="line-key secondary" />
          F1 score
        </span>
      </div>
      {data.length ? (
        <div className="curve-container">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 10, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient
                  id={compact ? 'accuracyFillCompact' : 'accuracyFill'}
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop offset="0%" stopColor="#55a184" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#55a184" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="3 4" />
              <XAxis
                dataKey="labeled"
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#8c9594', fontSize: 10 }}
                tickFormatter={formatNumber}
                tickMargin={9}
              />
              <YAxis
                domain={[0, 100]}
                ticks={[0, 25, 50, 75, 100]}
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#8c9594', fontSize: 10 }}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                contentStyle={tooltipStyle}
                labelFormatter={(l) => `${formatNumber(Number(l))} labeled samples`}
                formatter={(value, name) => [
                  `${value}%`,
                  name === 'accuracy' ? 'Accuracy' : 'F1 score',
                ]}
              />
              <Area
                type="monotone"
                dataKey="f1"
                stroke="#b2c8bd"
                strokeWidth={1.8}
                strokeDasharray="4 4"
                fill="transparent"
                isAnimationActive={false}
              />
              <Area
                type="monotone"
                dataKey="accuracy"
                stroke="#388e70"
                strokeWidth={2.3}
                fill={`url(#${compact ? 'accuracyFillCompact' : 'accuracyFill'})`}
                dot={{ r: 3, fill: '#fff', stroke: '#388e70', strokeWidth: 2 }}
                activeDot={{ r: 5 }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <EmptyState
          title="Your learning curve starts here"
          description="Train your first model to see how accuracy improves."
        />
      )}
      <div className="chart-footer">
        <span>{metrics.curve.length} completed iterations</span>
        <span>
          Labeled samples <ArrowRight size={12} />
        </span>
      </div>
    </article>
  );
}
function ClassDistribution({ metrics, compact = false }: { metrics: Metrics; compact?: boolean }) {
  return (
    <article className="chart-card class-distribution-card">
      <div className="chart-card-heading">
        <div>
          <h3>Class distribution</h3>
          <p>A balanced view of your labeled data.</p>
        </div>
        <Badge>{formatNumber(metrics.labeledCount)} samples</Badge>
      </div>
      <div className="distribution-stacked">
        {metrics.distribution.map((c) => (
          <span
            key={c.name}
            style={{
              background: c.color,
              width: `${metrics.labeledCount ? (c.value / metrics.labeledCount) * 100 : 100 / metrics.distribution.length}%`,
            }}
            title={`${c.name}: ${c.value} labels`}
          />
        ))}
      </div>
      <div className="distribution-rows">
        {metrics.distribution.map((c) => (
          <div key={c.name}>
            <span>
              <Dot color={c.color} />
              {c.name}
            </span>
            <div className="distribution-bar">
              <i
                style={{
                  width: `${metrics.labeledCount ? (c.value / metrics.labeledCount) * 100 * 2.5 : 0}%`,
                  background: c.color,
                }}
              />
            </div>
            <strong>{formatNumber(c.value)}</strong>
            <span className="distribution-percent">
              {metrics.labeledCount ? Math.round((c.value / metrics.labeledCount) * 100) : 0}%
            </span>
          </div>
        ))}
      </div>
    </article>
  );
}
export function AnalyticsPreview({ project }: { project: Project }) {
  const { data, isLoading, error, refetch } = useMetrics(project.id);
  const setView = useWorkspace((s) => s.setView);
  if (isLoading)
    return (
      <div className="analytics-preview">
        <Skeleton className="chart-skeleton" />
        <Skeleton className="chart-skeleton" />
      </div>
    );
  if (error) return <ErrorState message={error.message} onRetry={() => refetch()} />;
  if (!data) return null;
  return (
    <>
      <div className="section-heading insights-section-heading">
        <div>
          <h2>Your model, at a glance</h2>
          <span className="section-subtitle">A little better with every label.</span>
        </div>
        <button className="text-button green-text" onClick={() => setView('analytics')}>
          View analytics
          <ArrowUpRight size={14} />
        </button>
      </div>
      <div className="analytics-preview">
        <LearningCurve metrics={data} compact />
        <ClassDistribution metrics={data} compact />
      </div>
    </>
  );
}
function IterationHistory({ metrics }: { metrics: Metrics }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <article className="history-card" id="iteration-history">
      <div className="chart-card-heading">
        <div>
          <h3>
            <History size={16} />
            Iteration history
          </h3>
          <p>Every step forward, in one place.</p>
        </div>
        <Badge>{metrics.curve.length} iterations</Badge>
      </div>
      {metrics.curve.length ? (
        <div className="table-scroll">
          <table className="data-table history-table">
            <thead>
              <tr>
                <th>Iteration</th>
                <th>Labeled samples</th>
                <th>New samples</th>
                <th>Accuracy</th>
                <th>Macro F1</th>
                <th>Completed</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {[...metrics.curve].reverse().map((iteration, i) => (
                <HistoryRows
                  key={iteration.id}
                  iteration={iteration}
                  latest={i === 0}
                  expanded={expanded === iteration.id}
                  onToggle={() => setExpanded(expanded === iteration.id ? null : iteration.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="The first chapter is yours"
          description="Submit a batch of labels and train your model to start your history."
        />
      )}
    </article>
  );
}
function HistoryRows({
  iteration,
  latest,
  expanded,
  onToggle,
}: {
  iteration: Iteration;
  latest: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr>
        <td>
          <button className="history-iteration" onClick={onToggle}>
            Iteration {String(iteration.number).padStart(2, '0')}
            {latest && <Badge>Latest</Badge>}
          </button>
        </td>
        <td>{formatNumber(iteration.labeledCount)}</td>
        <td>
          <span className="green-text">+{iteration.sampleCount}</span>
        </td>
        <td>
          <strong>{(iteration.accuracy * 100).toFixed(1)}%</strong>
        </td>
        <td>{iteration.f1.toFixed(3)}</td>
        <td>
          {new Date(iteration.createdAt).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          })}
          <span className="history-time">
            {new Date(iteration.createdAt).toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </td>
        <td>
          <button
            className="icon-button"
            aria-label={`Details for iteration ${iteration.number}`}
            onClick={onToggle}
          >
            <ChevronDown size={16} style={{ transform: expanded ? 'rotate(180deg)' : undefined }} />
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="history-expanded">
          <td colSpan={7}>
            <div>
              <span>
                <Check size={16} />
                Completed with {iteration.sampleCount} newly reviewed samples and{' '}
                {formatNumber(iteration.labeledCount)} cumulative labels.
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => downloadJSON(iteration, `iteration-${iteration.number}.json`)}
              >
                <Download size={13} />
                Export iteration
              </Button>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
/**
 * The maps that exist for this project, with the iteration that produced them
 * and whether a newer run has superseded them. Each row downloads the same
 * artifact the map view renders.
 */
function MapExports({ project }: { project: Project }) {
  const exports = useQuery({
    queryKey: ['project', project.id, 'exports'],
    queryFn: async () => {
      const response = await fetch(`/api/projects/${project.id}/exports`);
      if (!response.ok) throw new Error('The export list could not be loaded.');
      return (await response.json()) as ExportRow[];
    },
  });

  if (exports.isLoading)
    return (
      <article className="chart-card map-exports-card">
        <Skeleton className="chart-skeleton" />
      </article>
    );

  const rows = exports.data ?? [];
  return (
    <article className="chart-card map-exports-card">
      <div className="chart-card-heading">
        <div>
          <h3>Maps</h3>
          <p>Classification and uncertainty rasters produced by your models.</p>
        </div>
      </div>
      {!rows.length ? (
        <EmptyState
          title="No maps yet"
          description="Train a model, then enable a layer in the map view — every layer is exportable as GeoTIFF, PNG or CSV."
        />
      ) : (
        <div className="map-export-list">
          {rows.map((row) => {
            const layer = (row.type === 'hard' ? 'hard' : row.type) as MapLayer | 'probability';
            const downloadable = layer === 'hard' || layer === 'uncertainty';
            return (
              <div className="map-export-row" key={row.id}>
                <div>
                  <strong>{LAYER_NAMES[layer] ?? row.type}</strong>
                  <span>
                    {row.dataset_name ?? `dataset ${row.id}`} · iteration {row.iteration ?? '—'}
                    {row.method ? ` · ${row.method.replace('_', ' ')}` : ''}
                  </span>
                </div>
                {row.stale && <span className="map-export-stale">retrain available</span>}
                {downloadable ? (
                  <div className="map-export-links">
                    {(['tif', 'png', 'csv'] as MapExportFormat[]).map((format) => (
                      <a
                        key={format}
                        href={api.mapExportUrl(project.id, {
                          layer: layer as MapLayer,
                          format,
                          method: (row.method as 'entropy') ?? 'entropy',
                        })}
                      >
                        {format.toUpperCase()}
                      </a>
                    ))}
                  </div>
                ) : (
                  <div className="map-export-links">
                    <a
                      href={api.mapExportUrl(project.id, {
                        layer: 'probability',
                        format: 'tif',
                        datasetId: undefined,
                      })}
                      title="One GeoTIFF band per class"
                    >
                      TIF
                    </a>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </article>
  );
}

export function Analytics({ project }: { project: Project }) {
  const { data, isLoading, error, refetch } = useMetrics(project.id);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            <span />
            MEASURE WHAT MATTERS
          </div>
          <h1>Model analytics</h1>
          <p>A clearer picture of your progress, one iteration at a time.</p>
        </div>
        <div className="heading-actions">
          <Button
            variant="outline"
            disabled={!data?.curve.length}
            onClick={() =>
              data &&
              downloadCSV(
                [
                  ['iteration', 'accuracy', 'macro_f1', 'new_samples', 'labeled_samples', 'completed_at'],
                  ...data.curve.map((it) => [
                    it.number,
                    it.accuracy.toFixed(4),
                    it.f1.toFixed(4),
                    it.sampleCount,
                    it.labeledCount,
                    it.createdAt,
                  ]),
                ],
                `${project.id}-iterations.csv`,
              )
            }
          >
            <Download size={15} />
            Export CSV
          </Button>
          <Button
            variant="outline"
            disabled={!data}
            onClick={() =>
              downloadJSON(
                { project: project.name, exportedAt: new Date().toISOString(), ...data },
                `${project.id}-metrics.json`,
              )
            }
          >
            <Download size={15} />
            Export report
          </Button>
        </div>
      </div>
      <MetricCards project={project} pendingCount={0} />
      {isLoading ? (
        <div className="analytics-preview">
          <Skeleton className="chart-skeleton" />
          <Skeleton className="chart-skeleton" />
        </div>
      ) : error ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : (
        data && (
          <>
            <div className="analytics-full-grid">
              <LearningCurve metrics={data} />
              <ClassDistribution metrics={data} />
              <article className="chart-card confusion-card">
                <div className="chart-card-heading">
                  <div>
                    <h3>Confusion matrix</h3>
                    <p>Understand where your model gets uncertain.</p>
                  </div>
                  <Badge>{data.evaluation === 'train' ? 'Training set' : 'Validation set'}</Badge>
                </div>
                <div className="matrix-axis">PREDICTED CLASS</div>
                <div className="table-scroll">
                  <table className="confusion-matrix">
                    <thead>
                      <tr>
                        <th />
                        {project.classes.map((c) => (
                          <th key={c.id}>{c.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.confusionMatrix.map((row, i) => (
                        <tr key={i}>
                          <th>{project.classes[i]?.name}</th>
                          {row.map((value, j) => {
                            const scale = value / Math.max(1, ...row);
                            return (
                              <td
                                key={j}
                                style={{
                                  background: `rgba(49, 137, 106, ${0.05 + scale * 0.82})`,
                                  color: scale > 0.5 ? '#fff' : 'var(--text-secondary)',
                                }}
                                title={`Actual ${project.classes[i]?.name}, predicted ${project.classes[j]?.name}: ${value}`}
                              >
                                {value}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="matrix-footnote">
                  Rows: actual class · Columns: predicted class
                  {data.evaluation === 'train'
                    ? ' · Evaluated on training data (small sample)'
                    : data.evaluation
                      ? ` · ${data.evaluation} evaluation`
                      : ''}
                </p>
              </article>
              <article className="chart-card confidence-card">
                <div className="chart-card-heading">
                  <div>
                    <h3>Per-class performance</h3>
                    <p>Where the model shines, and where it needs you.</p>
                  </div>
                  <TrendingUp size={19} className="green-text" />
                </div>
                {data.perClass.length && data.curve.length > 0 ? (
                  <div className="table-scroll">
                    <table className="data-table per-class-table">
                      <thead>
                        <tr>
                          <th>Class</th>
                          <th>Precision</th>
                          <th>Recall</th>
                          <th>F1</th>
                          <th>Support</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.perClass.map((c) => (
                          <tr key={c.name}>
                            <td>
                              <span className="per-class-name">
                                <Dot color={c.color} />
                                {c.name}
                              </span>
                            </td>
                            <td>{(c.precision * 100).toFixed(1)}%</td>
                            <td>{(c.recall * 100).toFixed(1)}%</td>
                            <td>
                              <strong>{c.f1.toFixed(3)}</strong>
                            </td>
                            <td>{formatNumber(c.support)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState
                    title="No class report yet"
                    description="Train a model to see precision, recall, and F1 for every class."
                  />
                )}
              </article>
            </div>
            <SomExplorer project={project} />
            <IterationHistory metrics={data} />
            <MapExports project={project} />
          </>
        )
      )}
    </>
  );
}
