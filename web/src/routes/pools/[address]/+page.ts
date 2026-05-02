import { api, type Bar, type PoolDetail } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
  const [detail, bars] = await Promise.all([
    api<PoolDetail>(`/pools/${params.address}`, fetch),
    api<Bar[]>(`/pools/${params.address}/bars`, fetch),
  ]);
  return { detail, bars };
};
