<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  onMount(() => goto('/pools'));
</script>

<p class="text-fg-muted">Redirecting to /pools...</p>
