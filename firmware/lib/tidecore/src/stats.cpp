#include "stats.h"

#include <math.h>

#include <algorithm>

#include "payload.h"

namespace tide {

double median_inplace(double* v, size_t n) {
  if (n == 0) return NAN;
  std::sort(v, v + n);
  if (n % 2) return v[n / 2];
  return (v[n / 2 - 1] + v[n / 2]) / 2.0;
}

bool burst_stats(const double* pitch, const double* roll, size_t n, double* scratch, BurstStats* out) {
  if (n == 0) return false;
  double sum = 0, rsum = 0;
  for (size_t i = 0; i < n; ++i) {
    scratch[i] = pitch[i];
    sum += pitch[i];
    rsum += roll[i];
  }
  const double mean = sum / static_cast<double>(n);
  double ss = 0;
  for (size_t i = 0; i < n; ++i) {
    const double d = pitch[i] - mean;
    ss += d * d;
  }
  out->n = n;
  out->pitch_sd = sqrt(ss / static_cast<double>(n));
  out->roll_mean = rsum / static_cast<double>(n);
  out->pitch_median = median_inplace(scratch, n);
  return true;
}

uint16_t sample_flags(const BurstStats* st, size_t n_valid) {
  if (st == nullptr || n_valid < kMinValidSamples) {
    return static_cast<uint16_t>(kFlagSensorError | (n_valid < kBurstSamples ? kFlagShortSample : 0));
  }
  uint16_t f = 0;
  if (n_valid < kBurstSamples) f |= kFlagShortSample;
  if (st->pitch_sd > kHighSdDeg) f |= kFlagHighSd;
  if (fabs(st->pitch_median) > kOutOfRangePitchDeg || fabs(st->roll_mean) > kOutOfRangeRollDeg) f |= kFlagOutOfRange;
  return f;
}

}  // namespace tide
