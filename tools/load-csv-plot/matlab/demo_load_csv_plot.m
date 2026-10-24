function demo_load_csv_plot()
%DEMO_LOAD_CSV_PLOT Run load-csv-plot on the synthetic three-day load CSV.
%   From this folder, call demo_load_csv_plot. The figure is written to
%   examples/output/load_csv_plot_demo_matlab.png (gitignored). Set
%   'show', true on the load_csv_plot call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_load_kw.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'load_csv_plot_demo_matlab.png');
    result = load_csv_plot(csvPath, ...
        'agg', 'daily_mean', ...
        'outlier_method', 'iqr', ...
        'fill_method', 'interpolate', ...
        'output_png', outPng, ...
        'show', false);
    fprintf('load-csv-plot: rows=%d missing=%d outliers=%d mean=%.2f kW\n', ...
        result.n_rows, result.n_missing, result.n_outliers, result.mean_kw);
    fprintf(['planted defects: 2024-06-01 04:00 missing, ', ...
        '2024-06-02 12:00 = 950 kW, 2024-06-03 18:00 = 5 kW\n']);
    fprintf('saved %s\n', result.output_png);
    disp(result.daily_mean);
end
