import { StyleSheet, Text, View } from 'react-native';
import { colors } from '../theme/tokens';
import type { ConnectionState } from '../types/telemetry';

const labels: Record<ConnectionState, string> = { online: 'Conectada', offline: 'Sem comunicação', never_seen: 'Aguardando dados' };
const tones: Record<ConnectionState, { bg: string; dot: string }> = {
  online: { bg: colors.successSurface, dot: colors.success },
  offline: { bg: colors.dangerSurface, dot: colors.danger },
  never_seen: { bg: colors.warningSurface, dot: colors.warning },
};
export function StatusPill({ state }: { state: ConnectionState }) {
  const tone = tones[state];
  return <View style={[styles.pill, { backgroundColor: tone.bg }]}><View style={[styles.dot, { backgroundColor: tone.dot }]} /><Text style={[styles.label, { color: tone.dot }]}>{labels[state]}</Text></View>;
}
const styles = StyleSheet.create({
  pill: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 7, borderRadius: 99, paddingHorizontal: 11, paddingVertical: 7 },
  dot: { width: 7, height: 7, borderRadius: 9 },
  label: { fontSize: 12, fontWeight: '700' },
});
