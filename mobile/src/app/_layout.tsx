import '../global.css';

import { Component, useEffect, type ReactNode } from 'react';
import { Text, View, Pressable } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { QueryClientProvider } from '@tanstack/react-query';
import * as SplashScreen from 'expo-splash-screen';

import { ConfigProvider, useServerConfig } from '../providers/config';
import { queryClient } from '../lib/query';

SplashScreen.preventAutoHideAsync();

/**
 * Last-resort guard against render crashes: instead of a frozen white screen,
 * show a recoverable message (and let the user restart the app).
 */
class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <View className="flex-1 items-center justify-center bg-surface-canvas px-8 gap-3">
          <Text className="text-lg font-bold text-primary">Algo deu errado</Text>
          <Text className="text-sm text-secondary text-center leading-relaxed">
            O app encontrou um erro inesperado. Reinicie o aplicativo para continuar.
          </Text>
          <Text className="font-mono text-[11px] text-muted text-center" numberOfLines={4}>
            {String(this.state.error?.message ?? this.state.error)}
          </Text>
          <Pressable
            onPress={() => this.setState({ error: null })}
            className="bg-accent px-4 py-2.5 rounded-xl"
            accessibilityRole="button"
            accessibilityLabel="Tentar novamente"
          >
            <Text className="text-sm font-medium text-canvas">Tentar novamente</Text>
          </Pressable>
        </View>
      );
    }
    return this.props.children;
  }
}

function RootNavigator() {
  const { config, loading } = useServerConfig();

  useEffect(() => {
    if (!loading) {
      void SplashScreen.hideAsync();
    }
  }, [loading]);

  if (loading) return null;

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: '#050505' },
      }}
    >
      <Stack.Protected guard={!!config}>
        <Stack.Screen name="(tabs)" />
      </Stack.Protected>
      <Stack.Protected guard={!config}>
        <Stack.Screen name="connect" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <ErrorBoundary>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <KeyboardProvider>
          <ConfigProvider>
            <QueryClientProvider client={queryClient}>
              <StatusBar style="light" />
              <RootNavigator />
            </QueryClientProvider>
          </ConfigProvider>
        </KeyboardProvider>
      </GestureHandlerRootView>
    </ErrorBoundary>
  );
}