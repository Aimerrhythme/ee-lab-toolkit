% Demo: capacity fade extraction on the shared synthetic CSV.
here = fileparts(mfilename('fullpath'));
csv = fullfile(here, '..', 'examples', 'data', 'synthetic_cycles.csv');
r = battery_capacity_fade_extract(csv);
fprintf('cycles=%d q0=%.3fAh qEnd=%.3fAh soh_end=%.3f slope=%.5fAh/cycle eol=%g\n', ...
    numel(r.cycles), r.capacity_ah(1), r.capacity_ah(end), r.soh(end), ...
    r.features.slope_ah_per_cycle, r.eol_cycle);
figure; yyaxis left; plot(r.cycles, r.capacity_ah, '.-'); ylabel('discharge capacity (Ah)');
yyaxis right; plot(r.cycles, r.soh, 'r'); ylabel('SOH'); xlabel('cycle');
title('Capacity fade');

