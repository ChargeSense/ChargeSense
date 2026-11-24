import { useEffect, useState } from 'react';
import { Platform, Pressable, Text, View } from 'react-native';
import type { ApiConfig } from '../services/api';
import { disablePush, enablePush, savedRegistration, type Registration } from '../services/push';
import { colors } from '../theme/tokens';

export function PushSettings({ config, backend }: { config: ApiConfig; backend: boolean }) {
  const [saved, setSaved] = useState<Registration | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  useEffect(() => { void savedRegistration().then(setSaved).catch(() => setMessage('Não foi possível consultar o registro local.')); }, []);
  if (Platform.OS !== 'android') return <Text style={{ color: colors.muted }}>Notificações com o app fechado: disponíveis no app Android instalado.</Text>;
  async function change(enable: boolean) {
    setBusy(true); setMessage('');
    try {
      if (enable) { setSaved(await enablePush(config)); setMessage('Registro concluído. Faça um teste com o app fechado.'); }
      else { await disablePush(); setSaved(null); setMessage('Notificações desativadas.'); }
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Falha ao configurar notificações.'); }
    finally { setBusy(false); }
  }
  return <View style={{ gap: 10, paddingVertical: 16 }}>
    <Text style={{ color: colors.text, fontWeight: '700' }}>Notificações com o app fechado</Text>
    <Text style={{ color: colors.muted }}>{saved
      ? `Registro salvo: ${saved.config.stationId} · ${saved.config.source === 'simulated' ? 'Simulador' : 'Sensores'} · ${saved.config.baseUrl}`
      : 'Ative para receber agravamentos e retorno ao normal.'}</Text>
    <Text style={{ color: colors.muted }}>A assinatura permanece ativa ao fechar o app ou mudar para demonstração. Ao trocar a origem ou o servidor, atualize o registro abaixo.</Text>
    <Pressable disabled={busy || !backend || !config.baseUrl.trim() || !config.readKey.trim()} onPress={() => void change(true)}>
      <Text style={{ color: backend ? colors.accent : colors.muted }}>{busy ? 'Aguarde…' : saved ? 'Atualizar registro de notificações' : 'Ativar notificações'}</Text>
    </Pressable>
    {saved ? <Pressable disabled={busy} onPress={() => void change(false)}><Text style={{ color: colors.danger }}>Desativar notificações</Text></Pressable> : null}
    {message ? <Text accessibilityLiveRegion="polite" style={{ color: colors.text }}>{message}</Text> : null}
  </View>;
}
