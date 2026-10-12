import { api } from './client';
import type {
  BriefingResponse,
  BriefingSummaryResponse,
  BriefingAckResponse,
} from '../types/briefing';

export const briefingApi = {
  getBriefing: () => api.get<BriefingResponse>('/api/briefing'),
  getSummary: () => api.post<BriefingSummaryResponse>('/api/briefing/summary', {}),
  ackBriefing: () => api.post<BriefingAckResponse>('/api/briefing/ack', {}),
};
