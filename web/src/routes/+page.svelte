<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  onMount(() => goto('/trials'));
</script>

<p class="text-fg-muted">Redirecting to /trials...</p>
