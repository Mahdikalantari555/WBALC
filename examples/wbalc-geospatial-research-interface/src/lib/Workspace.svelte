<script lang="ts">
  import { onMount } from 'svelte';
  import {
    Bell, CalendarDays, ChartNoAxesCombined, Check, ChevronDown, ChevronRight, CircleCheck,
    Database, FlaskConical, LayoutDashboard, Map, MapPin, Menu, PanelLeftClose, PanelLeftOpen,
    ScanLine, Tags, X,
  } from '@lucide/svelte';
  import { createState, pageFromHash, pages, provideWorkspace, type Page } from './state.svelte';
  import { fmtDate, getObservation, labelKeys, latest, observations, project, samples, seededReviews, sensorDetails, type Reviews } from './data/research';
  import Geospatial from './pages/Geospatial.svelte';
  import Overview from './pages/Overview.svelte';
  import Temporal from './pages/Temporal.svelte';
  import Learning from './pages/Learning.svelte';
  import Arena from './pages/Arena.svelte';
  import Evaluation from './pages/Evaluation.svelte';

  const nav = [
    { title: 'WORKSPACE', items: [{ page: 'overview', icon: LayoutDashboard }, { page: 'map', icon: Map }, { page: 'temporal', icon: ChartNoAxesCombined }] },
    { title: 'RESEARCH', items: [{ page: 'learning', icon: Tags }, { page: 'arena', icon: FlaskConical }, { page: 'evaluation', icon: ScanLine }] },
  ] as const;
  const views = { map: Geospatial, overview: Overview, temporal: Temporal, learning: Learning, arena: Arena, evaluation: Evaluation };
  const storageKey = 'wbalc:workspace:v1';

  const workspace = provideWorkspace(createState());
  let ready = $state(false);
  let collapsed = $state(false);
  let mobileOpen = $state(false);
  let popover = $state<'project' | 'date' | 'notifications' | 'profile' | null>(null);
  let unread = $state(true);
  let confirming = $state(false);
  let toast = $state('');
  let toastTimer: number | undefined;

  const View = $derived(views[workspace.page]);
  const pending = $derived(samples.filter(sample => !workspace.reviews[sample.id]).length);
  const current = $derived(getObservation(workspace.observation));

  onMount(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey) ?? '{}') as { collapsed?: boolean; reviews?: Reviews };
      if (typeof stored.collapsed === 'boolean') collapsed = stored.collapsed;
      for (const sample of samples) {
        const review = stored.reviews?.[sample.id];
        if (review && labelKeys.includes(review.label) && /^\d{4}-\d{2}-\d{2}$/.test(review.date)) workspace.reviews[sample.id] = review;
      }
    } catch { /* This prototype also works with browser storage disabled. */ }
    workspace.page = pageFromHash(location.hash);
    ready = true;
    return () => { window.clearTimeout(toastTimer); };
  });

  $effect(() => {
    if (!ready) return;
    const value = JSON.stringify({ collapsed, reviews: workspace.reviews });
    try { localStorage.setItem(storageKey, value); } catch { /* Optional persistence. */ }
  });

  $effect(() => { document.title = `WBALC | ${pages[workspace.page]}`; });

  function setPage(page: Page) {
    if (workspace.page !== page) window.scrollTo(0, 0);
    workspace.page = page;
    popover = null;
    mobileOpen = false;
  }

  function go(page: Page) {
    setPage(page);
    if (location.hash !== `#/${page}`) location.hash = `/${page}`;
  }

  function notify(message: string) {
    toast = message;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toast = ''; }, 4600);
  }

  function togglePopover(menu: typeof popover) {
    popover = popover === menu ? null : menu;
    confirming = false;
  }

  function collapse() {
    if (matchMedia('(max-width: 760px)').matches) mobileOpen = false;
    else collapsed = !collapsed;
  }

  function selectDate(date: string) {
    workspace.observation = date;
    if (workspace.sensor !== 'all' && workspace.sensor !== getObservation(date).sensor) workspace.sensor = 'all';
    popover = null;
  }
</script>

<svelte:window onhashchange={() => setPage(pageFromHash(location.hash))}
  onkeydown={(event) => { if (event.key === 'Escape') { popover = null; mobileOpen = false; } }}
  onclick={(event) => { if (!event.composedPath().some(node => node instanceof Element && node.hasAttribute('data-popover'))) popover = null; }} />

<a class="skip-link" href="#workspace-main" onclick={(event) => { event.preventDefault(); document.getElementById('workspace-main')?.focus(); }}>Skip to workspace</a>
<div class:collapsed class:mobile-open={mobileOpen} class="workspace-shell">
  {#if mobileOpen}<button class="nav-backdrop" aria-label="Close navigation" onclick={() => { mobileOpen = false; }}></button>{/if}
  <aside class="sidebar" aria-label="Application sidebar" id="site-sidebar">
    <a href="#/map" class="brand" title="WBALC Geospatial Workspace" onclick={() => go('map')}>
      <img src="/wbalc.svg" width="36" height="36" alt="" />
      <span class="brand-copy"><strong>WBALC</strong><small>Water Body Research</small></span>
    </a>

    <nav aria-label="Research navigation" class="sidebar-nav">
      {#each nav as section}
        <div class="nav-group">
          <p class="nav-title">{section.title}</p>
          {#each section.items as item}
            <a class="nav-link" class:active={workspace.page === item.page} title={pages[item.page]}
              href={`#/${item.page}`} aria-current={workspace.page === item.page ? 'page' : undefined}
              onclick={(event) => { if (!(event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)) { event.preventDefault(); go(item.page); } }}>
              <item.icon size={17} strokeWidth={1.7} />
              <span class="nav-label">{pages[item.page]}</span>
              {#if item.page === 'learning' && pending > 0}<span class="nav-count" aria-label={`${pending} pending`}>{pending}</span>{/if}
            </a>
          {/each}
        </div>
      {/each}
    </nav>

    <div class="sidebar-bottom">
      <div class="local-status" title="Local demo data. No live connections.">
        <div class="local-status-title"><span class="status-dot"></span><strong>Demo environment</strong></div>
        <span class="local-status-sub">Local data only</span>
      </div>
      <button class="collapse-button" onclick={collapse} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
        {#if collapsed}<PanelLeftOpen size={17} strokeWidth={1.7} />{:else}<PanelLeftClose size={17} strokeWidth={1.7} />{/if}
        <span class="collapse-text">Collapse sidebar</span><span class="close-nav-text">Close navigation</span>
      </button>
    </div>
  </aside>

  <div class="workspace-body">
    <header class="topbar">
      <div class="topbar-start">
        <button class="icon-button mobile-menu" onclick={() => { mobileOpen = !mobileOpen; }} aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="site-sidebar"><Menu size={21} /></button>
        <div class="toolbar-slot" data-popover>
          <button class="toolbar-button project-button" aria-label="Zarivar Lake, Iran: Select project" aria-expanded={popover === 'project'} onclick={() => togglePopover('project')}>
            <MapPin size={17} class="accent" /><span>Zarivar Lake<span class="project-country">, Iran</span></span><ChevronDown size={14} class="toolbar-chevron" />
          </button>
          {#if popover === 'project'}
            <div class="popover project-popover">
              <p class="popover-heading">RESEARCH PROJECTS</p>
              <button class="popover-row chosen" onclick={() => go('overview')}>
                <MapPin size={16} class="accent" /><span><strong>Zarivar Lake, Iran</strong><small>{project.id} / Water body monitoring</small></span><Check size={15} class="accent" />
              </button>
              <p class="popover-note">One study area is available in this demo.</p>
            </div>
          {/if}
        </div>
        <span class="toolbar-divider project-divider"></span>
        <span class="toolbar-context">Research workspace</span>
      </div>

      <div class="topbar-end">
        <div class="toolbar-slot" data-popover>
          <button class="toolbar-button observation-button" aria-label={`${fmtDate(current.date)}: Select observation date`} aria-expanded={popover === 'date'} onclick={() => togglePopover('date')}>
            <CalendarDays size={16} /><span>{fmtDate(current.date)}</span><ChevronDown size={14} class="toolbar-chevron" />
          </button>
          {#if popover === 'date'}
            <div class="popover end-popover date-popover">
              <p class="popover-heading">OBSERVATION DATE</p>
              <div class="popover-scroll">
                {#each [...observations].reverse() as item}
                  <button class="popover-row" class:chosen={current.date === item.date} onclick={() => selectDate(item.date)}>
                    <span><strong>{fmtDate(item.date)}</strong><small>{item.sensor}</small></span>
                    {#if current.date === item.date}<Check size={15} class="accent" />{/if}
                  </button>
                {/each}
              </div>
            </div>
          {/if}
        </div>

        <div class="toolbar-slot" data-popover>
          <button class="icon-button bell-button" aria-label="Notifications" aria-expanded={popover === 'notifications'} title="Notifications" onclick={() => togglePopover('notifications')}>
            <Bell size={18} strokeWidth={1.8} />{#if unread}<span class="notification-dot"></span>{/if}
          </button>
          {#if popover === 'notifications'}
            <div class="popover end-popover notification-popover">
              <div class="popover-heading flex justify-between items-center">NOTIFICATIONS {#if unread}<button class="text-button" onclick={() => { unread = false; }}>Mark as read</button>{/if}</div>
              <button class="popover-row" onclick={() => { unread = false; selectDate(latest.date); go('map'); }}><CircleCheck size={17} class="accent" /><span><strong>April classification available</strong><small>{fmtDate(latest.date)} / {sensorDetails[latest.sensor].product}</small></span><ChevronRight size={14} /></button>
              <button class="popover-row" onclick={() => { unread = false; go('learning'); }}><Tags size={17} /><span><strong>{pending ? `${pending} samples await review` : 'All samples reviewed'}</strong><small>Local active learning queue</small></span><ChevronRight size={14} /></button>
            </div>
          {/if}
        </div>

        <span class="toolbar-divider profile-divider"></span>
        <div class="toolbar-slot" data-popover>
          <button class="profile-button" aria-label="RS: Researcher profile" aria-expanded={popover === 'profile'} title="Researcher profile" onclick={() => togglePopover('profile')}><span class="avatar">RS</span><ChevronDown size={13} class="toolbar-chevron" /></button>
          {#if popover === 'profile'}
            <div class="popover end-popover profile-popover">
              <div class="popover-row profile-info"><span class="avatar">RS</span><span><strong>Researcher</strong><small>Local demo profile</small></span></div>
              <p class="popover-note">Labels are saved in this browser only.</p>
              <button class="popover-row reset-row" onclick={() => {
                if (!confirming) { confirming = true; return; }
                workspace.reviews = { ...seededReviews }; workspace.selectedSample = null; popover = null;
                notify('Demo reviews restored.');
              }}><span>{confirming ? 'Confirm reset of local labels' : 'Reset demo reviews'}</span></button>
            </div>
          {/if}
        </div>
      </div>
    </header>

    <main class="page-content" id="workspace-main" tabindex="-1">
      {#key workspace.page}
        <div class="page-view"><View {go} {notify} /></div>
      {/key}
      <footer class="data-footer"><Database size={13} /><strong>SIMULATED DATA</strong><span>Imagery and results are for demonstration only.</span></footer>
    </main>
  </div>
</div>

<div class="toast-region" aria-live="polite">
  {#if toast}
    <div class="toast"><CircleCheck size={18} class="accent" /><span>{toast}</span><button class="icon-button" title="Dismiss message" aria-label="Dismiss message" onclick={() => { toast = ''; }}><X size={16} /></button></div>
  {/if}
</div>