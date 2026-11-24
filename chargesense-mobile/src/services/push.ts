import { Platform } from 'react-native';
import Constants from 'expo-constants';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import type { ApiConfig } from './api';

// Foreground notices already appear in the app banner.
Notifications.setNotificationHandler({ handleNotification: async () => ({
  shouldShowBanner: false, shouldShowList: false, shouldPlaySound: false, shouldSetBadge: false,
}) });
export type Registration = { config: ApiConfig; token: string };
const KEY = 'chargesense.push.registration';
export async function savedRegistration(): Promise<Registration | null> {
  if (Platform.OS !== 'android') return null;
  const value = await SecureStore.getItemAsync(KEY);
  return value ? JSON.parse(value) as Registration : null;
}
async function subscribe(registration: Registration, enabled: boolean) {
  const { config, token } = registration;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`${config.baseUrl.replace(/\/+$/, '')}/api/v1/stations/${encodeURIComponent(config.stationId)}/push-subscriptions`, {
      method: 'POST', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-API-Key': config.readKey },
      body: JSON.stringify({ token, source: config.source, enabled }),
    });
    if (!response.ok) throw new Error(`Não foi possível registrar notificações (HTTP ${response.status}).`);
  } finally { clearTimeout(timeout); }
}
export async function enablePush(config: ApiConfig): Promise<Registration> {
  if (Platform.OS !== 'android') throw new Error('Push disponível nesta versão para Android instalado.');
  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) throw new Error('Configure o projeto Expo/EAS e reinstale o aplicativo conforme o guia de push.');
  await Notifications.setNotificationChannelAsync('chargesense-alerts', {
    name: 'Alertas elétricos', importance: Notifications.AndroidImportance.HIGH,
    sound: 'default', vibrationPattern: [0, 250, 250, 250],
  });
  let permission = await Notifications.getPermissionsAsync();
  if (!permission.granted) permission = await Notifications.requestPermissionsAsync();
  if (!permission.granted) throw new Error('Permita notificações nas configurações do Android.');
  const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
  const next = { config: { ...config, baseUrl: config.baseUrl.trim().replace(/\/+$/, ''), readKey: config.readKey.trim() }, token };
  const old = await savedRegistration();
  if (old && (old.config.baseUrl !== next.config.baseUrl || old.token !== token)) {
    await subscribe(old, false);
    await SecureStore.deleteItemAsync(KEY);
  }
  await subscribe(next, true);
  await SecureStore.setItemAsync(KEY, JSON.stringify(next));
  return next;
}
export async function disablePush(): Promise<void> {
  const old = await savedRegistration();
  if (old) await subscribe(old, false);
  await SecureStore.deleteItemAsync(KEY);
}
