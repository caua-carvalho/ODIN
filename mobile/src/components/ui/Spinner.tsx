import { ActivityIndicator, View } from 'react-native';

export function Spinner({ labelClass }: { labelClass?: string }) {
  return (
    <View className="items-center justify-center py-10">
      <ActivityIndicator size="large" color="#FF7A00" />
    </View>
  );
}