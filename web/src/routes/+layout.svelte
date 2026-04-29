<script lang="ts">
  import '../app.css';
  import { Activity, GitCompareArrows, Database, FlaskConical } from 'lucide-svelte';
  import { page } from '$app/stores';

  $: pathname = $page.url.pathname;

  const nav = [
    { href: '/',         label: 'Runs',     icon: Activity },
    { href: '/compare',  label: 'Compare',  icon: GitCompareArrows },
    { href: '/sessions', label: 'Sessions', icon: FlaskConical },
    { href: '/pools',    label: 'Pools',    icon: Database },
  ];
</script>

<div class="flex h-screen bg-bg text-fg">
  <aside class="w-52 shrink-0 border-r border-bg-muted bg-bg-surface p-4">
    <h1 class="mb-6 font-mono text-sm font-bold tracking-wider text-fg-muted">
      ASTEROID-BELT
    </h1>
    <nav class="flex flex-col gap-1">
      {#each nav as item}
        <a href={item.href}
           class="flex items-center gap-2 rounded px-2 py-1.5 text-sm transition-colors
                  {pathname === item.href || pathname.startsWith(item.href + '/')
                    ? 'bg-bg-muted text-fg'
                    : 'text-fg-muted hover:bg-bg-muted hover:text-fg'}">
          <svelte:component this={item.icon} size={14} />
          {item.label}
        </a>
      {/each}
    </nav>
  </aside>
  <main class="flex-1 overflow-y-auto p-6">
    <slot />
  </main>
</div>
