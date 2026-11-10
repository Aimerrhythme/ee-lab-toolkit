function demo_pmu_iforest()
%DEMO_PMU_IFOREST Flag glitches in the synthetic PMU stream with an Isolation Forest.
%   From this folder, call demo_pmu_iforest. Outputs go to examples/output/ (gitignored).
%   Set 'show', true below to keep the figure window.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_pmu.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    r = pmu_iforest(csvPath, 'n_trees', 100, 'contamination', 0.03, 'seed', 0, ...
        'output_csv', fullfile(outDir, 'pmu_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'pmu_demo_matlab.png'), 'show', false);
    fprintf('flagged times (s): %s\n', sprintf('%.3f ', r.anomaly_times));
    fprintf('%s\n', r.summary);
    fprintf('saved %s\n', r.output_csv);
    fprintf('saved %s\n', r.output_png);
end
