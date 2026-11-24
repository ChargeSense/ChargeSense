import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StatusBar, StyleSheet, Text, TextInput, View, useWindowDimensions,
} from 'react-native';
import { PushSettings } from './components/PushSettings';
import { MetricCard } from './components/MetricCard';
import { StatusPill } from './components/StatusPill';
import { chargesenseApi, ApiError, type ApiConfig } from './services/api';
import { colors } from './theme/tokens';
import type { DataSource, StationEvent, StationStatus, TelemetryReading } from './types/telemetry';

type Tab = 'overview' | 'history' | 'events' | 'settings';
type Mode = 'demo' | 'backend';

const STATION_ID = 'bancada-01';
const DEFAULT_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';

function demoReading(sequence: number): TelemetryReading {
  const current = Number((15.2 + Math.sin(sequence / 3) * 0.8).toFixed(1));
  const voltage = Number((220 + Math.sin(sequence / 5) * 1.2).toFixed(1));
  const temperature = Number((32 + Math.sin(sequence / 7) * 1.4).toFixed(1));
  return {
    id: sequence + 1, schemaVersion: 1, stationId: STATION_ID, bootId: 'demo-session',
    sequence, source: 'simulated', measuredAt: new Date().toISOString(),
    receivedAt: new Date().toISOString(), uptimeMs: sequence * 5000, quality: 'valid',
    measurements: { currentA: current, voltageV: voltage, activePowerW: Math.round(current * voltage * 0.95), panelTempC: temperature },
  };
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Horário indisponível';
  return new Date(value).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', dateStyle: 'short', timeStyle: 'medium' });
}
function sourceName(source: DataSource): string { return source === 'sensor' ? 'Sensores' : 'Simulador'; }
function levelName(level: StationEvent['level']): string {
  return ({ normal: 'Normalizado', diagnostic: 'Diagnóstico', attention: 'Atenção', alert: 'Alerta', critical: 'Crítico' })[level];
}
function levelColor(level: StationEvent['level']): string {
  return ({ normal: colors.success, diagnostic: colors.blue, attention: colors.warning,
    alert: colors.alert, critical: colors.danger })[level];
}
function eventDetails(event: StationEvent): string {
  return event.value != null && event.threshold != null
    ? ` · ${event.value.toFixed(3)} ${event.unit ?? ''} (limite: ${event.threshold.toFixed(3)} ${event.unit ?? ''})` : '';
}
function eventName(kind: string): string {
  const names: Record<string, string> = {
    measurement_uncalibrated: 'Medição não calibrada',
    measurement_invalid: 'Medição inválida',
    current_threshold: 'Limite de corrente atingido',
    voltage_threshold: 'Limite de tensão atingido',
    current_recovered: 'Corrente normalizada',
    voltage_recovered: 'Tensão normalizada',
  };
  return names[kind] ?? kind.replace(/_/g, ' ');
}

function Header({ subtitle }: { subtitle: string }) {
  return <View style={styles.header}>
    <View style={styles.brandMark}><View style={styles.brandBolt}><Text style={styles.brandBoltText}>C</Text></View></View>
    <View style={{ flex: 1 }}><Text style={styles.brand}>CHARGESENSE</Text><Text style={styles.headerSubtitle}>{subtitle}</Text></View>
  </View>;
}

function SectionTitle({ title, detail }: { title: string; detail?: string }) {
  return <View style={styles.sectionTitle}><Text style={styles.sectionHeading}>{title}</Text>{detail ? <Text style={styles.sectionDetail}>{detail}</Text> : null}</View>;
}

function Overview({ reading, status, mode, refreshing, error, onRefresh, events }: {
  reading: TelemetryReading | null; status: StationStatus | null; mode: Mode; refreshing: boolean;
  error: string | null; onRefresh: () => void; events: StationEvent[];
}) {
  const { width } = useWindowDimensions();
  const compact = width < 360;
  const m = reading?.measurements;
  const temperatureColor = m?.panelTempC != null && m.panelTempC >= 45 ? colors.warning : colors.text;
  return <ScrollView contentContainerStyle={styles.page} showsVerticalScrollIndicator={false}>
    <View style={styles.stationHeading}>
      <View><Text style={styles.eyebrow}>ESTAÇÃO MONITORADA</Text><Text style={styles.stationName}>Bancada 01</Text><Text style={styles.stationId}>{STATION_ID}</Text></View>
      <StatusPill state={mode === 'demo' ? 'online' : status?.connection ?? 'never_seen'} />
    </View>
    <View style={styles.sourceLine}>
      <View style={[styles.sourceDot, { backgroundColor: mode === 'demo' ? colors.blue : colors.accent }]} />
      <Text style={styles.sourceText}>{mode === 'demo' ? 'Demonstração local' : `Backend local · ${sourceName(status?.source ?? 'simulated')}`}</Text>
      <Text style={styles.sourceDivider}>/</Text>
      <Text style={styles.sourceText}>{mode === 'demo' ? 'sem hardware' : status?.freshness === 'fresh' ? 'dados recentes' : status?.freshness === 'stale' ? 'dados desatualizados' : 'frescor desconhecido'}</Text>
    </View>

    <View style={styles.panel}>
      <View style={styles.panelTop}><Text style={styles.panelLabel}>VISÃO GERAL</Text><Text style={styles.panelTime}>{reading ? formatDate(reading.measuredAt) : 'Sem leitura'}</Text></View>
      {reading ? <View style={[styles.metricsGrid, compact && styles.metricsGridCompact]}>
        <MetricCard label="CORRENTE" value={m?.currentA} unit="A" accent={colors.accent} />
        <MetricCard label="TENSÃO" value={m?.voltageV} unit="V" />
        <MetricCard label="POTÊNCIA ATIVA" value={m?.activePowerW} unit="W" precision={0} />
        <MetricCard label="TEMP. DO QUADRO" value={m?.panelTempC} unit="°C" accent={temperatureColor} />
      </View> : <View style={styles.emptyState}><Text style={styles.emptyTitle}>Nenhuma leitura recebida</Text><Text style={styles.emptyText}>Verifique a conexão com o backend e a origem selecionada.</Text></View>}
      <View style={styles.panelFooter}><Text style={styles.footerLabel}>QUALIDADE DA MEDIÇÃO</Text><Text style={styles.footerValue}>{reading?.quality === 'valid' ? 'Válida' : reading?.quality === 'uncalibrated' ? 'Não calibrada' : reading?.quality === 'invalid' ? 'Inválida' : '—'}</Text></View>
    </View>

    <View style={styles.infoRow}>
      <View style={styles.infoCard}><Text style={styles.infoLabel}>ÚLTIMO RECEBIMENTO</Text><Text style={styles.infoValue}>{status?.lastReceivedAt ? formatDate(status.lastReceivedAt) : mode === 'demo' ? 'Agora · local' : 'Ainda não recebido'}</Text></View>
      <View style={styles.infoCard}><Text style={styles.infoLabel}>PROTEÇÃO LOCAL</Text><Text style={styles.infoValue}>No dispositivo embarcado</Text></View>
    </View>

    <SectionTitle title="Eventos recentes" detail="Registros do backend" />
    {events.length ? events.slice(0, 3).map((event) => <EventRow key={event.id} event={event} />) :
      <View style={styles.emptyInline}><Text style={styles.emptyText}>Nenhum evento registrado para esta origem.</Text></View>}
    {error ? <View style={styles.errorBox}><Text style={styles.errorText}>{error}</Text></View> : null}
    <Pressable onPress={onRefresh} style={styles.secondaryButton}><Text style={styles.secondaryButtonText}>{refreshing ? 'Atualizando…' : 'Atualizar dados'}</Text></Pressable>
    <Text style={styles.disclaimer}>O aplicativo apresenta telemetria e eventos registrados. A indicação de estado da conexão não comprova que a carga esteja ligada ou desligada.</Text>
  </ScrollView>;
}

function EventRow({ event }: { event: StationEvent }) {
  const color = levelColor(event.level);
  return <View style={styles.eventRow}><View style={[styles.eventRail, { backgroundColor: color }]} /><View style={{ flex: 1 }}><Text style={styles.eventTitle}>{eventName(event.kind)}{eventDetails(event)}</Text><Text style={styles.eventMeta}>{levelName(event.level)} · {formatDate(event.receivedAt)}</Text></View></View>;
}

function History({ readings, mode, loading }: { readings: TelemetryReading[]; mode: Mode; loading: boolean }) {
  return <ScrollView contentContainerStyle={styles.page}>
    <SectionTitle title="Histórico de leituras" detail={mode === 'demo' ? 'Sessão de demonstração' : 'Últimos registros do backend'} />
    {loading ? <ActivityIndicator color={colors.accent} /> : null}
    {!readings.length && !loading ? <View style={styles.emptyState}><Text style={styles.emptyTitle}>Histórico vazio</Text><Text style={styles.emptyText}>As leituras aparecerão aqui assim que forem recebidas.</Text></View> : null}
    {readings.map((item) => <View key={item.id} style={styles.historyRow}>
      <View style={{ flex: 1 }}><Text style={styles.historyDate}>{formatDate(item.measuredAt)}</Text><Text style={styles.historySource}>{sourceName(item.source)} · {item.quality === 'valid' ? 'Válida' : item.quality}</Text></View>
      <View style={styles.historyValues}><Text style={styles.historyMain}>{item.measurements.currentA == null ? '—' : item.measurements.currentA.toFixed(1) + ' A'}</Text><Text style={styles.historySub}>{item.measurements.voltageV == null ? '—' : item.measurements.voltageV.toFixed(1) + ' V'} · {item.measurements.activePowerW == null ? '—' : Math.round(item.measurements.activePowerW) + ' W'}</Text></View>
    </View>)}
  </ScrollView>;
}

function Events({ events, loading }: { events: StationEvent[]; loading: boolean }) {
  return <ScrollView contentContainerStyle={styles.page}><SectionTitle title="Central de eventos" detail="Ocorrências retornadas pela API" />
    {loading ? <ActivityIndicator color={colors.accent} /> : null}
    {events.length ? events.map((event) => <EventRow key={event.id} event={event} />) :
      <View style={styles.emptyState}><Text style={styles.emptyTitle}>Tudo tranquilo por aqui</Text><Text style={styles.emptyText}>Nenhum evento foi registrado pelo backend para a estação selecionada.</Text></View>}
    <Text style={styles.disclaimer}>Os alertas de tensão e corrente registram mudanças de nível. Eles não representam, por si só, um comando de desligamento ou confirmação de corte de energia.</Text>
  </ScrollView>;
}

function Settings({ mode, setMode, baseUrl, setBaseUrl, readKey, setReadKey, source, setSource, onSave, saving }: {
  mode: Mode; setMode: (v: Mode) => void; baseUrl: string; setBaseUrl: (v: string) => void;
  readKey: string; setReadKey: (v: string) => void; source: DataSource; setSource: (v: DataSource) => void;
  onSave: () => void; saving: boolean;
}) {
  return <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <SectionTitle title="Configurações" detail="Conexão e origem dos dados" />
      <Text style={styles.fieldLabel}>MODO DE OPERAÇÃO</Text>
      <View style={styles.segment}><Pressable onPress={() => setMode('demo')} style={[styles.segmentButton, mode === 'demo' && styles.segmentActive]}><Text style={[styles.segmentText, mode === 'demo' && styles.segmentTextActive]}>Demonstração</Text></Pressable><Pressable onPress={() => setMode('backend')} style={[styles.segmentButton, mode === 'backend' && styles.segmentActive]}><Text style={[styles.segmentText, mode === 'backend' && styles.segmentTextActive]}>Backend local</Text></Pressable></View>
      {mode === 'backend' ? <>
        <Text style={styles.fieldLabel}>ENDEREÇO DA API</Text>
        <TextInput value={baseUrl} onChangeText={setBaseUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="http://10.0.2.2:8000" placeholderTextColor={colors.subtle} style={styles.input} />
        <Text style={styles.helper}>Emulador Android: 10.0.2.2. Celular físico: use o IP do computador na rede Wi-Fi.</Text>
        <Text style={styles.fieldLabel}>CHAVE DE LEITURA (X-API-KEY)</Text>
        <TextInput value={readKey} onChangeText={setReadKey} autoCapitalize="none" autoCorrect={false} secureTextEntry placeholder="Chave configurada no backend" placeholderTextColor={colors.subtle} style={styles.input} />
        <Text style={styles.fieldLabel}>ORIGEM DOS DADOS</Text>
        <View style={styles.segment}><Pressable onPress={() => setSource('simulated')} style={[styles.segmentButton, source === 'simulated' && styles.segmentActive]}><Text style={[styles.segmentText, source === 'simulated' && styles.segmentTextActive]}>Simulador</Text></Pressable><Pressable onPress={() => setSource('sensor')} style={[styles.segmentButton, source === 'sensor' && styles.segmentActive]}><Text style={[styles.segmentText, source === 'sensor' && styles.segmentTextActive]}>Sensores</Text></Pressable></View>
        <Text style={styles.helper}>O app usa somente a chave de leitura. A chave de dispositivo, usada para enviar telemetria, não deve ser colocada no aplicativo.</Text>
      </> : <View style={styles.demoNote}><Text style={styles.demoNoteTitle}>Modo independente</Text><Text style={styles.helper}>Gera valores demonstrativos no próprio aplicativo. Não exige backend, internet, Wokwi ou ESP32. Os dados são fictícios e identificados como demonstração.</Text></View>}
      <View style={styles.configSummary}><Text style={styles.summaryLabel}>ESTAÇÃO</Text><Text style={styles.summaryValue}>{STATION_ID}</Text><Text style={styles.summaryLabel}>ATUALIZAÇÃO</Text><Text style={styles.summaryValue}>A cada 5 segundos</Text></View>
      <PushSettings backend={mode === 'backend'} config={{ baseUrl, readKey, source, stationId: STATION_ID }} />
      <Pressable onPress={onSave} style={styles.primaryButton}><Text style={styles.primaryButtonText}>{saving ? 'Salvando…' : 'Salvar e conectar'}</Text></Pressable>
    </ScrollView>
  </KeyboardAvoidingView>;
}

export default function App() {
  const [tab, setTab] = useState<Tab>('overview');
  const [mode, setMode] = useState<Mode>('demo');
  const [baseUrl, setBaseUrl] = useState(DEFAULT_URL);
  const [readKey, setReadKey] = useState('');
  const [source, setSource] = useState<DataSource>('simulated');
  const [reading, setReading] = useState<TelemetryReading | null>(demoReading(0));
  const [readings, setReadings] = useState<TelemetryReading[]>([demoReading(0)]);
  const [status, setStatus] = useState<StationStatus | null>(null);
  const [events, setEvents] = useState<StationEvent[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demoSequence, setDemoSequence] = useState(0);

  const [notices, setNotices] = useState<StationEvent[]>([]);
  const notice = notices[0];
  const notificationCursor = useRef<number | null>(null);
  const generation = useRef(0);
  const busy = useRef<number | null>(null);

  const config = useMemo<ApiConfig>(() => ({ baseUrl, readKey, stationId: STATION_ID, source }), [baseUrl, readKey, source]);

  const refreshBackend = useCallback(async () => {
    if (mode !== 'backend' || busy.current === generation.current) return;
    const requestGeneration = generation.current;
    busy.current = requestGeneration;
    setRefreshing(true);
    try {
      const [latestResult, statusResult, historyResult, eventsResult] = await Promise.all([
        chargesenseApi.latest(config).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }), chargesenseApi.status(config),
        chargesenseApi.history(config), chargesenseApi.events(config),
      ]);
      if (requestGeneration !== generation.current) return;
      // Catch up all events since the last successful poll, including bursts >30.
      let before = eventsResult.nextBeforeId;
      while (notificationCursor.current !== null && before !== null &&
             eventsResult.items.length && (eventsResult.items[eventsResult.items.length - 1]?.id ?? 0) > notificationCursor.current) {
        const page = await chargesenseApi.events(config, before);
        if (requestGeneration !== generation.current) return;
        eventsResult.items.push(...page.items);
        before = page.nextBeforeId;
      }
      const newestId = Math.max(0, ...eventsResult.items.map((event) => event.id));
      if (notificationCursor.current !== null) {
        const next = eventsResult.items.filter((event) => event.id > notificationCursor.current!
          && ['current_threshold', 'voltage_threshold', 'current_recovered', 'voltage_recovered'].includes(event.kind));
        if (next.length) setNotices((previous) => [...previous, ...next.sort((a, b) => a.id - b.id)]);
      }
      notificationCursor.current = Math.max(notificationCursor.current ?? 0, newestId);
      setReading(latestResult);
      setStatus(statusResult);
      setReadings(historyResult.items);
      setEvents(eventsResult.items.slice(0, 30));
      setError(null);
    } catch (e) {
      if (requestGeneration !== generation.current) return;
      setStatus(null);
      setError(e instanceof Error ? e.message : 'Falha ao consultar o backend.');
    } finally {
      if (requestGeneration === generation.current) {
        busy.current = null;
        setRefreshing(false);
      }
    }
  }, [config, mode]);

  useEffect(() => {
    generation.current += 1;
    busy.current = null;
    notificationCursor.current = null;
    setNotices([]); setStatus(null); setEvents([]); setError(null);
    setRefreshing(false);
    if (mode !== 'backend') return;
    setReading(null); setReadings([]);
    void refreshBackend();
    const timer = setInterval(() => { void refreshBackend(); }, 5000);
    return () => { clearInterval(timer); generation.current += 1; };
  }, [mode, refreshBackend]);

  useEffect(() => {
    if (mode !== 'demo') return;
    const timer = setInterval(() => {
      setDemoSequence((current) => {
        const next = current + 1;
        const item = demoReading(next);
        setReading(item);
        setReadings((previous) => [item, ...previous].slice(0, 30));
        return next;
      });
    }, 5000);
    return () => clearInterval(timer);
  }, [mode]);

  function saveSettings() {
    if (mode === 'backend' && (!baseUrl.trim() || !readKey.trim())) {
      Alert.alert('Configuração incompleta', 'Informe o endereço da API e a chave de leitura.');
      return;
    }
    setTab('overview');
    if (mode === 'backend') void refreshBackend();
    else {
      const item = demoReading(demoSequence);
      setReading(item); setReadings((previous) => [item, ...previous].slice(0, 30));
      setError(null); setStatus(null); setEvents([]);
    }
  }

  const title = tab === 'overview' ? 'Monitoramento da estação' : tab === 'history' ? 'Leituras registradas' : tab === 'events' ? 'Alertas e ocorrências' : 'Preferências do sistema';

  return <View style={styles.app}>
    <StatusBar barStyle="light-content" backgroundColor={colors.background} />
    <Header subtitle={title} />
    {notice && mode === 'backend' ? <View accessibilityRole="alert" accessibilityLiveRegion="assertive" style={{ padding: 12, backgroundColor: colors.surfaceRaised }}>
      <Text style={{ color: levelColor(notice.level), fontWeight: '700' }}>
        {levelName(notice.level)} · {sourceName(source)}
      </Text>
      <Text style={{ color: colors.text }}>{eventName(notice.kind)}{eventDetails(notice)}</Text>
      <Text style={{ color: colors.muted }}>{formatDate(notice.receivedAt)}</Text>
      <Pressable accessibilityRole="button" onPress={() => setNotices((previous) => previous.slice(1))}><Text style={{ color: colors.accent, paddingVertical: 8 }}>Dispensar aviso</Text></Pressable>
    </View> : null}
    <View style={styles.content}>
      {tab === 'overview' ? <Overview reading={reading} status={status} mode={mode} refreshing={refreshing} error={error} onRefresh={() => mode === 'backend' ? void refreshBackend() : setDemoSequence((v) => v + 1)} events={events} /> : null}
      {tab === 'history' ? <History readings={readings} mode={mode} loading={loadingHistory} /> : null}
      {tab === 'events' ? <Events events={events} loading={false} /> : null}
      {tab === 'settings' ? <Settings mode={mode} setMode={setMode} baseUrl={baseUrl} setBaseUrl={setBaseUrl} readKey={readKey} setReadKey={setReadKey} source={source} setSource={setSource} onSave={saveSettings} saving={refreshing} /> : null}
    </View>
    <View style={styles.tabBar}>
      {([{ id: 'overview', label: 'Visão geral', icon: '◫' }, { id: 'history', label: 'Histórico', icon: '↗' }, { id: 'events', label: 'Eventos', icon: '!' }, { id: 'settings', label: 'Ajustes', icon: '⚙' }] as const).map((item) =>
        <Pressable key={item.id} onPress={() => setTab(item.id)} style={styles.tabItem}>
          <View style={[styles.tabIcon, tab === item.id && styles.tabIconActive]}><Text style={[styles.tabIconText, tab === item.id && styles.tabIconTextActive]}>{item.icon}</Text></View>
          <Text style={[styles.tabLabel, tab === item.id && styles.tabLabelActive]}>{item.label}</Text>
        </Pressable>)}
    </View>
  </View>;
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: colors.background, paddingTop: Platform.OS === 'android' ? StatusBar.currentHeight ?? 0 : 0 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingTop: 12, paddingBottom: 16, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 12 },
  brandMark: { width: 38, height: 38, borderRadius: 12, backgroundColor: colors.accentDark, alignItems: 'center', justifyContent: 'center' },
  brandBolt: { width: 24, height: 24, borderRadius: 8, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' },
  brandBoltText: { color: colors.background, fontSize: 17, fontWeight: '900' },
  brand: { color: colors.text, fontSize: 13, fontWeight: '900', letterSpacing: 1.8 },
  headerSubtitle: { color: colors.muted, fontSize: 11, marginTop: 3 },
  headerTag: { borderWidth: 1, borderColor: colors.border, borderRadius: 7, paddingHorizontal: 8, paddingVertical: 5 },
  headerTagText: { color: colors.muted, fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  content: { flex: 1 },
  page: { padding: 16, paddingBottom: 44, gap: 14 },
  stationHeading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  eyebrow: { color: colors.subtle, fontSize: 10, fontWeight: '800', letterSpacing: 1.3 },
  stationName: { color: colors.text, fontSize: 23, fontWeight: '700', marginTop: 4 },
  stationId: { color: colors.muted, fontSize: 11, marginTop: 2 },
  sourceLine: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7, marginTop: 2, marginBottom: 4 },
  sourceDot: { width: 7, height: 7, borderRadius: 8 },
  sourceText: { color: colors.muted, fontSize: 11, flexShrink: 1 },
  sourceDivider: { color: colors.subtle, fontSize: 12 },
  panel: { backgroundColor: '#0B1B2B', borderRadius: 20, borderWidth: 1, borderColor: colors.border, padding: 14, gap: 12 },
  panelTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 },
  panelLabel: { color: colors.muted, fontSize: 10, fontWeight: '800', letterSpacing: 1.2 },
  panelTime: { color: colors.subtle, fontSize: 10 },
  metricsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  metricsGridCompact: { flexDirection: 'column' },
  panelFooter: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 11, flexDirection: 'row', justifyContent: 'space-between' },
  footerLabel: { color: colors.subtle, fontSize: 10, fontWeight: '700', letterSpacing: 0.6 },
  footerValue: { color: colors.accent, fontSize: 11, fontWeight: '700' },
  infoRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  infoCard: { flex: 1, minWidth: '46%', backgroundColor: colors.surface, borderRadius: 13, borderWidth: 1, borderColor: colors.border, padding: 12, gap: 7 },
  infoLabel: { color: colors.subtle, fontSize: 9, fontWeight: '800', letterSpacing: 0.5 },
  infoValue: { color: colors.text, fontSize: 11, fontWeight: '600' },
  sectionTitle: { marginTop: 8, marginBottom: 2, gap: 4 },
  sectionHeading: { color: colors.text, fontSize: 18, fontWeight: '700' },
  sectionDetail: { color: colors.muted, fontSize: 11 },
  eventRow: { flexDirection: 'row', backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: 'hidden', minHeight: 64, alignItems: 'center' },
  eventRail: { width: 3, alignSelf: 'stretch' },
  eventTitle: { color: colors.text, fontSize: 12, fontWeight: '700', marginLeft: 12, marginTop: 10 },
  eventMeta: { color: colors.muted, fontSize: 10, marginLeft: 12, marginTop: 4, marginBottom: 10 },
  emptyState: { backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 22, alignItems: 'center', gap: 8 },
  emptyInline: { padding: 12 },
  emptyTitle: { color: colors.text, fontSize: 14, fontWeight: '700' },
  emptyText: { color: colors.muted, fontSize: 11, textAlign: 'center', lineHeight: 17 },
  errorBox: { padding: 12, backgroundColor: colors.dangerSurface, borderRadius: 10, borderWidth: 1, borderColor: '#754047' },
  errorText: { color: colors.danger, fontSize: 11 },
  secondaryButton: { padding: 13, alignItems: 'center', borderRadius: 11, borderWidth: 1, borderColor: colors.border },
  secondaryButtonText: { color: colors.accent, fontSize: 12, fontWeight: '700' },
  disclaimer: { color: colors.subtle, fontSize: 10, lineHeight: 15, marginTop: 3 },
  historyRow: { flexDirection: 'row', alignItems: 'center', padding: 14, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, gap: 10 },
  historyDate: { color: colors.text, fontSize: 11, fontWeight: '700' },
  historySource: { color: colors.muted, fontSize: 10, marginTop: 5 },
  historyValues: { alignItems: 'flex-end', gap: 4 },
  historyMain: { color: colors.accent, fontSize: 12, fontWeight: '700' },
  historySub: { color: colors.muted, fontSize: 9 },
  fieldLabel: { color: colors.muted, fontSize: 10, fontWeight: '800', letterSpacing: 0.8, marginTop: 8 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 10, color: colors.text, paddingHorizontal: 13, paddingVertical: 12, fontSize: 13 },
  helper: { color: colors.subtle, fontSize: 10, lineHeight: 15 },
  segment: { flexDirection: 'row', backgroundColor: colors.surface, borderRadius: 11, padding: 4, borderWidth: 1, borderColor: colors.border, gap: 4 },
  segmentButton: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  segmentActive: { backgroundColor: colors.surfaceRaised },
  segmentText: { color: colors.muted, fontSize: 11, fontWeight: '600' },
  segmentTextActive: { color: colors.accent },
  demoNote: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, padding: 14, borderRadius: 12, gap: 8 },
  demoNoteTitle: { color: colors.text, fontSize: 13, fontWeight: '700' },
  configSummary: { padding: 14, backgroundColor: colors.surface, borderRadius: 12, gap: 5 },
  summaryLabel: { color: colors.subtle, fontSize: 9, fontWeight: '800', letterSpacing: 0.8, marginTop: 4 },
  summaryValue: { color: colors.text, fontSize: 12 },
  primaryButton: { backgroundColor: colors.accent, borderRadius: 11, padding: 14, alignItems: 'center' },
  primaryButtonText: { color: colors.background, fontSize: 12, fontWeight: '800' },
  tabBar: { flexDirection: 'row', backgroundColor: '#091A29', borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 8, paddingBottom: Platform.OS === 'ios' ? 24 : 28, minHeight: 72 },
  tabItem: { flex: 1, alignItems: 'center', gap: 4 },
  tabIcon: { width: 29, height: 25, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  tabIconActive: { backgroundColor: colors.accentDark },
  tabIconText: { color: colors.subtle, fontSize: 16, fontWeight: '700' },
  tabIconTextActive: { color: colors.accent },
  tabLabel: { color: colors.subtle, fontSize: 9, fontWeight: '600', flexShrink: 1, textAlign: 'center' },
  tabLabelActive: { color: colors.accent },
});

