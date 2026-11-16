#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    double v[128], i[128];
    uint64_t pairs;
    unsigned n, clips, vclips, iclips;
    double sv, si, svv, sii, svi;
    double vmin, vmax, imin, imax;
} measurement_t;
typedef struct {
    double vr, ir, covariance, vmean, imean;
    double vmin, vmax, imin, imax;
    unsigned clips, vclips, iclips;
} result_t;
bool measurement_push(measurement_t *s, double v, double i, result_t *r);

