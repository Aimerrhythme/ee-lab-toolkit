function demo_pv_clearsky_index()
%DEMO_PV_CLEARSKY_INDEX Classify the synthetic days by clear-sky index.
%   From this folder, call demo_pv_clearsky_index. Same summary lines as
%   examples/run_demo.py; outputs go to examples/output/ (gitignored).
    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    outDir = fullfile(toolDir, 'examples', 'output');
    r = pv_clearsky_index(fullfile(toolDir, 'examples', 'data', 'synthetic_ghi.csv'), ...
        'lat', 25, 'output_csv', fullfile(outDir, 'clearsky_index_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'clearsky_index_demo_matlab.png'), 'show', false);
    fprintf('days=%d clear=%d cloudy=%d overcast=%d\n', r.n_days, ...
        r.counts.clear, r.counts.cloudy, r.counts.overcast);
    fprintf('kt=%s\n', strjoin(compose('%.3f', r.kt'), ','));
    fprintf('types=%s\n', strjoin(r.sky_type, ','));
    fprintf('outputs in %s\n', outDir);
end
