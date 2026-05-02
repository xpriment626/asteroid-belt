import { api, type TrialSummary } from '$lib/api/client';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
  const trials = await api<TrialSummary[]>('/trials', fetch);
  return { trials };
};
