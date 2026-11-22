import type { DataSource, Page, StationEvent, StationStatus, TelemetryReading } from '../types/telemetry';

export type ApiConfig = {
  baseUrl: string;
  readKey: string;
  stationId: string;
  source: DataSource;
};

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = 'ApiError';
  }
}

function cleanBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, '');
}

async function request<T>(config: ApiConfig, path: string): Promise<T> {
  const baseUrl = cleanBaseUrl(config.baseUrl);
  if (!baseUrl) throw new ApiError('Informe o endereço do backend local.');
  if (!config.readKey.trim()) throw new ApiError('Informe a chave de leitura da API.');
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      headers: { 'X-API-Key': config.readKey.trim(), Accept: 'application/json' },
    });
  } catch {
    throw new ApiError('Não foi possível alcançar o backend. Confira o endereço, a rede e se a API está iniciada.');
  }
  if (!response.ok) {
    const message = response.status === 401
      ? 'Chave de leitura inválida.'
      : response.status === 404
        ? 'Ainda não há dados para esta estação e origem.'
        : `O backend respondeu com erro (${response.status}).`;
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

function stationPath(config: ApiConfig): string {
  return `/api/v1/stations/${encodeURIComponent(config.stationId)}`;
}

export const chargesenseApi = {
  latest: (config: ApiConfig) =>
    request<TelemetryReading>(config, `${stationPath(config)}/latest?source=${config.source}`),
  status: (config: ApiConfig) =>
    request<StationStatus>(config, `${stationPath(config)}/status?source=${config.source}`),
  history: (config: ApiConfig) =>
    request<Page<TelemetryReading>>(config, `${stationPath(config)}/readings?source=${config.source}&limit=30`),
  events: (config: ApiConfig) =>
    request<Page<StationEvent>>(config, `${stationPath(config)}/events?source=${config.source}&limit=30`),
};
