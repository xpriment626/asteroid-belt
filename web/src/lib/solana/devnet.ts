import { Connection, PublicKey, clusterApiUrl } from '@solana/web3.js';

// Devnet Meteora DLMM pool we picked for the demo (SOL/USDC, bin_step=10, zero
// liquidity at time of writing — the first deposit lands visibly on explorer).
export const DEVNET_POOL = new PublicKey(
  '9EE5MLCRzk5gXa5ag7UjFvgDeuozZwpiKiCprEP4kVZf',
);

// Same Meteora DLMM program ID on mainnet + devnet.
export const DLMM_PROGRAM_ID = new PublicKey(
  'LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo',
);

export const DEVNET_RPC = clusterApiUrl('devnet');

export function getConnection(): Connection {
  return new Connection(DEVNET_RPC, 'confirmed');
}

export function explorerTxUrl(sig: string): string {
  return `https://explorer.solana.com/tx/${sig}?cluster=devnet`;
}

export function explorerAddrUrl(addr: string): string {
  return `https://explorer.solana.com/address/${addr}?cluster=devnet`;
}
