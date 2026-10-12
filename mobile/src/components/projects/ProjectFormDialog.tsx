import { Modal, Pressable, View, Text, ScrollView } from 'react-native';
import { useState } from 'react';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { PROJECT_COLORS, type Project, type ProjectCreate, type ProjectUpdate } from '../../types/project';
import { cn } from '../../lib/utils';

interface ProjectFormDialogProps {
  open: boolean;
  /** When set, the dialog edits this project; otherwise it creates a new one. */
  initial?: Project | null;
  busy?: boolean;
  onConfirm: (data: ProjectCreate | ProjectUpdate) => void;
  onClose: () => void;
}

/**
 * The form body is unmounted while the dialog is closed and remounted (with a
 * fresh `key`) every time it opens, so the fields are initialised directly from
 * `initial` — no prop→state sync effect required.
 */
export function ProjectFormDialog({ open, ...props }: ProjectFormDialogProps) {
  if (!open) return null;
  return <ProjectForm key={props.initial?.id ?? 'new'} {...props} />;
}

function ProjectForm({
  initial,
  busy = false,
  onConfirm,
  onClose,
}: Omit<ProjectFormDialogProps, 'open'>) {
  const [name, setName] = useState(initial?.name ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [color, setColor] = useState(initial?.color ?? PROJECT_COLORS[0]);

  const handleConfirm = () => {
    if (!name.trim()) return;
    onConfirm({ name: name.trim(), description: description.trim() || undefined, color });
  };

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <Pressable className="flex-1 bg-black/60 items-center justify-center px-6" onPress={onClose}>
        <Pressable className="w-full max-w-sm bg-surface-base border border-line rounded-2xl p-5 gap-4">
          <Text className="text-base font-bold text-primary">
            {initial ? 'Editar projeto' : 'Novo projeto'}
          </Text>

          <Input
            label="Nome"
            placeholder="Nome do projeto"
            autoFocus
            value={name}
            onChangeText={setName}
          />
          <Input
            label="Descrição (opcional)"
            placeholder="O que é este projeto?"
            multiline
            value={description}
            onChangeText={setDescription}
          />

          <View className="gap-1.5">
            <Text className="text-xs font-medium text-muted uppercase tracking-wider">Cor</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View className="flex-row gap-2.5 py-1">
                {PROJECT_COLORS.map((c) => (
                  <Pressable
                    key={c}
                    onPress={() => setColor(c)}
                    className={cn(
                      'w-8 h-8 rounded-full items-center justify-center border-2',
                      color === c ? 'border-primary' : 'border-transparent'
                    )}
                    style={{ backgroundColor: c }}
                  >
                    {color === c ? <View className="w-2 h-2 rounded-full bg-canvas" /> : null}
                  </Pressable>
                ))}
              </View>
            </ScrollView>
          </View>

          <View className="flex-row gap-3 justify-end">
            <Button variant="ghost" title="Cancelar" onPress={onClose} disabled={busy} />
            <Button
              title={initial ? 'Salvar' : 'Criar'}
              loading={busy}
              disabled={!name.trim()}
              onPress={handleConfirm}
            />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
