/**
 * Minimal Phantom wallet wrapper. We talk to `window.solana` directly rather
 * than pulling in @solana/wallet-adapter-* — the demo only supports Phantom
 * and the wallet-adapter-svelte ecosystem is less mature than the React one.
 */

import type { PublicKey, Transaction, VersionedTransaction } from '@solana/web3.js';

interface PhantomProvider {
  isPhantom?: boolean;
  publicKey: PublicKey | null;
  isConnected: boolean;
  connect: (opts?: { onlyIfTrusted?: boolean }) => Promise<{ publicKey: PublicKey }>;
  disconnect: () => Promise<void>;
  signTransaction: <T extends Transaction | VersionedTransaction>(tx: T) => Promise<T>;
  signAllTransactions: <T extends Transaction | VersionedTransaction>(txs: T[]) => Promise<T[]>;
  on: (event: string, handler: (...args: unknown[]) => void) => void;
}

declare global {
  interface Window {
    solana?: PhantomProvider;
  }
}

export function getPhantom(): PhantomProvider | null {
  if (typeof window === 'undefined') return null;
  const provider = window.solana;
  return provider?.isPhantom ? provider : null;
}

export async function connectPhantom(): Promise<PublicKey> {
  const p = getPhantom();
  if (!p) throw new Error('Phantom wallet not detected. Install at https://phantom.app/');
  const { publicKey } = await p.connect();
  return publicKey;
}

export function isConnected(): boolean {
  return getPhantom()?.isConnected ?? false;
}
