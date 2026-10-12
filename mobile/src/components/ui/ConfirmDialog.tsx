import { Modal, Pressable, View, Text } from 'react-native';
import { Button } from './Button';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirmar',
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        className="flex-1 bg-black/60 items-center justify-center px-6"
        onPress={onClose}
      >
        <Pressable className="w-full max-w-sm bg-surface-base border border-line rounded-2xl p-5 gap-4">
          <Text className="text-base font-bold text-primary">{title}</Text>
          {description ? <Text className="text-sm text-secondary leading-relaxed">{description}</Text> : null}
          <View className="flex-row gap-3 justify-end">
            <Button variant="ghost" title="Cancelar" onPress={onClose} disabled={busy} />
            <Button
              variant={danger ? 'danger' : 'primary'}
              title={confirmLabel}
              loading={busy}
              onPress={onConfirm}
            />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}