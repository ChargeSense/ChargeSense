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


export async function diagnosePush(test = false): Promise<string> {
  const saved = await savedRegistration();
  if (!saved) throw new Error('Permissão Android não basta: toque em Ativar notificações primeiro.');
  const permission = await Notifications.getPermissionsAsync();
  const channel = await Notifications.getNotificationChannelAsync('chargesense-alerts');
  if (!permission.granted || channel?.importance === Notifications.AndroidImportance.NONE) {
    throw new Error('Notificações ou canal Alertas elétricos estão bloqueados no Android.');
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const { config, token } = saved;
    const path = test ? 'push-test' : 'push-diagnostics';
    const response = await fetch(`${config.baseUrl}/api/v1/stations/${encodeURIComponent(config.stationId)}/${path}`, {
      method: 'POST', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-API-Key': config.readKey },
      body: JSON.stringify({ token, source: config.source }),
    });
    if (!response.ok) throw new Error(`Diagnóstico HTTP ${response.status}. Confira backend atualizado, endereço e chave do registro salvo.`);
    if (test) return 'Teste agendado. Vá à tela inicial do Android agora; o envio ocorrerá após 15 segundos.';
    const info = await response.json() as {
      registered: boolean; source: string | null; workerRunning: boolean;
      lastJob: { id: number; phase: string; error: string | null; attempts: number } | null;
    };
    if (!info.registered) return 'Dispositivo não cadastrado no backend. Atualize o registro de notificações.';
    if (!info.workerRunning) return 'Worker push parado. Reinicie o backend e confira seu terminal.';
    if (!info.lastJob) return `Registro ativo (${info.source}), mas nenhum push foi enfileirado. Use Testar notificação.`;
    const job = info.lastJob;
    const hints: Record<string, string> = {
      InvalidCredentials: 'Confira a chave FCM V1 no Expo para com.chargesense.',
      MismatchSenderId: 'A chave FCM no Expo e google-services.json devem pertencer ao mesmo Firebase.',
      DeviceNotRegistered: 'Atualize o registro para obter um token válido.',
      HTTP401: 'Confira CHARGESENSE_EXPO_ACCESS_TOKEN e a segurança push no Expo.',
      HTTP403: 'Confira autorização e credenciais do Expo.',
      ConnectError: 'O backend não conseguiu conectar ao Expo. Confira internet, proxy e firewall.',
      ReadTimeout: 'O Expo não respondeu a tempo; haverá novas tentativas se aplicável.',
    };
    const phases: Record<string, string> = {
      send: 'Aguardando envio/tentativa',
      receipt: 'Aceito pela Expo; aguardando recibo (consulta em cerca de 15 minutos)',
      done: 'Aceito pelo provedor; isto não confirma exibição no Android',
      failed: 'Envio falhou',
    };
    return `Job ${job.id}: ${phases[job.phase] ?? job.phase}. Tentativas: ${job.attempts}.` +
      (job.error ? ` Erro: ${job.error}. ${hints[job.error] ?? 'Confira o terminal do backend.'}` : '');
  } finally { clearTimeout(timeout); }
}
