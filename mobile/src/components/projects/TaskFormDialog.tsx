import { Modal, Pressable, View, Text } from 'react-native';
import { useState } from 'react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { Segmented } from '../ui/Segmented';
import {
  PRIORITY_LABELS,
  type Task,
  type TaskCreate,
  type TaskPriority,
  type TaskUpdate,
} from '../../types/project';

interface TaskFormDialogProps {
  open: boolean;
  initial?: Task | null;
  busy?: boolean;
  onConfirm: (data: TaskCreate | TaskUpdate) => void;
  onClose: () => void;
}

/**
 * The form body is unmounted while the dialog is closed and remounted (with a
 * fresh `key`) every time it opens, so the fields are initialised directly from
 * `initial` — no prop→state sync effect required.
 */
export function TaskFormDialog({ open, ...props }: TaskFormDialogProps) {
  if (!open) return null;
  return <TaskForm key={props.initial?.id ?? 'new'} {...props} />;
}

function TaskForm({
  initial,
  busy = false,
  onConfirm,
  onClose,
}: Omit<TaskFormDialogProps, 'open'>) {
  const [title, setTitle] = useState(initial?.title ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [priority, setPriority] = useState<TaskPriority>(initial?.priority ?? 'medium');

  const handleConfirm = () => {
    if (!title.trim()) return;
    onConfirm({
      title: title.trim(),
      description: description.trim() || undefined,
      priority,
    });
  };

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable className="flex-1 bg-black/60 items-center justify-center px-6" onPress={onClose}>
        <Pressable className="w-full max-w-sm bg-surface-base border border-line rounded-2xl p-5 gap-4">
          <Text className="text-base font-bold text-primary">
            {initial ? 'Editar tarefa' : 'Nova tarefa'}
          </Text>

          <Input
            label="Título"
            placeholder="Título da tarefa"
            autoFocus
            value={title}
            onChangeText={setTitle}
          />
          <Input
            label="Descrição (opcional)"
            placeholder="Detalhes…"
            multiline
            value={description}
            onChangeText={setDescription}
          />

          <View className="gap-1.5">
            <Text className="text-xs font-medium text-muted uppercase tracking-wider">Prioridade</Text>
            <Segmented
              options={[
                { id: 'low', label: PRIORITY_LABELS.low },
                { id: 'medium', label: PRIORITY_LABELS.medium },
                { id: 'high', label: PRIORITY_LABELS.high },
              ]}
              value={priority}
              onChange={setPriority}
            />
          </View>

          <View className="flex-row gap-3 justify-end">
            <Button variant="ghost" title="Cancelar" onPress={onClose} disabled={busy} />
            <Button
              title={initial ? 'Salvar' : 'Criar'}
              loading={busy}
              disabled={!title.trim()}
              onPress={handleConfirm}
            />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
