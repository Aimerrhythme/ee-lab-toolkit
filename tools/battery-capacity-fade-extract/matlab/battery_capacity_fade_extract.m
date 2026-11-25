function res = battery_capacity_fade_extract(csv_path, nominal_ah, n_early, eol_soh)
%BATTERY_CAPACITY_FADE_EXTRACT Per-cycle discharge capacity, SOH, early features.
%   res = battery_capacity_fade_extract(csv_path, nominal_ah, n_early, eol_soh)
%   CSV columns: cycle,time_s,current_a,voltage_v (discharge current negative).
%   Defaults: nominal_ah = first-cycle capacity, n_early = 100, eol_soh = 0.8.
%   res fields: cycles, capacity_ah, soh, nominal_ah, features (struct), eol_cycle (NaN if none).
if nargin < 2, nominal_ah = []; end
if nargin < 3 || isempty(n_early), n_early = 100; end
if nargin < 4 || isempty(eol_soh), eol_soh = 0.8; end
if ~(eol_soh > 0 && eol_soh < 1), error('eol_soh must be in (0,1)'); end
if n_early < 3, error('n_early must be >= 3'); end
T = readmatrix(csv_path, 'NumHeaderLines', 1);
if isempty(T) || size(T,2) < 4 || any(~isfinite(T(:))), error('bad CSV'); end
cyc = T(:,1); t = T(:,2); cur = T(:,3);
ks = unique(cyc)';
cycles = []; cap = [];
for k = ks
    m = (cyc == k) & (cur < 0);
    if sum(m) < 2, continue; end
    tk = t(m); ik = -cur(m);
    if any(diff(tk) <= 0), error('time not increasing in cycle %d', k); end
    cycles(end+1) = k; %#ok<AGROW>
    cap(end+1) = sum((ik(2:end) + ik(1:end-1)) / 2 .* diff(tk)) / 3600; %#ok<AGROW>
end
if numel(cycles) < 3, error('need discharge data for at least 3 cycles'); end
if isempty(nominal_ah), q_nom = cap(1); else, q_nom = nominal_ah; end
soh = cap / q_nom;
e = cycles <= cycles(1) + n_early - 1;
x = cycles(e); y = cap(e);
p = polyfit(x, y, 1);
f = struct('q_first', y(1), 'q_last_early', y(end), 'delta_q', y(end) - y(1), ...
    'q_mean', mean(y), 'q_std', std(y, 1), 'slope_ah_per_cycle', p(1), 'n_early', sum(e));
b = find(soh <= eol_soh, 1);
eol = NaN; if ~isempty(b), eol = cycles(b); end
res = struct('cycles', cycles, 'capacity_ah', cap, 'soh', soh, 'nominal_ah', q_nom, ...
    'features', f, 'eol_cycle', eol);
end

