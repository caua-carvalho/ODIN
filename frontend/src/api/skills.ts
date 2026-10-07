import { api } from './client';
import type { Skill } from '../types/skill';

export const skillsApi = {
  getSkills: () => api.get<Skill[]>('/api/skills'),
};