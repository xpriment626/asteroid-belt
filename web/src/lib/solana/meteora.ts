/**
 * Wraps @meteora-ag/dlmm just enough to open a position + add liquidity from
 * the browser. For the demo we only target one pool (DEVNET_POOL).
 */

import DLMM, { StrategyType } from '@meteora-ag/dlmm';
import {
  Keypair,
  PublicKey,
  Transaction,
} from '@solana/web3.js';
import BN from 'bn.js';
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

let _dlmmInstance: DLMM | null = null;

async function getDlmm(): Promise<DLMM> {
  if (_dlmmInstance) return _dlmmInstance;
  const connection = getConnection();
  // SDK accepts (connection, poolPubkey, opts?). Cast the type because the
  // SDK's public d.ts is loose.
  _dlmmInstance = await DLMM.create(connection, DEVNET_POOL);
  return _dlmmInstance;
}

export async function fetchPoolSnapshot(): Promise<PoolSnapshot> {
  const d = await getDlmm();
  const active = await d.getActiveBin();
  // The SDK exposes mint pubkeys + decimals on `tokenX` / `tokenY` accessors.
  const tx = d.tokenX;
  const ty = d.tokenY;
  return {
    activeBin: active.binId,
    binStep: d.lbPair.binStep,
    tokenXMint: tx.publicKey.toString(),
    tokenYMint: ty.publicKey.toString(),
    tokenXDecimals: tx.mint.decimals,
    tokenYDecimals: ty.mint.decimals,
    tokenXSymbol: 'SOL',
    tokenYSymbol: 'USDC',
  };
}

function strategyTypeFor(distribution: string): StrategyType {
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
}): Promise<{ tx: Transaction; positionKeypair: Keypair }> {
  const d = await getDlmm();
  const positionKeypair = Keypair.generate();
  const strategy = strategyTypeFor(args.distribution);

  const tx = await d.initializePositionAndAddLiquidityByStrategy({
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
