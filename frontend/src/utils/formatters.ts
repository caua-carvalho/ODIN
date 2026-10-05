export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function formatDuration(ms?: number): string {
  if (ms === undefined || ms === null) return '—';
  if (ms < 1000) return `${ms}ms`;
  const seconds = (ms / 1000).toFixed(1);
  if (Number(seconds) < 60) return `${seconds}s`;
  const minutes = Math.floor(ms / 60000);
  const remainingSec = ((ms % 60000) / 1000).toFixed(0);
  return `${minutes}m ${remainingSec}s`;
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 5) return 'agora mesmo';
  if (diffInSeconds < 60) return `${diffInSeconds}s atrás`;
  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) return `${diffInMinutes}m atrás`;
  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) return `${diffInHours}h atrás`;
  const diffInDays = Math.floor(diffInHours / 24);
  return `${diffInDays}d atrás`;
}

export function formatTimePrecise(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat('pt-BR').format(num);
}
