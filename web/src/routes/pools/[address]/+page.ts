import { api, type Bar, type PoolDetail } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ params }) => {
  const [detail, bars] = await Promise.all([
    api<PoolDetail>(`/pools/${params.address}`),
    api<Bar[]>(`/pools/${params.address}/bars`),
  ]);
  return { detail, bars };
};
