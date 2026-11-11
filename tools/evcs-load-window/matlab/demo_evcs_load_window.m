function demo_evcs_load_window()
%DEMO_EVCS_LOAD_WINDOW Run evcs-load-window on the synthetic session CSV.
%   From this folder, call demo_evcs_load_window. Outputs go to
%   examples/output/ (gitignored).

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_sessions.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    r = evcs_load_window(csvPath, 'output_csv', fullfile(outDir, 'windows_matlab.csv'));
    fprintf(['evcs-load-window: sessions=%d dropped=%d bins=%d windows=%d ', ...
        'X=(%d, %d) y=(%d, %d) peak=%.2f kW\n'], ...
        r.n_sessions, r.n_dropped, numel(r.load_kw), size(r.X, 1), ...
        size(r.X, 1), size(r.X, 2), size(r.y, 1), size(r.y, 2), max(r.load_kw));
    fprintf('planted defects: 4 bad rows (end<=start, missing power, 0 kW, 900 kW)\n');
    fig = figure('Visible', 'off');
    stairs(r.time, r.load_kw);
    xlabel('time'); ylabel('station load (kW)');
    title('Synthetic EVCS load, 15-min bins');
    png = fullfile(outDir, 'evcs_load_window_demo_matlab.png');
    saveas(fig, png);
    close(fig);
    fprintf('saved %s\nsaved %s\n', png, r.output_csv);
end
