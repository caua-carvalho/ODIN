import { Modal, Pressable, View, Text } from 'react-native';
import { useState } from 'react';
import { Input } from './Input';
import { Button } from './Button';

interface PromptDialogProps {
  open: boolean;
  title: string;
  placeholder?: string;
  initialValue?: string;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: (value: string) => void;
  onClose: () => void;
}

/**
 * The body is unmounted while the dialog is closed and remounted (with a fresh
 * `key`) every time it opens, so the input is seeded directly from
 * `initialValue` — no prop→state sync effect required.
 */
export function PromptDialog({ open, ...props }: PromptDialogProps) {
  if (!open) return null;
  return <PromptDialogBody key={props.initialValue ?? ''} {...props} />;
}

function PromptDialogBody({
  title,
  placeholder,
  initialValue = '',
  confirmLabel = 'Criar',
  busy = false,
  onConfirm,
  onClose,
}: Omit<PromptDialogProps, 'open'>) {
  const [value, setValue] = useState(initialValue);

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable className="flex-1 bg-black/60 items-center justify-center px-6" onPress={onClose}>
        <Pressable className="w-full max-w-sm bg-surface-base border border-line rounded-2xl p-5 gap-4">
          <Text className="text-base font-bold text-primary">{title}</Text>
          <Input
            autoFocus
            placeholder={placeholder}
            value={value}
            onChangeText={setValue}
            onSubmitEditing={() => value.trim() && onConfirm(value.trim())}
            returnKeyType="done"
          />
          <View className="flex-row gap-3 justify-end">
            <Button variant="ghost" title="Cancelar" onPress={onClose} disabled={busy} />
            <Button
              title={confirmLabel}
              loading={busy}
              disabled={!value.trim()}
              onPress={() => onConfirm(value.trim())}
            />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
