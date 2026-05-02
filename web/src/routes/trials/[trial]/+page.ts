import { api, type TrialDetail } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
  const trial = await api<TrialDetail>(`/trials/${params.trial}`, fetch);
  return { trial };
};
