function demo_nilm_window_prep()
%DEMO_NILM_WINDOW_PREP Run the NILM window preparation on the synthetic CSV.
%   From this folder, call demo_nilm_window_prep. Outputs go to examples/output/
%   (gitignored). Prints the same summary lines as examples/run_demo.py.
    here = fileparts(mfilename('fullpath'));
    csvPath = fullfile(here, '..', 'examples', 'data', 'synthetic_meter.csv');
    outDir = fullfile(here, '..', 'examples', 'output');
    if exist(outDir, 'dir') ~= 7, mkdir(outDir); end
    res = nilm_window_prep(csvPath, 'step_s', 6, 'max_gap_steps', 3, ...
        'window', 11, 'stride', 3, ...
        'output_csv', fullfile(outDir, 'nilm_windows_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'nilm_window_prep_demo_matlab.png'));
    fprintf('bins=%d\n', res.n_bins);
    fprintf('empty_bins=%d\n', res.n_empty_bins);
    fprintf('filled=%d\n', res.n_filled);
    fprintf('candidates=%d\n', res.n_candidates);
    fprintf('windows=%d\n', res.n_windows);
    fprintf('dropped=%d\n', res.n_dropped);
    fprintf('y_mean_w=%.3f\n', mean(res.y));
    fprintf('outputs in %s\n', outDir);
end
