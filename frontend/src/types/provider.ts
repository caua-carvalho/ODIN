export interface ProviderModelInfo {
  id: string;
  label: string;
  description: string;
  configured: boolean;
  models: string[];
}

export interface ActiveSelection {
  provider: string;
  model: string;
}

export interface ProvidersResponse {
  providers: ProviderModelInfo[];
  active: ActiveSelection;
}