import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
import { nodePolyfills } from 'vite-plugin-node-polyfills';

export default defineConfig({
  plugins: [
    sveltekit(),
    // Solana web3.js + Anchor + Meteora DLMM SDK assume Node's Buffer/process
    // globals exist in the browser. Polyfill them only on the client.
    nodePolyfills({
      include: ['buffer', 'process', 'crypto', 'stream', 'util'],
      globals: { Buffer: true, process: true, global: true },
      protocolImports: true,
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
