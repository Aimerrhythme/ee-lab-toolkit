function demo_voltage_drop()
%DEMO_VOLTAGE_DROP One section and a four-section synthetic feeder.
%   From this folder, call demo_voltage_drop. The figure is written to
%   examples/output/voltage_drop_demo_matlab.png (gitignored). Set
%   'show', true on the feeder voltage_drop call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_feeder_sections.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'voltage_drop_demo_matlab.png');
    outCsv = fullfile(outDir, 'voltage_drop_demo_matlab.csv');

    single = voltage_drop('length_km', 2.0, 'r_ohm_per_km', 0.4, ...
        'x_ohm_per_km', 0.35, 'i_a', 80, 'pf', 0.8, 'v_nominal', 10000);
    row = single.sections(1);
    fprintf('voltage-drop single: dV=%.4f V (%.4f %%) I=%.3f A pf=%.4f V_recv=%.4f V\n', ...
        row.delta_v, row.delta_v_percent, row.i_a, row.pf, row.v_recv);

    result = voltage_drop(csvPath, ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
end
