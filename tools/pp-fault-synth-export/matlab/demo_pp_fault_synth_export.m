function demo_pp_fault_synth_export()
%DEMO_PP_FAULT_SYNTH_EXPORT Radial feeder short-circuit samples and labels.
%   From this folder, call demo_pp_fault_synth_export. The figure is written
%   to examples/output/pp_fault_synth_export_demo_matlab.png (gitignored).
%   Set 'show', true on the call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_radial_feeder.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'pp_fault_synth_export_demo_matlab.png');
    outCsv = fullfile(outDir, 'pp_fault_synth_export_demo_matlab.csv');

    result = pp_fault_synth_export(csvPath, ...
        'engine', 'zbus', ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    fprintf('%s\n', result.preview);
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
end
