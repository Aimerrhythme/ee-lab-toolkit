function demo_epf_naive_baselines()
%DEMO_EPF_NAIVE_BASELINES Score previous-day / previous-week naive forecasts.
%   From this folder, call demo_epf_naive_baselines. Outputs go to
%   examples/output/ (gitignored). Same summary lines as examples/run_demo.py.
    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_day_ahead_price.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    result = epf_naive_baselines(csvPath, 'eval_start_day', 7, ...
        'output_csv', fullfile(outDir, 'epf_naive_baselines_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'epf_naive_baselines_demo_matlab.png'), ...
        'show', false);
    fprintf('eval_days=%d\n', result.n_eval_days);
    fprintf('model,mae,smape_pct,rmse\n');
    for m = 1:2
        s = result.metrics.(result.models{m});
        fprintf('%s,%.4f,%.4f,%.4f\n', result.models{m}, s.mae, s.smape_pct, s.rmse);
    end
    fprintf('outputs in %s\n', outDir);
end
