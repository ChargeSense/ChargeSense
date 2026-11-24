from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

NonNegative = Annotated[FiniteFloat, Field(ge=0, le=100000)]


class Measurements(BaseModel):
    model_config = ConfigDict(extra='forbid')
    voltageV: NonNegative | None = None
    currentA: NonNegative | None = None
    activePowerW: Annotated[FiniteFloat, Field(ge=-10000000, le=10000000)] | None = None
    panelTempC: Annotated[FiniteFloat, Field(ge=-100, le=200)] | None = None


class Telemetry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schemaVersion: Literal[1]
    stationId: Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')]
    bootId: UUID
    sequence: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
    source: Literal['sensor', 'simulated']
    measuredAt: datetime | None = None
    uptimeMs: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
    quality: Literal['valid', 'uncalibrated', 'invalid']
    measurements: Measurements

    @field_validator('measuredAt', mode='wrap')
    @classmethod
    def tolerate_simulator_clock(cls, value, handler, info):
        if info.data.get('source') != 'simulated':
            return handler(value)
        try:
            parsed = handler(value)
        except ValueError:
            return None
        if parsed is not None and (parsed.tzinfo is None or parsed.utcoffset() is None):
            return None
        return parsed

    @model_validator(mode='after')
    def check_semantics(self):
        if self.measuredAt is not None:
            if self.measuredAt.tzinfo is None or self.measuredAt.utcoffset() is None:
                raise ValueError('measuredAt deve incluir fuso horario')
            self.measuredAt = self.measuredAt.astimezone(timezone.utc)
        populated = [v for v in self.measurements.model_dump().values() if v is not None]
        if self.quality != 'valid' and populated:
            raise ValueError('Medicoes invalidas/nao calibradas devem ser null')
        if self.quality == 'valid' and not populated:
            raise ValueError('Leitura valida exige ao menos uma grandeza')
        if self.measurements.activePowerW is not None and (
            self.measurements.voltageV is None or self.measurements.currentA is None
        ):
            raise ValueError('Potencia exige tensao e corrente validas')
        return self

