function demo_wind_curve_binning_filter()
%DEMO_WIND_CURVE_BINNING_FILTER Clean the synthetic wind-power scatter.
%   From this folder, call demo_wind_curve_binning_filter. Outputs go to
%   examples/output/ (gitignored). Set 'show', true below to keep the figure.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_wind_power.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    result = wind_curve_binning_filter(csvPath, ...
        'bin_width', 0.5, 'v_min', 0, 'v_cut_in', 3, 'v_rated', 12, ...
        'v_cut_out', 25, 'p_rated_kw', 2000, ...
        'output_csv', fullfile(outDir, 'wind_curve_binning_filter_demo_matlab.csv'), ...
        'output_bins_csv', fullfile(outDir, 'wind_curve_binning_filter_demo_matlab_bins.csv'), ...
        'output_png', fullfile(outDir, 'wind_curve_binning_filter_demo_matlab.png'), ...
        'show', false);
    rated = [];
    for i = 1:numel(result.bins)
        if abs(result.bins(i).v_left - 12) < 1e-9
            rated = result.bins(i);
            break
        end
    end
    fprintf('%s\n', result.summary);
    fprintf(['bin v=[12,12.5) n_raw=%d n_clean=%d ' ...
        'median_clean_kw=%.4f q1_kw=%.4f q3_kw=%.4f theory_kw=%.4f\n'], ...
        rated.n_raw, rated.n_clean, rated.median_clean_kw, ...
        rated.q1_kw, rated.q3_kw, rated.theory_kw);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
    fprintf('saved %s\n', result.output_bins_csv);
end
