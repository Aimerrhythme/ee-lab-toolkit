# Changelog

All notable tools and breaking changes are listed here.

## [Unreleased]

### Added

- Tool `bess-tou-qlearn-toy`: tabular Q-learning (deterministic full-sweep training) for a battery on a synthetic hourly TOU tariff over an hour × SOC grid, compared with a threshold-greedy policy on one-day net cost and exported as a schedule CSV, in Python (numpy/matplotlib) and base MATLAB.
- Tool `evcs-load-window`: clean EV charging-session records (bad times, missing/zero/over-limit power), resample to a time-weighted station load, and cut input/target windows exported as CSV, in Python (numpy/pandas/matplotlib) and base MATLAB.
- Tool `pmu-iforest-demo`: hand-written Isolation Forest on a synthetic 30 fps PMU stream (voltage magnitude, angle, frequency) with frame-to-frame features, contamination-based flagging, anomaly timestamps, and a three-panel figure, in Python (numpy/matplotlib) and base MATLAB.
- Tool `dga-ratio-vs-rf`: compare a simplified IEC 60599 three-ratio rule with a hand-written random forest on synthetic dissolved-gas samples — test-set confusion matrices (rule has an ND outcome) and gas feature importance — in Python (numpy/matplotlib) and base MATLAB.
- Tool `load-curve-dnn-fit`: fit one typical daily load curve with a configurable polynomial and a shallow tanh MLP (1-hidden-1, full-batch Adam), after peak or min-max normalization, and compare RMSE, MAE, and maximum absolute error in kW, in Python and base MATLAB.
- Tool `pp-fault-synth-export`: batch short-circuit samples on a radial MV feeder, with phase voltages and currents plus protection labels (AG/BG/CG, AB/BC/CA, ABC), exported as one CSV schema in Python and base MATLAB. Pandapower CIGRE-MV is an optional engine with the same columns.
- Tool `simulink-param-export`: CSV convention for Simulink block, mask, model, and workspace parameters (name, value, unit, description, scope, path, dtype, bounds, group), with validation and a canonical round trip, in Python (stdlib) and base MATLAB. Simulink is not required.
- Tool `bode-demo`: Bode magnitude (dB) and phase (deg) of a transfer function on a log frequency grid, with gain and phase margins and crossover frequencies, for a first-order lag, a second-order damping sweep, and a filtered PID/plant loop, in Python (numpy/scipy/matplotlib) and base MATLAB.
- Tool `short-circuit-mva`: convert short-circuit MVA, fault current, and impedance, and combine source, transformer, and line stages by the MVA method (series reciprocal, parallel sum), with an X/R phasor check, in Python and base MATLAB.
- Tool `voltage-drop`: approximate feeder voltage drop for one section or a radial multi-section line, from R/X and P/Q or I/pf, with percent drop and a sending-to-receiving voltage profile, in Python and base MATLAB.
- Tool `load-kmeans`: cluster typical daily load profiles with peak-normalized k-means — per-day labels, centroids, within-cluster SSE, and silhouette — in Python and base MATLAB.
- Tool `pv-daily-features`: daily PV features from a power time series — peak power and time, energy, capacity factor, daylight window, step and window ramps, and a variability index — in Python and base MATLAB.
- Tool `motor-torque-speed`: torque-speed curves for a three-phase induction motor from its per-phase equivalent circuit (slip sweep, starting torque, breakdown torque and slip, rated point) and for DC separately excited, shunt, and series motors, with parameter comparisons, in Python and base MATLAB.
- Tool `pwm-waveform`: sine-triangle PWM (bipolar and unipolar) with carrier and modulation index, gate and bridge-voltage waveforms, and a linear-range fundamental / full-band THD check, in Python and base MATLAB.
- Tool `fft-thd`: single-sided amplitude spectrum, fundamental detection, per-harmonic amplitude and percent, and THD for a sampled waveform, with windowing and a least-squares fit for non-integer cycles, in Python and base MATLAB.
- Tool `pu-convert`: convert V, I, S/P/Q, and Z/R/X between SI (named) values and per-unit on a shared power base, including two-winding impedance referral, in Python and base MATLAB.
- Tool `pid-step-compare`: compare PID step responses on a simple plant and report rise time, overshoot, settling time, and steady-state error in Python and base MATLAB.
- Tool `load-csv-plot`: clean a timestamped load CSV (missing values, spike flags, optional daily mean) and save a standard figure in Python and MATLAB.
- Repository scaffold, dual-runtime conventions, and theme queue for daily tools.
