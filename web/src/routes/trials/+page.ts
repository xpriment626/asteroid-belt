import { api, type TrialSummary } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
  const trials = await api<TrialSummary[]>('/trials');
  return { trials };
};
