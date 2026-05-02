/**
 * Wraps @meteora-ag/dlmm just enough to open a position + add liquidity from
 * the browser. The SDK + its @coral-xyz/anchor transitive dep have CJS-style
 * directory imports that Node's ESM resolver rejects during SSR, so we lazy-
 * load via dynamic import() — keeps the SDK out of the SSR import graph.
 */

import type {
  Keypair as KeypairT,
  PublicKey,
  Transaction,
} from '@solana/web3.js';
import type BN from 'bn.js';
import { DEVNET_POOL, getConnection } from './devnet';

export type PoolSnapshot = {
  activeBin: number;
  binStep: number;
  tokenXMint: string;
  tokenYMint: string;
  tokenXDecimals: number;
  tokenYDecimals: number;
  tokenXSymbol: string;
  tokenYSymbol: string;
};

// Cached at module scope so we only load the SDK + initialize once per session.
let _dlmmInstance: unknown = null;

async function getDlmm(): Promise<{
  dlmm: unknown;
  StrategyType: { Spot: number; Curve: number; BidAsk: number };
}> {
  // dynamic import — never resolved during SSR
  const mod = await import('@meteora-ag/dlmm');
  // ESM/CJS interop: the default export is the DLMM class
  const DLMM = (mod as { default: unknown }).default ?? mod;
  if (!_dlmmInstance) {
    const connection = getConnection();
    // @ts-expect-error — DLMM is loaded dynamically; cast at call site
    _dlmmInstance = await DLMM.create(connection, DEVNET_POOL);
  }
  return {
    dlmm: _dlmmInstance,
    StrategyType: (mod as unknown as { StrategyType: { Spot: number; Curve: number; BidAsk: number } }).StrategyType,
  };
}

export async function fetchPoolSnapshot(): Promise<PoolSnapshot> {
  const { dlmm } = await getDlmm();
  // @ts-expect-error — dynamic types
  const active = await dlmm.getActiveBin();
  // @ts-expect-error
  const tx = dlmm.tokenX;
  // @ts-expect-error
  const ty = dlmm.tokenY;
  // @ts-expect-error
  const lbPair = dlmm.lbPair;
  return {
    activeBin: active.binId,
    binStep: lbPair.binStep,
    tokenXMint: tx.publicKey.toString(),
    tokenYMint: ty.publicKey.toString(),
    tokenXDecimals: tx.mint.decimals,
    tokenYDecimals: ty.mint.decimals,
    tokenXSymbol: 'SOL',
    tokenYSymbol: 'USDC',
  };
}

function strategyEnumFor(
  StrategyType: { Spot: number; Curve: number; BidAsk: number },
  distribution: string,
): number {
  switch (distribution) {
    case 'curve':
      return StrategyType.Curve;
    case 'bid_ask':
      return StrategyType.BidAsk;
    case 'spot':
    default:
      return StrategyType.Spot;
  }
}

/**
 * Build a tx that creates a new position NFT + deposits liquidity into the
 * given bin range using the given distribution shape. Returns the tx + the
 * fresh position keypair (caller adds it as a partial signer).
 */
export async function buildOpenAndAddLiquidityTx(args: {
  user: PublicKey;
  lowerBin: number;
  upperBin: number;
  distribution: string;
  amountX: BN; // raw token units
  amountY: BN;
}): Promise<{ tx: Transaction; positionKeypair: KeypairT }> {
  const { dlmm, StrategyType } = await getDlmm();
  // Lazy-load Keypair too so we don't have to import @solana/web3.js as a
  // value at module scope (it's lighter than DLMM but consistency is nice).
  const { Keypair } = await import('@solana/web3.js');
  const positionKeypair = Keypair.generate();
  const strategy = strategyEnumFor(StrategyType, args.distribution);

  // @ts-expect-error — dynamic types
  const tx: Transaction = await dlmm.initializePositionAndAddLiquidityByStrategy({
    positionPubKey: positionKeypair.publicKey,
    user: args.user,
    totalXAmount: args.amountX,
    totalYAmount: args.amountY,
    strategy: {
      maxBinId: args.upperBin,
      minBinId: args.lowerBin,
      strategyType: strategy,
    },
  });

  return { tx, positionKeypair };
}
