#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "measurement.h"
#include "config.h"
#define PI 3.14159265358979323846
static void sine_test(double angle) {
    measurement_t s = {0}; result_t r = {0}; unsigned windows = 0;
    for (unsigned n=0;n<30064;n++) {
        double t = (double)n / PAIR_RATE;
        double v = 1700 + 600*sin(2*PI*60*t);
        double i = 2100 + 300*sin(2*PI*60*(t+0.5/PAIR_RATE)-angle);
        if (measurement_push(&s,v,i,&r)) {
            windows++;
            assert(fabs(r.vr-600/sqrt(2)) < 0.1);
            assert(fabs(r.ir-300/sqrt(2)) < 0.01);
            assert(fabs(r.covariance/(r.vr*r.ir)-cos(angle)) < 0.0001);
            assert(r.clips == 0);
        }
    }
    assert(windows == 3);
}
int main(void) {
    sine_test(0); sine_test(PI/3); sine_test(PI);
    measurement_t s = {0}; result_t r = {0};
    for (unsigned n=0;n<WINDOW_PAIRS+64;n++) measurement_push(&s,1700,2000,&r);
    assert(r.vr == 0 && r.ir == 0 && r.covariance == 0);
    s = (measurement_t){0};
    for (unsigned n=0;n<WINDOW_PAIRS+64;n++) measurement_push(&s,4095,0,&r);
    assert(r.clips == WINDOW_PAIRS);
    puts("PASS: RMS, offset, fase 0/60/180 graus, continuidade e recorte.");
}
