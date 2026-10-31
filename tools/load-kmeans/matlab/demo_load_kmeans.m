function demo_load_kmeans()
%DEMO_LOAD_KMEANS Cluster synthetic commercial, residential, and weekend days.
%   From this folder, call demo_load_kmeans. The figure is written to
%   examples/output/load_kmeans_demo_matlab.png (gitignored). Set 'show', true
%   on the load_kmeans call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_load_kw.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'load_kmeans_demo_matlab.png');
    outCsv = fullfile(outDir, 'load_kmeans_demo_matlab.csv');
    result = load_kmeans(csvPath, ...
        'k', 3, ...
        'seed', 0, ...
        'normalize', 'peak', ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    for index = 1:numel(result.dates)
        fprintf('load-kmeans: date=%s label=%d peak_kw=%.4f day_sse=%.6f\n', ...
            result.dates{index}, result.labels(index), result.peak_kw(index), result.day_sse(index));
    end
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
end
