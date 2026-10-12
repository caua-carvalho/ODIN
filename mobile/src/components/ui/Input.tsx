import { TextInput, View, Text, type TextInputProps } from 'react-native';

interface InputProps extends TextInputProps {
  label?: string;
}

export function Input({ label, className, ...rest }: InputProps) {
  return (
    <View className="gap-1.5">
      {label ? (
        <Text className="text-xs font-medium text-muted uppercase tracking-wider">{label}</Text>
      ) : null}
      <TextInput
        placeholderTextColor="#6E6E73"
        className={
          className ??
          'bg-surface-container border border-line rounded-xl px-3.5 py-2.5 text-primary text-sm'
        }
        {...rest}
      />
    </View>
  );
}