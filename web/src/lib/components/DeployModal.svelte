<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import BN from 'bn.js';
  import { LAMPORTS_PER_SOL, PublicKey } from '@solana/web3.js';
  import { X, Wallet, Play, CheckCircle2, AlertTriangle, ExternalLink } from 'lucide-svelte';
  import { apiPost } from '$lib/api/client';
  import { connectPhantom, getPhantom } from '$lib/solana/phantom';
  import { getConnection, explorerTxUrl, DEVNET_POOL } from '$lib/solana/devnet';
  import {
    buildOpenAndAddLiquidityTx,
    fetchPoolSnapshot,
    type PoolSnapshot,
  } from '$lib/solana/meteora';

  export let trial: string;
  export let iteration: number;
  export let strategySummary: string = ''; // short label shown in the header

  const dispatch = createEventDispatcher();

  type Step = 'connect' | 'amounts' | 'preview' | 'signing' | 'done' | 'error';
  let step: Step = 'connect';
  let err: string | null = null;

  let publicKey: PublicKey | null = null;
  let solBalance = 0; // human SOL
  let snapshot: PoolSnapshot | null = null;

  // Amount inputs (human units — converted to raw on submit)
  let amountX = '0.05'; // SOL
  let amountY = '0';    // USDC

  // Resolved deploy parameters
  let lowerBin: number | null = null;
  let upperBin: number | null = null;
  let distribution: string | null = null;

  let txSig: string | null = null;

  onMount(async () => {
    // Auto-attempt silent reconnect if Phantom remembers us.
    const p = getPhantom();
    if (p?.isConnected && p.publicKey) {
      publicKey = p.publicKey;
      await afterConnect();
    }
  });

  async function connect() {
    err = null;
    try {
      publicKey = await connectPhantom();
      await afterConnect();
    } catch (e) {
      err = String(e);
      step = 'error';
    }
  }

  async function afterConnect() {
    if (!publicKey) return;
    const connection = getConnection();
    const lamports = await connection.getBalance(publicKey);
    solBalance = lamports / LAMPORTS_PER_SOL;
    snapshot = await fetchPoolSnapshot();
    step = 'amounts';
  }

  async function preview() {
    err = null;
    if (!snapshot) {
      err = 'pool snapshot missing — try reopening the modal';
      step = 'error';
      return;
    }
    const xRaw = Math.floor(parseFloat(amountX || '0') * 10 ** snapshot.tokenXDecimals);
    const yRaw = Math.floor(parseFloat(amountY || '0') * 10 ** snapshot.tokenYDecimals);
    if (xRaw <= 0 && yRaw <= 0) {
      err = 'enter a non-zero amount on at least one side';
      return;
    }
    try {
      const resp = await apiPost<{
        action_type: string;
        lower_bin: number | null;
        upper_bin: number | null;
        distribution: string | null;
        error: string | null;
      }>(`/trials/${trial}/iterations/${iteration}/build-action`, {
        active_bin: snapshot.activeBin,
        bin_step: snapshot.binStep,
        initial_x: xRaw,
        initial_y: yRaw,
        decimals_x: snapshot.tokenXDecimals,
        decimals_y: snapshot.tokenYDecimals,
      });
      if (resp.action_type !== 'open_position' || resp.lower_bin === null) {
        err = resp.error ?? 'strategy did not produce an OpenPosition';
        step = 'error';
        return;
      }
      lowerBin = resp.lower_bin;
      upperBin = resp.upper_bin;
      distribution = resp.distribution;
      step = 'preview';
    } catch (e) {
      err = String(e);
      step = 'error';
    }
  }

  async function signAndSubmit() {
    if (!publicKey || !snapshot || lowerBin === null || upperBin === null || !distribution) return;
    err = null;
    step = 'signing';
    try {
      const xRaw = new BN(Math.floor(parseFloat(amountX || '0') * 10 ** snapshot.tokenXDecimals));
      const yRaw = new BN(Math.floor(parseFloat(amountY || '0') * 10 ** snapshot.tokenYDecimals));
      const { tx, positionKeypair } = await buildOpenAndAddLiquidityTx({
        user: publicKey,
        lowerBin,
        upperBin,
        distribution,
        amountX: xRaw,
        amountY: yRaw,
      });

      const connection = getConnection();
      const { blockhash } = await connection.getLatestBlockhash('confirmed');
      tx.recentBlockhash = blockhash;
      tx.feePayer = publicKey;
      tx.partialSign(positionKeypair);

      const phantom = getPhantom();
      if (!phantom) throw new Error('Phantom disappeared mid-flight');
      const signed = await phantom.signTransaction(tx);

      const sig = await connection.sendRawTransaction(signed.serialize(), {
        skipPreflight: false,
      });
      await connection.confirmTransaction({ signature: sig, blockhash, lastValidBlockHeight: (await connection.getLatestBlockhash('confirmed')).lastValidBlockHeight }, 'confirmed');

      txSig = sig;
      step = 'done';
    } catch (e) {
      err = String(e);
      step = 'error';
    }
  }

  function close() {
    dispatch('close');
  }
</script>

<div
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
  role="presentation"
  on:click|self={close}
  on:keydown={(e) => e.key === 'Escape' && close()}
>
  <div class="w-full max-w-md rounded-lg border border-bg-muted bg-bg-surface p-5"
       role="dialog" aria-modal="true">
    <header class="mb-3 flex items-center justify-between">
      <div>
        <h3 class="font-medium">Deploy live (devnet)</h3>
        <p class="mt-0.5 text-xs text-fg-muted">
          Trial <span class="font-mono">{trial}</span> · iter {iteration}
          {#if strategySummary}<span class="text-fg-dim"> · {strategySummary}</span>{/if}
        </p>
      </div>
      <button on:click={close} class="text-fg-muted hover:text-fg"><X size={16} /></button>
    </header>

    {#if step === 'connect'}
      <div class="space-y-3">
        <div class="rounded border border-bg-muted bg-bg p-3 text-xs text-fg-muted">
          Connect your Phantom wallet to continue. The transaction will land on
          <span class="font-mono">devnet</span> against pool
          <span class="font-mono">{DEVNET_POOL.toBase58().slice(0, 8)}…</span>
          (SOL/USDC, bin_step=10).
        </div>
        <button on:click={connect}
          class="flex w-full items-center justify-center gap-2 rounded bg-accent px-3 py-2 text-sm font-medium text-bg hover:bg-accent/90">
          <Wallet size={14} /> Connect Phantom
        </button>
      </div>
    {/if}

    {#if step === 'amounts' && snapshot}
      <div class="space-y-3 text-sm">
        <div class="rounded border border-bg-muted bg-bg p-3 text-xs">
          <div class="flex justify-between">
            <span class="text-fg-muted">Wallet</span>
            <span class="font-mono">{publicKey?.toBase58().slice(0, 4)}…{publicKey?.toBase58().slice(-4)}</span>
          </div>
          <div class="mt-1 flex justify-between">
            <span class="text-fg-muted">Balance</span>
            <span class="font-mono">{solBalance.toFixed(4)} SOL</span>
          </div>
          <div class="mt-1 flex justify-between">
            <span class="text-fg-muted">Pool active bin</span>
            <span class="font-mono">{snapshot.activeBin}</span>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-xs text-fg-muted">{snapshot.tokenXSymbol}</span>
            <input type="text" bind:value={amountX}
              class="mt-1 w-full rounded border border-bg-muted bg-bg px-2 py-1.5 font-mono text-sm" />
          </label>
          <label class="block">
            <span class="text-xs text-fg-muted">{snapshot.tokenYSymbol}</span>
            <input type="text" bind:value={amountY}
              class="mt-1 w-full rounded border border-bg-muted bg-bg px-2 py-1.5 font-mono text-sm" />
          </label>
        </div>

        <p class="text-xs text-fg-dim">
          Devnet USDC may not be in your wallet. If you only have SOL, leave USDC at 0 —
          the strategy's distribution will deposit X-only above the active bin.
        </p>

        {#if err}
          <p class="rounded border border-rose-500/40 bg-rose-500/5 p-2 text-xs text-rose-300">{err}</p>
        {/if}

        <div class="flex justify-end gap-2">
          <button on:click={close} class="rounded px-3 py-1.5 text-xs text-fg-muted hover:text-fg">Cancel</button>
          <button on:click={preview}
            class="rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg hover:bg-accent/90">
            Preview position →
          </button>
        </div>
      </div>
    {/if}

    {#if step === 'preview' && snapshot && lowerBin !== null && upperBin !== null}
      <div class="space-y-3 text-sm">
        <div class="rounded border border-bg-muted bg-bg p-3 text-xs">
          <div class="mb-2 text-fg-muted">Strategy will open:</div>
          <div class="space-y-1 font-mono">
            <div>bins [{lowerBin}, {upperBin}] (width {upperBin - lowerBin + 1})</div>
            <div>distribution: {distribution}</div>
            <div>active bin: {snapshot.activeBin}</div>
            <div>deposit: {amountX} {snapshot.tokenXSymbol} + {amountY} {snapshot.tokenYSymbol}</div>
          </div>
        </div>

        <p class="text-xs text-fg-dim">
          Phantom will pop up to sign. Position NFT is created in the same tx.
        </p>

        <div class="flex justify-end gap-2">
          <button on:click={() => (step = 'amounts')} class="rounded px-3 py-1.5 text-xs text-fg-muted hover:text-fg">
            ← Back
          </button>
          <button on:click={signAndSubmit}
            class="flex items-center gap-1.5 rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg hover:bg-accent/90">
            <Play size={12} /> Sign + Submit
          </button>
        </div>
      </div>
    {/if}

    {#if step === 'signing'}
      <div class="space-y-3 text-sm">
        <div class="rounded border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-200">
          Awaiting signature in Phantom… (don't close this dialog)
        </div>
      </div>
    {/if}

    {#if step === 'done' && txSig}
      <div class="space-y-3 text-sm">
        <div class="rounded border border-emerald-500/40 bg-emerald-500/5 p-3 text-xs text-emerald-200">
          <div class="flex items-center gap-1.5 font-medium">
            <CheckCircle2 size={14} /> Landed on devnet
          </div>
          <a href={explorerTxUrl(txSig)} target="_blank" rel="noopener noreferrer"
             class="mt-2 flex items-center gap-1 break-all font-mono text-emerald-300 hover:underline">
            <ExternalLink size={10} /> {txSig.slice(0, 32)}…
          </a>
        </div>
        <div class="flex justify-end">
          <button on:click={close} class="rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg hover:bg-accent/90">
            Done
          </button>
        </div>
      </div>
    {/if}

    {#if step === 'error'}
      <div class="space-y-3 text-sm">
        <div class="rounded border border-rose-500/40 bg-rose-500/5 p-3 text-xs text-rose-300">
          <div class="mb-1 flex items-center gap-1.5 font-medium">
            <AlertTriangle size={12} /> Failed
          </div>
          <pre class="max-h-48 overflow-auto whitespace-pre-wrap break-all">{err}</pre>
        </div>
        <div class="flex justify-end gap-2">
          <button on:click={() => (step = publicKey ? 'amounts' : 'connect')}
            class="rounded px-3 py-1.5 text-xs text-fg-muted hover:text-fg">
            Try again
          </button>
          <button on:click={close} class="rounded bg-accent px-3 py-1.5 text-xs font-medium text-bg hover:bg-accent/90">
            Close
          </button>
        </div>
      </div>
    {/if}
  </div>
</div>
