'use client';
import { useState } from 'react';
import {
  ArrowRight,
  Check,
  Database,
  FolderPlus,
  Keyboard,
  Leaf,
  LoaderCircle,
  Moon,
  ScanLine,
  Sparkles,
  Sun,
  Tags,
  TrendingUp,
} from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Kbd } from './ui/common';
import { CLASS_COLORS, DEFAULT_CLASS_NAMES } from '@/lib/palette';
import { useCreateProject, useQueryBatch } from '@/hooks/use-projects';
import { cn } from '@/lib/utils';
import { useWorkspace } from '@/stores/workspace';
import type { BinaryOutputInterpretation, Project } from '@/types';
export function CreateProjectDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (id: string) => void;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [count, setCount] = useState(3);
  const [names, setNames] = useState<string[]>(DEFAULT_CLASS_NAMES);
  const [colors, setColors] = useState<string[]>(CLASS_COLORS);
  const [studyAreaCrs, setStudyAreaCrs] = useState('');
  const [studyAreaText, setStudyAreaText] = useState('');
  const [binaryInterpretation, setBinaryInterpretation] = useState<BinaryOutputInterpretation>('water_vs_non_water');
  const create = useCreateProject();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    let studyAreaGeometry: Record<string, unknown> | null = null;
    if (studyAreaText.trim()) {
      try {
        const parsed: unknown = JSON.parse(studyAreaText);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error();
        studyAreaGeometry = parsed as Record<string, unknown>;
      } catch {
        toast.error('Study-area geometry must be a valid GeoJSON geometry object.');
        return;
      }
      if (!studyAreaCrs.trim()) {
        toast.error('Provide the study-area CRS when a geometry is supplied.');
        return;
      }
    }
    try {
      const project = await create.mutateAsync({
        name,
        description,
        classes: Array.from({ length: count }, (_, i) => ({
          id: (names[i] ?? '').trim(),
          name: (names[i] ?? '').trim(),
          color: colors[i % colors.length],
        })),
        studyAreaGeometry,
        studyAreaCrs: studyAreaCrs.trim() || null,
        classificationConfig: {
          internalClasses: ['open_water', 'emergent_vegetation', 'land'] as ['open_water', 'emergent_vegetation', 'land'],
          binaryOutputInterpretation: binaryInterpretation,
        },
      });
      toast.success('Project created. Let’s add your imagery.');
      setName('');
      setDescription('');
      onOpenChange(false);
      onCreated(project.id);
    } catch {
      /* Mutation displays the error. */
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <span className="dialog-icon">
            <FolderPlus size={23} />
          </span>
          <DialogTitle>A new perspective starts here.</DialogTitle>
          <DialogDescription>
            Create a project and define the land-cover classes you want to understand.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="project-form">
          <label className="field-label">
            Project name
            <input
              className="input"
              placeholder="e.g. Sacramento land cover"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              required
              autoFocus
            />
          </label>
          <label className="field-label">
            Description <span className="optional">Optional</span>
            <textarea
              className="input textarea"
              placeholder="What would you like to explore?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={2000}
              rows={2}
            />
          </label>
          <label className="field-label">
            Study-area CRS <span className="optional">Optional unless geometry is supplied</span>
            <input className="input" placeholder="e.g. EPSG:4326" value={studyAreaCrs} onChange={(e) => setStudyAreaCrs(e.target.value)} />
          </label>
          <label className="field-label">
            Study-area GeoJSON <span className="optional">Optional</span>
            <textarea className="input textarea" rows={2} placeholder='{"type":"Polygon","coordinates":[...]}' value={studyAreaText} onChange={(e) => setStudyAreaText(e.target.value)} />
          </label>
          <label className="field-label">
            Binary output interpretation
            <select className="input" value={binaryInterpretation} onChange={(e) => setBinaryInterpretation(e.target.value as BinaryOutputInterpretation)}>
              <option value="water_vs_non_water">Water (open water + emergent vegetation) vs non-water</option>
              <option value="open_water_vs_other">Open water vs all other classes</option>
            </select>
          </label>
          <p className="project-domain-note">Internal WBALC classes remain open_water, emergent_vegetation, and land.</p>
          <div className="class-config-header">
            <label className="field-label" htmlFor="class-count">
              Classification classes
            </label>
            <select
              id="class-count"
              className="input compact-select"
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            >
              {Array.from({ length: 11 }, (_, i) => (
                <option value={i + 2} key={i}>
                  {i + 2} classes
                </option>
              ))}
            </select>
          </div>
          <div className="class-inputs">
            {Array.from({ length: count }, (_, i) => (
              <div className="class-input" key={i}>
                <input
                  type="color"
                  aria-label={`Class ${i + 1} color`}
                  value={colors[i]}
                  onChange={(e) =>
                    setColors((c) => c.map((v, j) => (j === i ? e.target.value : v)))
                  }
                />
                <input
                  className="input"
                  placeholder={`Class ${i + 1} name`}
                  aria-label={`Class ${i + 1} name`}
                  value={names[i] ?? ''}
                  onChange={(e) =>
                    setNames((current) => {
                      const next = [...current];
                      next[i] = e.target.value;
                      return next;
                    })
                  }
                  required
                  maxLength={40}
                />
                <Kbd>{i + 1}</Kbd>
              </div>
            ))}
          </div>
          <div className="dialog-footer">
            <Button variant="outline" type="button" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <LoaderCircle className="spin" size={16} /> : <PlusIcon />}Create
              project
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
function PlusIcon() {
  return <FolderPlus size={16} />;
}
export function HelpDialog({
  open,
  onOpenChange,
  shortcuts = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  shortcuts?: boolean;
}) {
  const steps = [
    {
      icon: Database,
      title: 'Bring your own perspective',
      text: 'Upload one or more GeoTIFFs. We’ll read their spectral bands, coordinate system, and resolution.',
    },
    {
      icon: ScanLine,
      title: 'Find the most valuable samples',
      text: 'Query a batch of uncertain predictions. Explore each location on the interactive map.',
    },
    {
      icon: Tags,
      title: 'Add your human insight',
      text: 'Accept the model’s prediction, assign a different class, or skip a difficult sample. Draw your own samples, too.',
    },
    {
      icon: TrendingUp,
      title: 'Learn. Measure. Repeat.',
      text: 'Submit your labels and retrain. Follow accuracy, class balance, and every iteration in Analytics.',
    },
  ];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={shortcuts ? 'shortcuts-dialog' : ''}>
        <DialogHeader>
          <span className="dialog-icon">
            {shortcuts ? <Keyboard size={23} /> : <Leaf size={23} />}
          </span>
          <DialogTitle>
            {shortcuts ? 'Stay in the labeling flow.' : 'Human insight. Earth intelligence.'}
          </DialogTitle>
          <DialogDescription>
            {shortcuts
              ? 'Less clicking, more understanding. Shortcuts are active in the labeling workspace.'
              : 'A simple, thoughtful workflow for better land-cover models.'}
          </DialogDescription>
        </DialogHeader>
        {!shortcuts && (
          <div className="workflow-steps">
            {steps.map(({ icon: Icon, title, text }, i) => (
              <div key={title}>
                <span className="workflow-number">
                  <Icon size={18} />
                </span>
                <div>
                  <small>STEP 0{i + 1}</small>
                  <h4>{title}</h4>
                  <p>{text}</p>
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="shortcut-list">
          {[
            ['1 – 9', 'Assign a class'],
            ['Enter', 'Accept label & move to next'],
            ['S', 'Skip the current sample'],
            ['← / →', 'Previous / next sample'],
            ['N', 'Add a sample note'],
            ['P', 'Draw a point on the map'],
            ['Escape', 'Cancel drawing'],
            ['?', 'Open keyboard shortcuts'],
          ].map(([key, label]) => (
            <div key={key}>
              <span>{label}</span>
              <Kbd>{key}</Kbd>
            </div>
          ))}
        </div>
        {!shortcuts && (
          <div className="info-callout">
            <Sparkles size={17} />
            <p>
              <strong>Every result here is real.</strong> Queries, training, and metrics run on the
              WBALC backend against your uploaded imagery. Start with a diversity batch, label at
              least four samples across two classes, then train your first model.
            </p>
          </div>
        )}
        <Button className="full-width" onClick={() => onOpenChange(false)}>
          Let’s explore <ArrowRight size={16} />
        </Button>
      </DialogContent>
    </Dialog>
  );
}
export function PreferencesDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { theme, toggleTheme } = useWorkspace();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <span className="dialog-icon">
            <Leaf size={23} />
          </span>
          <DialogTitle>Your workspace</DialogTitle>
          <DialogDescription>A comfortable place to see the bigger picture.</DialogDescription>
        </DialogHeader>
        <div className="preference-row">
          <div>
            <strong>Appearance</strong>
            <p>Choose the theme that works for you.</p>
          </div>
          <Button variant="outline" onClick={toggleTheme}>
            {theme === 'light' ? <Sun size={16} /> : <Moon size={16} />}{' '}
            {theme === 'light' ? 'Light' : 'Dark'} mode
          </Button>
        </div>
        <div className="preference-info">
          <strong>Backend connection</strong>
          <p>
            This workspace runs on the RSAL active-learning backend. Point the frontend server at
            your backend with:
          </p>
          <code>RSAL_API_URL=http://localhost:8000</code>
          <p>
            An optional <code>RSAL_API_TOKEN</code> stays on the server. Restart the frontend after
            changing environment variables.
          </p>
        </div>
        <div className="info-callout">
          <Check size={17} />
          <p>
            Projects, uploads, labels, and iteration history live in the WBALC backend. Unsubmitted
            reviews and your current batch are saved locally in this browser.
          </p>
        </div>
        <Button className="full-width" onClick={() => onOpenChange(false)}>
          Done
        </Button>
      </DialogContent>
    </Dialog>
  );
}
export function QueryBatchDialog({
  project,
  open,
  onOpenChange,
}: {
  project: Project;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [batchSize, setBatchSize] = useState(12);
  const hasModel = !!project.modelVersion;
  const [strategy, setStrategy] = useState(hasModel ? 'entropy' : 'diversity');
  const query = useQueryBatch(project.id);
  const selectSample = useWorkspace((s) => s.selectSample);
  const selectDataset = useWorkspace((s) => s.selectDataset);
  const selectedDatasetId = useWorkspace((s) => s.selectedDatasetId);
  const run = async () => {
    try {
      const result = await query.mutateAsync({
        batchSize,
        strategy,
        datasetId: selectedDatasetId ?? undefined,
      });
      if (result.samples[0]) {
        selectSample(result.samples[0].id);
        if (result.samples[0].datasetId) selectDataset(result.samples[0].datasetId);
      }
      toast.success(`${result.samples.length} samples added to the review queue.`, {
        description:
          strategy === 'som'
            ? hasModel
              ? 'Balanced model uncertainty across Kohonen topological clusters.'
              : 'Cold-start Kohonen SOM topological sampling — no model needed yet.'
            : hasModel
              ? 'Ranked by your trained model on the WBALC backend.'
              : 'Cold-start core-set selection — no model needed yet.',
      });
      onOpenChange(false);
    } catch {
      /* Mutation displays errors. */
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <span className="dialog-icon">
            <Sparkles size={23} />
          </span>
          <DialogTitle>Make your next labels count.</DialogTitle>
          <DialogDescription>
            Find the samples where your expertise makes the biggest difference.
          </DialogDescription>
        </DialogHeader>
        <label className="field-label">
          Batch size
          <select
            className="input"
            value={batchSize}
            onChange={(e) => setBatchSize(Number(e.target.value))}
          >
            {[6, 12, 24, 48].map((n) => (
              <option key={n} value={n}>
                {n} samples
              </option>
            ))}
          </select>
        </label>
        <div className="field-label strategy-label">Sampling strategy</div>
        <div className="strategy-options">
          {[
            {
              id: 'diversity',
              title: 'Diversity (core-set)',
              text: 'Cover the scene’s spectral variety. Works before the first model.',
              tag: hasModel ? undefined : 'Recommended',
              needsModel: false,
            },
            {
              id: 'som',
              title: 'Self-organizing map (SOM)',
              text: hasModel
                ? 'Balance model uncertainty across topological spectral clusters.'
                : 'Organize patches onto a 2D Kohonen grid to sample distinct clusters.',
              tag: 'Topological',
              needsModel: false,
            },
            {
              id: 'entropy',
              title: 'Predictive entropy',
              text: 'Review predictions with the most overall uncertainty.',
              tag: hasModel ? 'Recommended' : undefined,
              needsModel: true,
            },
            {
              id: 'margin',
              title: 'Margin sampling',
              text: 'Focus on samples with two equally likely classes.',
              needsModel: true,
            },
            {
              id: 'least-confidence',
              title: 'Least confidence',
              text: 'Review the model’s least confident predictions.',
              needsModel: true,
            },
            {
              id: 'hybrid',
              title: 'Hybrid (uncertainty + diversity)',
              text: 'Uncertain candidates, diversified into a representative batch.',
              needsModel: true,
            },
          ].map((s) => (
            <label
              key={s.id}
              className={cn(
                'strategy-option',
                strategy === s.id && 'selected',
                s.needsModel && !hasModel && 'disabled',
              )}
            >
              <input
                type="radio"
                name="strategy"
                checked={strategy === s.id}
                disabled={s.needsModel && !hasModel}
                onChange={() => setStrategy(s.id)}
              />
              <span>
                <strong>
                  {s.title}
                  {s.tag && <small>{s.tag}</small>}
                </strong>
                <p>
                  {s.needsModel && !hasModel
                    ? 'Train your first model to unlock this strategy.'
                    : s.text}
                </p>
              </span>
            </label>
          ))}
        </div>
        <div className="dialog-footer">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={run} disabled={query.isPending}>
            {query.isPending ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}{' '}
            {query.isPending ? 'Finding samples…' : 'Query next batch'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
