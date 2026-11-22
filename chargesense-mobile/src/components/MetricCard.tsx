import { StyleSheet, Text, View } from 'react-native';
import { colors } from '../theme/tokens';

type Props = { label: string; value: number | null | undefined; unit: string; precision?: number; accent?: string };
export function MetricCard({ label, value, unit, precision = 1, accent = colors.text }: Props) {
  const formatted = value == null || !Number.isFinite(value) ? '—' : value.toFixed(precision);
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={[styles.value, { color: accent }]}>{formatted}</Text>
        <Text style={styles.unit}>{unit}</Text>
      </View>
    </View>
  );
}
const styles = StyleSheet.create({
  card: { flex: 1, minHeight: 104, padding: 16, borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, justifyContent: 'space-between' },
  label: { color: colors.muted, fontSize: 12, fontWeight: '600', letterSpacing: 0.5 },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
  value: { fontSize: 27, fontWeight: '700', letterSpacing: -0.8 },
  unit: { color: colors.muted, fontSize: 12 },
});
