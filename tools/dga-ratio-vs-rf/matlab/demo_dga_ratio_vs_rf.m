function demo_dga_ratio_vs_rf()
%DEMO_DGA_RATIO_VS_RF Compare the IEC ratio rule and a random forest on synthetic DGA data.
%   From this folder, call demo_dga_ratio_vs_rf. Outputs go to
%   examples/output/ (gitignored). Set 'show', true below to keep the figure.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_dga_ppm.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    result = dga_ratio_vs_rf(csvPath, ...
        'n_trees', 50, 'max_depth', 6, 'mtry', 2, 'seed', 0, ...
        'output_csv', fullfile(outDir, 'dga_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'dga_demo_matlab.png'), ...
        'show', false);
    for i = 1:numel(result.sample_ids)
        if strcmp(result.split{i}, 'test')
            fprintf('dga: id=%s true=%s rule=%s rf=%s rf_prob=%.3f\n', result.sample_ids{i}, ...
                result.true_label{i}, result.rule_label{i}, result.rf_label{i}, result.rf_prob(i));
        end
    end
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_csv);
    fprintf('saved %s\n', result.output_png);
end
