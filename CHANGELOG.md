# Changelog

All notable tools and breaking changes are listed here.

## [Unreleased]

### Added

- Tool `load-kmeans`: cluster typical daily load profiles with peak-normalized k-means — per-day labels, centroids, within-cluster SSE, and silhouette — in Python and base MATLAB.
- Tool `pv-daily-features`: daily PV features from a power time series — peak power and time, energy, capacity factor, daylight window, step and window ramps, and a variability index — in Python and base MATLAB.
- Tool `motor-torque-speed`: torque-speed curves for a three-phase induction motor from its per-phase equivalent circuit (slip sweep, starting torque, breakdown torque and slip, rated point) and for DC separately excited, shunt, and series motors, with parameter comparisons, in Python and base MATLAB.
- Tool `pwm-waveform`: sine-triangle PWM (bipolar and unipolar) with carrier and modulation index, gate and bridge-voltage waveforms, and a linear-range fundamental / full-band THD check, in Python and base MATLAB.
- Tool `fft-thd`: single-sided amplitude spectrum, fundamental detection, per-harmonic amplitude and percent, and THD for a sampled waveform, with windowing and a least-squares fit for non-integer cycles, in Python and base MATLAB.
- Tool `pu-convert`: convert V, I, S/P/Q, and Z/R/X between SI (named) values and per-unit on a shared power base, including two-winding impedance referral, in Python and base MATLAB.
- Tool `pid-step-compare`: compare PID step responses on a simple plant and report rise time, overshoot, settling time, and steady-state error in Python and base MATLAB.
- Tool `load-csv-plot`: clean a timestamped load CSV (missing values, spike flags, optional daily mean) and save a standard figure in Python and MATLAB.
- Repository scaffold, dual-runtime conventions, and theme queue for daily tools.
