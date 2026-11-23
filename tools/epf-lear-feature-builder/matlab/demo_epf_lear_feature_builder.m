function demo_epf_lear_feature_builder()
%DEMO_EPF_LEAR_FEATURE_BUILDER Build the LEAR feature matrix for the synthetic CSV.
%   From this folder, call demo_epf_lear_feature_builder. Same summary lines as
%   examples/run_demo.py; outputs go to examples/output/ (gitignored).
    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_price_load.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    r = epf_lear_feature_builder(csvPath, 'lags', [1 2 3 7], ...
        'output_csv', fullfile(outDir, 'lear_features_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'lear_features_demo_matlab.png'), 'show', false);
    fprintf('rows=%d features=%d lags=%s\n', r.n_rows, r.n_features, strjoin(string(r.lags), ','));
    fprintf('first_target=%s last_target=%s\n', r.target_dates{1}, r.target_dates{end});
    fprintf('X_sum=%.4f y_mean=%.4f\n', sum(r.X(:)), mean(r.y(:)));
    fprintf('first_row_head=%s\n', strjoin(compose('%.2f', r.X(1, 1:4)), ','));
    fprintf('outputs in %s\n', outDir);
end
