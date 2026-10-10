// Burst statistics (ARCHITECTURE 4.6). Shared rule with the server
// (tidesvc.derive.median) and tests/vectors/stats_v1.json:
//   median of an even count = mean of the two middle values after sorting;
//   SD = population standard deviation (divide by N).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace tide {

constexpr size_t kBurstSamples = 300;
constexpr size_t kMinValidSamples = 30;
constexpr double kHighSdDeg = 0.25;
constexpr double kOutOfRangePitchDeg = 15.0;
constexpr double kOutOfRangeRollDeg = 10.0;

struct BurstStats {
  size_t n = 0;
  double pitch_median = 0;
  double pitch_sd = 0;
  double roll_mean = 0;
};

// Sorts `values` in place (n <= a few hundred: insertion-free std::sort).
double median_inplace(double* values, size_t n);

// pitch/roll: n samples. scratch: n doubles of workspace (pitch is not modified).
bool burst_stats(const double* pitch, const double* roll, size_t n, double* scratch, BurstStats* out);

// Flags from the burst: high_sd, out_of_range, short_sample, sensor_error.
// stats may be null when the sensor failed outright.
uint16_t sample_flags(const BurstStats* stats, size_t n_valid);

}  // namespace tide
