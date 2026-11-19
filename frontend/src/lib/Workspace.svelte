<script lang="ts">
  import { onMount, untrack, type Component } from 'svelte';
  import {
    Bell, ChartNoAxesCombined, Check, ChevronDown, ChevronRight, CircleCheck,
    Database, FlaskConical, FolderPlus, LayoutDashboard, Map as MapIcon, MapPin, Menu, PanelLeftClose,
    PanelLeftOpen, RefreshCw, ScanLine, Tags, TriangleAlert, X,
  } from '@lucide/svelte';
  import EmptyState from './components/EmptyState.svelte';
  import LocaleSwitch from './components/LocaleSwitch.svelte';
  import Intake from './pages/Intake.svelte';
  import Overview from './pages/Overview.svelte';
  import { applyDocumentLocale } from './i18n/store.svelte';
  import type { Locale } from './i18n/locales';
  import { createWorkspace, provideWorkspace, viewFromHash, views, type ViewId } from './state.svelte';
  import { useT } from './t.svelte';

  let { locale }: { locale: Locale } = $props();

  // Seeded once from the SSR cookie; the runtime store takes over on switch.
  // `untrack` documents that this read is intentionally the initial value only.
  const workspace = provideWorkspace(untrack(() => createWorkspace(locale)));
  const { t } = useT();

  const nav = [
    {
      title: 'nav.workspace' as const,
      items: [
        { view: 'overview' as const, icon: LayoutDashboard },
        { view: 'intake' as const, icon: FolderPlus },
        { view: 'map' as const, icon: MapIcon },
        { view: 'temporal' as const, icon: ChartNoAxesCombined },
      ],
    },
    {
      title: 'nav.research' as const,
      items: [
        { view: 'learning' as const, icon: Tags },
        { view: 'arena' as const, icon: FlaskConical },
        { view: 'evaluation' as const, icon: ScanLine },
      ],
    },
  ];

  /**
   * Views load on demand.
   *
   * Only the overview is in the initial graph. The map view pulls in Leaflet
   * (~146 KB) and the raster reader (~233 KB chunk of geotiff), the learning view
   * pulls the raster reader, and no page needs the others; importing all six
   * eagerly made every first paint pay for the heaviest screen.
   */
  const loaders: Record<Exclude<ViewId, 'overview' | 'intake'>, () => Promise<{ default: Component }>> = {
    map: () => import('./pages/Geospatial.svelte'),
    temporal: () => import('./pages/Temporal.svelte'),
    learning: () => import('./pages/Learning.svelte'),
    arena: () => import('./pages/Arena.svelte'),
    evaluation: () => import('./pages/Evaluation.svelte'),
  };

  const loaded = new globalThis.Map<ViewId, Component>();
  let PageView = $state<Component | null>(null);
  let pageError = $state<string | null>(null);

  /**
   * Load the component for the active view. `workspace.view` is also changed by
   * the hash listener, so this is driven by an effect rather than by `setView`.
   */
  $effect(() => {
    const view = workspace.view;
    pageError = null;
    const cached = loaded.get(view);
    if (cached) {
      PageView = cached;
      return;
    }
    if (view === 'overview' || view === 'intake') {
      const component = view === 'overview' ? Overview : Intake;
      loaded.set(view, component);
      PageView = component;
      return;
    }
    let active = true;
    PageView = null;
    loaders[view]()
      .then((module) => {
        if (!active) return;
        loaded.set(view, module.default);
        PageView = module.default;
      })
      .catch((error: unknown) => {
        if (!active) return;
        pageError = error instanceof Error ? error.message : String(error);
      });
    return () => {
      active = false;
    };
  });

  let ready = $state(false);
  let collapsed = $state(false);
  let mobileOpen = $state(false);
  let popover = $state<'project' | 'dataset' | 'notifications' | null>(null);
  let unread = $state(true);
  let toastTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => {
    applyDocumentLocale(workspace.locale.current);
    workspace.view = viewFromHash(location.hash);
    try {
      if (localStorage.getItem('wbalc:collapsed') === 'true') collapsed = true;
    } catch {
      /* Storage is optional. */
    }
    void workspace.boot().then(() => {
      if (workspace.dataset && workspace.view === 'map') void workspace.loadMapField();
    });
    ready = true;
    return () => clearTimeout(toastTimer);
  });

  $effect(() => {
    if (!ready) return;
    try {
      localStorage.setItem('wbalc:collapsed', String(collapsed));
    } catch {
      /* Optional persistence. */
    }
  });

  $effect(() => {
    document.title = `WBALC | ${t(views[workspace.view])}`;
  });

  // Toast auto-dismiss (also clears when a new message arrives).
  $effect(() => {
    const message = workspace.toast;
    if (!message) return;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      workspace.toast = '';
    }, 4600);
  });

  function setView(view: ViewId) {
    if (workspace.view !== view) window.scrollTo({ top: 0 });
    workspace.view = view;
    popover = null;
    mobileOpen = false;
    if (location.hash !== `#/${view}`) history.replaceState(null, '', `#/${view}`);
    // The map needs a prediction field; fetch it lazily when the view opens.
    if (view === 'map' && workspace.latestRun && workspace.dataset) void workspace.loadMapField();
  }

  function togglePopover(menu: typeof popover) {
    popover = popover === menu ? null : menu;
  }

  function collapse() {
    if (matchMedia('(max-width: 760px)').matches) mobileOpen = false;
    else collapsed = !collapsed;
  }
</script>

<svelte:window
  onhashchange={() => {
    const view = viewFromHash(location.hash);
    if (workspace.view !== view) {
      workspace.view = view;
      // Mirror setView: the map needs its prediction field when opened via the
      // browser history as well as through the sidebar links.
      if (view === 'map' && workspace.latestRun && workspace.dataset) void workspace.loadMapField();
    }
  }}
  onkeydown={(event) => {
    if (event.key === 'Escape') {
      popover = null;
      mobileOpen = false;
    }
  }}
  onclick={(event) => {
    if (!event.composedPath().some((node) => node instanceof Element && node.hasAttribute('data-popover')))
      popover = null;
  }}
/>

<a
  class="skip-link"
  href="#workspace-main"
  onclick={(event) => {
    event.preventDefault();
    document.getElementById('workspace-main')?.focus();
  }}>{t('app.skip')}</a
>

<div class:collapsed class:mobile-open={mobileOpen} class="workspace-shell">
  {#if mobileOpen}
    <button
      class="nav-backdrop"
      aria-label={t('nav.close')}
      onclick={() => {
        mobileOpen = false;
      }}></button>
  {/if}

  <aside class="sidebar" aria-label={t('nav.workspace')} id="site-sidebar">
    <a
      href="#/overview"
      class="brand"
      title="WBALC"
      onclick={() => setView('overview')}
    >
      <img src="/wbalc.svg" width="34" height="34" alt="" />
      <span class="brand-copy"><strong>WBALC</strong><small>{t('app.tagline')}</small></span>
    </a>

    <nav aria-label={t('app.workspaceContext')} class="sidebar-nav">
      {#each nav as section (section.title)}
        <div class="nav-group">
          <p class="nav-title">{t(section.title)}</p>
          {#each section.items as item (item.view)}
            <a
              class="nav-link"
              class:active={workspace.view === item.view}
              title={t(views[item.view])}
              href={`#/${item.view}`}
              aria-current={workspace.view === item.view ? 'page' : undefined}
              onclick={(event) => {
                if (!(event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)) {
                  event.preventDefault();
                  setView(item.view);
                }
              }}
            >
              <item.icon size={17} strokeWidth={1.7} />
              <span class="nav-label">{t(views[item.view])}</span>
              {#if item.view === 'learning' && workspace.pendingCount > 0}
                <span class="nav-count" aria-label={t('nav.pending', { count: workspace.pendingCount })}
                  >{workspace.pendingCount}</span
                >
              {/if}
            </a>
          {/each}
        </div>
      {/each}
    </nav>

    <div class="sidebar-bottom">
      <div class="local-status" title={t('app.footer.note')}>
        <div class="local-status-title">
          <span class="status-dot" class:offline={!workspace.project}></span>
          <strong>{workspace.project ? 'RSAL engine' : t('error.title')}</strong>
        </div>
        <span class="local-status-sub">
          {workspace.project ? t('app.footer.source') : t('error.body')}
        </span>
      </div>
      <LocaleSwitch />
      <button
        class="collapse-button"
        onclick={collapse}
        title={collapsed ? t('nav.expand') : t('nav.collapse')}
        aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
      >
        {#if collapsed}<PanelLeftOpen size={17} strokeWidth={1.7} />{:else}<PanelLeftClose size={17} strokeWidth={1.7} />{/if}
        <span class="collapse-text">{t('nav.collapse')}</span>
        <span class="close-nav-text">{t('nav.close')}</span>
      </button>
    </div>
  </aside>

  <div class="workspace-body">
    <header class="topbar">
      <div class="topbar-start">
        <button
          class="icon-button mobile-menu"
          onclick={() => {
            mobileOpen = !mobileOpen;
          }}
          aria-label={t('nav.open')}
          aria-expanded={mobileOpen}
          aria-controls="site-sidebar"><Menu size={21} /></button
        >

        <div class="toolbar-slot" data-popover>
          <button
            class="toolbar-button project-button"
            aria-label={t('project.select')}
            aria-expanded={popover === 'project'}
            onclick={() => togglePopover('project')}
          >
            <MapPin size={17} class="accent" />
            <span>{workspace.project?.name ?? t('project.none')}</span>
            <ChevronDown size={14} class="toolbar-chevron" />
          </button>
          {#if popover === 'project'}
            <div class="popover project-popover">
              <p class="popover-heading">{t('project.projects')}</p>
              {#each workspace.projects as project (project.id)}
                <button
                  class="popover-row"
                  class:chosen={workspace.project?.id === project.id}
                  onclick={() => {
                    void workspace.selectProject(project.id).then(() => {
                      popover = null;
                    });
                  }}
                >
                  <MapPin size={16} class="accent" />
                  <span>
                    <strong>{project.name}</strong>
                    <small>#{project.id} · {t('project.status')}: {project.status}</small>
                  </span>
                  {#if workspace.project?.id === project.id}<Check size={15} class="accent" />{/if}
                </button>
              {:else}
                <p class="popover-note">{t('error.noProjects')}</p>
              {/each}
              <button class="popover-row" onclick={() => { popover = null; setView('intake'); }}>
                <FolderPlus size={16} class="accent" />{t('intake.create')}
              </button>
            </div>
          {/if}
        </div>

        <span class="toolbar-divider project-divider"></span>
        <span class="toolbar-context">{t('app.workspaceContext')}</span>
      </div>

      <div class="topbar-end">
        <div class="toolbar-slot" data-popover>
          <button
            class="toolbar-button"
            aria-label={t('map.dataset')}
            aria-expanded={popover === 'dataset'}
            onclick={() => togglePopover('dataset')}
            disabled={!workspace.datasets.length}
          >
            <Database size={16} />
            <span class="dataset-label">{workspace.dataset?.name ?? t('map.noDataset')}</span>
            <ChevronDown size={14} class="toolbar-chevron" />
          </button>
          {#if popover === 'dataset'}
            <div class="popover end-popover">
              <p class="popover-heading">{t('map.dataset')}</p>
              <div class="popover-scroll">
                {#each [...workspace.datasets].reverse() as dataset (dataset.id)}
                  <button
                    class="popover-row"
                    class:chosen={workspace.dataset?.id === dataset.id}
                    onclick={() => {
                      workspace.selectDataset(dataset.id);
                      popover = null;
                      if (workspace.latestRun) void workspace.loadMapField();
                    }}
                  >
                    <span>
                      <strong>{dataset.name}</strong>
                      <small class="ltr-numeric">{dataset.width}×{dataset.height} · {dataset.bands} bands</small>
                    </span>
                    {#if workspace.dataset?.id === dataset.id}<Check size={15} class="accent" />{/if}
                  </button>
                {/each}
              </div>
            </div>
          {/if}
        </div>

        <div class="toolbar-slot" data-popover>
          <button
            class="icon-button bell-button"
            aria-label={t('overview.activity')}
            aria-expanded={popover === 'notifications'}
            onclick={() => {
              unread = false;
              togglePopover('notifications');
            }}
          >
            <Bell size={18} strokeWidth={1.8} />{#if unread}<span class="notification-dot"></span>{/if}
          </button>
          {#if popover === 'notifications'}
            <div class="popover end-popover notification-popover">
              <div class="popover-heading">{t('overview.status')}</div>
              <button class="popover-row" onclick={() => setView('map')}>
                <CircleCheck size={17} class="accent" />
                <span>
                  <strong>{t('overview.datasets')}: {workspace.datasets.length}</strong>
                  <small>{t('overview.scenes')}: {workspace.scenes.length}</small>
                </span>
                <ChevronRight size={14} />
              </button>
              <button class="popover-row" onclick={() => setView('learning')}>
                <Tags size={17} />
                <span>
                  <strong>{t('overview.labels')}: {workspace.labels.length}</strong>
                  <small>{t('learning.progress', {
                    done: workspace.labels.length,
                    total: Math.max(workspace.labels.length, workspace.labels.length + workspace.pendingCount),
                  })}</small>
                </span>
                <ChevronRight size={14} />
              </button>
              <button class="popover-row" onclick={() => setView('arena')}>
                <FlaskConical size={17} />
                <span>
                  <strong>{t('overview.runs')}: {workspace.runs.length}</strong>
                  <small>{t('arena.comparisonHint')}</small>
                </span>
                <ChevronRight size={14} />
              </button>
            </div>
          {/if}
        </div>

        <span class="toolbar-divider profile-divider"></span>
        <button
          class="icon-button"
          title={t('common.refresh')}
          aria-label={t('common.refresh')}
          disabled={workspace.loading || workspace.detailLoading}
          onclick={() => {
            void workspace.reload().then(() => {
              workspace.notify(t('common.refresh'));
            });
          }}
        >
          <RefreshCw size={16} class={workspace.loading || workspace.detailLoading ? 'spin' : ''} />
        </button>
        <div class="toolbar-slot locale-slot"><LocaleSwitch /></div>
      </div>
    </header>

    <main class="page-content" id="workspace-main" tabindex="-1">
      {#if workspace.error}
        <div class="connection-error">
          <TriangleAlert size={22} />
          <div>
            <strong>{t('error.title')}</strong>
            <p>{workspace.error.message}</p>
            <p class="hint">{t('error.body')}</p>
          </div>
          <button
            class="button primary"
            onclick={() => {
              workspace.error = null;
              void workspace.boot();
            }}>{t('error.retry')}</button
          >
        </div>
      {:else if workspace.loading}
        <div class="boot-state"><span class="spinner"></span>{t('common.loading')}</div>
      {:else if !workspace.projects.length || workspace.view === 'intake'}
        <Intake />
      {:else}
        {#key workspace.view}
          <div class="page-view">
            {#if pageError}
              <div class="surface">
                <EmptyState title={t('error.generic')} hint={pageError} />
              </div>
            {:else if PageView}
              <PageView />
            {:else}
              <div class="boot-state"><span class="spinner"></span>{t('common.loading')}</div>
            {/if}
          </div>
        {/key}
      {/if}
      <footer class="data-footer">
        <Database size={13} />
        <strong>{t('app.footer.source')}</strong>
        <span>{t('app.footer.note')}</span>
      </footer>
    </main>
  </div>
</div>

<div class="toast-region" aria-live="polite">
  {#if workspace.toast}
    <div class="toast">
      <CircleCheck size={18} class="accent" />
      <span>{workspace.toast}</span>
      <button
        class="icon-button"
        title={t('common.dismiss')}
        aria-label={t('common.dismiss')}
        onclick={() => {
          workspace.toast = '';
        }}><X size={16} /></button
      >
    </div>
  {/if}
</div>

<style>
  .connection-error { display: flex; gap: 14px; align-items: flex-start; padding: 18px; border: 1px solid var(--control-border); border-radius: 8px; background: var(--control-bg); color: var(--danger-fg); }
  .connection-error strong { color: var(--danger-fg); font-size: 14px; }
  .connection-error p { margin: 4px 0 0; font-size: 12px; line-height: 1.6; }
  .connection-error .hint { color: var(--danger-fg); }
  .connection-error .button { margin-inline-start: auto; }
  .boot-state { display: flex; align-items: center; gap: 9px; justify-content: center; min-height: 220px; color: var(--muted); font-size: 12.5px; }
  .spinner { width: 15px; height: 15px; border-radius: 50%; border: 2px solid var(--control-border); border-top-color: var(--accent); animation: spin 700ms linear infinite; }
  .status-dot.offline { background: var(--warn); box-shadow: 0 0 0 3px #f3be6717; }
  .locale-slot { display: none; }
  .dataset-label { max-width: 148px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  :global(.spin) { animation: spin 900ms linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 1010px) {
    .locale-slot { display: block; }
  }
  @media (max-width: 700px) {
    .dataset-label { max-width: 92px; }
    .connection-error { flex-direction: column; }
    .connection-error .button { margin-inline-start: 0; }
  }
</style>
