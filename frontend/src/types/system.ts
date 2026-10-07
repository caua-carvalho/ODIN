export interface SystemInfo {
  cpu_percent: number;
  memory_total: number;
  memory_used: number;
  memory_percent: number;
  disk_total: number;
  disk_used: number;
  disk_percent: number;
  uptime_seconds: number;
  load_avg: number[];
}

export interface FormattedSystemInfo {
  cpu: {
    percent: number;
    label: string;
  };
  memory: {
    used: string;
    total: string;
    percent: number;
  };
  disk: {
    used: string;
    total: string;
    percent: number;
  };
  load: {
    avg1: number;
    avg5: number;
    avg15: number;
  };
  uptime: string;
}