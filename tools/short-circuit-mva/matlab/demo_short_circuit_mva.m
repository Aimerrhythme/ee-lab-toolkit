function demo_short_circuit_mva()
%DEMO_SHORT_CIRCUIT_MVA One point, one transformer, and a four-stage feeder.
%   From this folder, call demo_short_circuit_mva. The figure is written to
%   examples/output/short_circuit_mva_demo_matlab.png (gitignored). Set
%   'show', true on the network short_circuit_mva call below to leave the
%   window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_short_circuit_stages.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'short_circuit_mva_demo_matlab.png');
    outCsv = fullfile(outDir, 'short_circuit_mva_demo_matlab.csv');

    single = short_circuit_mva('s_mva', 250, 'v_kv', 10);
    fprintf(['short-circuit-mva single: S=%.4f MVA  I=%.4f kA  ', ...
        'Z=%.4f ohm  z_pu=%.4f pu  X/R=%s\n'], ...
        single.s_mva, single.i_ka, single.z_ohm, single.z_pu, xr_text(single.x_over_r));

    fromCurrent = short_circuit_mva('i_ka', 10, 'v_kv', 10);
    fprintf(['short-circuit-mva single: S=%.4f MVA  I=%.4f kA  ', ...
        'Z=%.4f ohm  z_pu=%.4f pu  X/R=%s\n'], ...
        fromCurrent.s_mva, fromCurrent.i_ka, fromCurrent.z_ohm, ...
        fromCurrent.z_pu, xr_text(fromCurrent.x_over_r));

    transformer = short_circuit_mva('kind', 'transformer', ...
        's_rated_mva', 20, 'z_percent', 8, 'x_over_r', 10, 'v_kv', 10);
    fprintf(['short-circuit-mva single: S=%.4f MVA  I=%.4f kA  ', ...
        'Z=%.4f ohm  z_pu=%.4f pu  X/R=%s\n'], ...
        transformer.s_mva, transformer.i_ka, transformer.z_ohm, ...
        transformer.z_pu, xr_text(transformer.x_over_r));

    result = short_circuit_mva(csvPath, ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
end

function text = xr_text(value)
    if isnan(value)
        text = 'nan';
    elseif isinf(value)
        if value < 0
            text = '-inf';
        else
            text = 'inf';
        end
    else
        text = sprintf('%.4f', value);
    end
end
