import { useState } from 'react';
import { Text, View } from 'react-native';
import { ShieldAlert, Check, X } from 'lucide-react-native';
import { permissionsApi } from '../../api/permissions';
import { Button } from '../ui/Button';
import { RiskBadge } from '../ui/Badges';
import type { PermissionRequestEvent } from '../../types/websocket';

interface PermissionInlineProps {
  event: PermissionRequestEvent;
  /** Defined once the permission has been resolved (via WS or locally). */
  resolved?: boolean;
}

export function PermissionInline({ event, resolved }: PermissionInlineProps) {
  const [busy, setBusy] = useState(false);
  const [localResolved, setLocalResolved] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isResolved = resolved ?? localResolved;

  const act = async (approve: boolean) => {
    setBusy(true);
    setError(null);
    try {
      await (approve
        ? permissionsApi.approvePermission(event.id)
        : permissionsApi.denyPermission(event.id));
      setLocalResolved(approve);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View className="rounded-xl border border-accent/30 bg-accent/5 px-3 py-2.5 gap-2">
      <View className="flex-row items-center gap-2">
        <ShieldAlert size={16} color="#FF7A00" />
        <Text className="flex-1 font-mono text-xs text-accent font-medium">
          {event.tool} · {event.operation}
        </Text>
        <RiskBadge level={event.risk_level} />
      </View>

      <Text className="text-xs text-secondary" numberOfLines={2}>
        {event.target}
      </Text>

      {event.reason ? (
        <Text className="text-[11px] text-muted" numberOfLines={2}>
          {event.reason}
        </Text>
      ) : null}

      {event.arguments && Object.keys(event.arguments).length > 0 ? (
        <Text className="font-mono text-[11px] text-muted" numberOfLines={3}>
          {JSON.stringify(event.arguments).slice(0, 300)}
        </Text>
      ) : null}

      {isResolved !== undefined && isResolved !== null ? (
        <View className="flex-row items-center gap-1.5">
          {isResolved ? (
            <Check size={14} color="#34d399" />
          ) : (
            <X size={14} color="#f87171" />
          )}
          <Text className="text-[11px] font-medium text-secondary">
            {isResolved ? 'Permitido' : 'Negado'}
          </Text>
        </View>
      ) : (
        <View className="flex-row gap-2">
          <Button size="sm" variant="primary" title="Aprovar" loading={busy} onPress={() => act(true)} />
          <Button size="sm" variant="ghost" title="Negar" disabled={busy} onPress={() => act(false)} />
        </View>
      )}

      {error ? <Text className="text-[11px] font-mono text-err">{error}</Text> : null}
    </View>
  );
}