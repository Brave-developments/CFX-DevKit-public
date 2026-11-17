<script lang="ts">
  import { onMount } from 'svelte';
  let visible = $state(false);
  onMount(() => { const handler = (e: MessageEvent) => { if (e.data?.action === 'visibility') visible = Boolean(e.data.visible); }; window.addEventListener('message', handler); return () => window.removeEventListener('message', handler); });
  async function close() { const getName = (window as any).GetParentResourceName; if (!getName) { visible = false; return; } try { await fetch('https://' + getName() + '/close', { method:'POST', headers: { 'Content-Type': 'application/json' }, body:'{}' }); } catch(e) { console.warn(e); } }
</script>
{#if visible}<main><h1>CFX Svelte NUI</h1><button onclick={close}>Close</button></main>{/if}
<style>main{background:#1b1d29;color:white;padding:24px;position:absolute;top:25%;left:30%;border-radius:16px}</style>
