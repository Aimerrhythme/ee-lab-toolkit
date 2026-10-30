function demo_pv_daily_features()
%DEMO_PV_DAILY_FEATURES Clear, cloud, and flicker PV daily features.
%   From this folder, call demo_pv_daily_features. The figure is written to
%   examples/output/pv_daily_features_demo_matlab.png (gitignored). Set
%   'show', true on the pv_daily_features call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_pv_kw.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'pv_daily_features_demo_matlab.png');
    outCsv = fullfile(outDir, 'pv_daily_features_demo_matlab.csv');
    result = pv_daily_features(csvPath, ...
        'p_rated_kw', 100, ...
        'ramp_minutes', 10, ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    for index = 1:numel(result.days)
        item = result.days(index);
        fprintf(['pv-daily-features: date=%s Ppeak=%.4f t_peak=%s ', ...
            'E=%.4f VI=%.6f ramp_up=%.4f ramp_down=%.4f\n'], ...
            item.date, item.p_peak_kw, item.t_peak, item.energy_kwh, ...
            item.variability_index, item.ramp_up_kw_per_min, item.ramp_down_kw_per_min);
    end
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
end
