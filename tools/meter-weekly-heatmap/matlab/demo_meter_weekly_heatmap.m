function demo_meter_weekly_heatmap()
%DEMO_METER_WEEKLY_HEATMAP Week x weekday heatmaps for the synthetic meters.
%   From this folder, call demo_meter_weekly_heatmap. Output goes to
%   examples/output/ (gitignored); the printed table should match run_demo.py.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    outDir = fullfile(toolDir, 'examples', 'output');
    res = meter_weekly_heatmap(fullfile(toolDir, 'examples', 'data', 'synthetic_meters.csv'), ...
        'output_dir', fullfile(outDir, 'meter_weekly_heatmap_matlab'), ...
        'output_png', fullfile(outDir, 'meter_weekly_heatmap_demo_matlab.png'));
    fprintf('meter-weekly-heatmap: customers=%d weeks=%d\n', numel(res.customers), res.n_weeks);
    fprintf('id    label    observed filled missing miss_rate wkend/wkday\n');
    for c = res.customers
        fprintf('%-5s %-8s %8d %6d %7d %9.3f %11.3f\n', c.customer_id, c.label, ...
            c.n_observed, c.n_filled, c.n_missing, c.missing_rate, c.weekend_ratio);
    end
end
