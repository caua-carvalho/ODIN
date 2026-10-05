import { OdinService } from './odinService';
import { mockOdinService } from '../mock/mockOdinService';
import { ApiOdinService } from './apiOdinService';

// Detect whether to use real backend API or mock
const isProductionOrApiConfigured = false; // By default MVP uses robust in-memory mock service

export const odinService: OdinService = isProductionOrApiConfigured
  ? new ApiOdinService()
  : mockOdinService;

export * from './odinService';
export * from './apiOdinService';
export * from '../mock/mockOdinService';
