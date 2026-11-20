#include "measurement.h"
#include "config.h"
#include <math.h>
/* Buffer circular: espera 32 pares para alinhar tensao/corrente.
   Interpolacao linear corrige atraso de multiplexacao + ajuste de fase.
   E aproximada: altera resposta em alta frequencia; validar em cargas reais. */
bool measurement_push(measurement_t *s, double v, double i, result_t *r) {
    uint64_t k = s->pairs++;
    s->v[k % 128] = v;
    s->i[k % 128] = i;
    if (k < 64) return false;
    uint64_t center = k - 32;
    double shift = 0.5 + SENSOR_PHASE_SAMPLES;
    int whole = (int)floor(shift);
    double fraction = shift - whole;
    uint64_t a = (uint64_t)((int64_t)center + whole);
    double v0 = s->v[a % 128], v1 = s->v[(a + 1) % 128];
    v = v0 + fraction * (v1 - v0);
    i = s->i[center % 128];
    if (s->n == 0) {
        s->vmin = fmin(v0, v1); s->vmax = fmax(v0, v1);
        s->imin = s->imax = i;
    }
    s->vmin = fmin(s->vmin, fmin(v0, v1));
    s->vmax = fmax(s->vmax, fmax(v0, v1));
    s->imin = fmin(s->imin, i); s->imax = fmax(s->imax, i);
    bool vclip = v0 < RAW_LOW || v0 > RAW_HIGH || v1 < RAW_LOW || v1 > RAW_HIGH;
    bool iclip = i < RAW_LOW || i > RAW_HIGH;
    if (vclip) s->vclips++;
    if (iclip) s->iclips++;
    if (vclip || iclip) s->clips++;
    s->sv += v; s->si += i;
    s->svv += v*v; s->sii += i*i; s->svi += v*i;
    if (++s->n < WINDOW_PAIRS) return false;
    double mv = s->sv / s->n, mi = s->si / s->n;
    *r = (result_t){
        .vr = sqrt(fmax(0, s->svv / s->n - mv*mv)),
        .ir = sqrt(fmax(0, s->sii / s->n - mi*mi)),
        .covariance = s->svi / s->n - mv*mi,
        .vmean = mv, .imean = mi, .vmin = s->vmin, .vmax = s->vmax,
        .imin = s->imin, .imax = s->imax, .clips = s->clips,
        .vclips = s->vclips, .iclips = s->iclips
    };
    s->n = s->clips = s->vclips = s->iclips = 0;
    s->sv = s->si = s->svv = s->sii = s->svi = 0;
    return true;
}

