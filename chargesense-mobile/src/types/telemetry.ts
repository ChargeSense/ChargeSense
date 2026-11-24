export type DataSource = 'sensor' | 'simulated';
export type ConnectionState = 'online' | 'offline' | 'never_seen';
export type FreshnessState = 'fresh' | 'stale' | 'unknown';
export type QualityState = 'valid' | 'uncalibrated' | 'invalid';

export type Measurements = {
  voltageV: number | null;
  currentA: number | null;
  activePowerW: number | null;
  panelTempC: number | null;
};

export type TelemetryReading = {
  id: number;
  schemaVersion: 1;
  stationId: string;
  bootId: string;
  sequence: number;
  source: DataSource;
  measuredAt: string | null;
  receivedAt: string;
  uptimeMs: number;
  quality: QualityState;
  measurements: Measurements;
};

export type StationStatus = {
  stationId: string;
  source: DataSource;
  connection: ConnectionState;
  lastReceivedAt: string | null;
  secondsSinceReception: number | null;
  measurementAgeSeconds: number | null;
  freshness: FreshnessState;
  quality: QualityState | null;
  thresholdsConfigured: boolean;
};

export type StationEvent = {
  id: number;
  readingId: number;
  kind: string;
  value?: number | null;
  threshold?: number | null;
  unit?: string | null;
  level: 'normal' | 'diagnostic' | 'attention' | 'alert' | 'critical';
  receivedAt: string;
};

export type Page<T> = { items: T[]; nextBeforeId: number | null };

