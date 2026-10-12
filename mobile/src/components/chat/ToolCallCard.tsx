import { Text, View, ActivityIndicator } from 'react-native';
import { Wrench, CheckCircle2, XCircle } from 'lucide-react-native';
import { cn } from '../../lib/utils';
import type { ToolExecutionData } from '../../hooks/useOdinSession';

function summarizeResult(result: Record<string, unknown> | undefined): string {
  if (!result || typeof result !== 'object') return '';
  const keys = Object.keys(result);
  if (keys.length === 0) return '{}';
  const sample = keys.slice(0, 4).map((k) => {
    const v = result[k];
    const text = typeof v === 'string' ? v : JSON.stringify(v);
    return `${k}: ${(text ?? '').slice(0, 80)}`;
  });
  return sample.join('\n');
}

export function ToolCallCard({ execution }: { execution: ToolExecutionData }) {
  const running = execution.status === 'running';
  return (
    <View
      className={cn(
        'rounded-xl border px-3 py-2.5 gap-1.5',
        running
          ? 'bg-surface-container border-line'
          : execution.status === 'success'
            ? 'bg-ok/5 border-ok/20'
            : 'bg-err/5 border-err/20'
      )}
    >
      <View className="flex-row items-center gap-2">
        {running ? (
          <ActivityIndicator size="small" color="#FF7A00" />
        ) : execution.status === 'success' ? (
          <CheckCircle2 size={16} color="#34d399" />
        ) : (
          <XCircle size={16} color="#f87171" />
        )}
        <Wrench size={14} color="#6E6E73" />
        <Text className="flex-1 font-mono text-xs text-primary font-medium">{execution.tool}</Text>
        <Text className="text-[10px] font-mono text-muted uppercase">
          {running ? 'executando' : execution.status === 'success' ? 'ok' : 'erro'}
        </Text>
      </View>

      {execution.arguments && Object.keys(execution.arguments).length > 0 ? (
        <Text className="font-mono text-[11px] text-muted" numberOfLines={3}>
          {JSON.stringify(execution.arguments).slice(0, 400)}
        </Text>
      ) : null}

      {!running && execution.result ? (
        <Text className="font-mono text-[11px] text-secondary" numberOfLines={4}>
          {summarizeResult(execution.result)}
        </Text>
      ) : null}
    </View>
  );
}