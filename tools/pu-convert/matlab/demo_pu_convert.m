function demo_pu_convert()
%DEMO_PU_CONVERT Convert the synthetic quantity table and save a bar chart.
%   From this folder, call demo_pu_convert. The figure is written to
%   examples/output/pu_convert_demo_matlab.png (gitignored). Set
%   'show', true on the pu_convert call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_quantities.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'pu_convert_demo_matlab.png');
    outCsv = fullfile(outDir, 'pu_convert_demo_matlab.csv');
    result = pu_convert(csvPath, ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    fprintf('pu-convert: system=%s S_base=%s VA Z_hv=%s ohm Z_lv=%s ohm rows=%d\n', ...
        result.system, plain(result.s_base), plain(result.z_base_hv), ...
        plain(result.z_base_lv), numel(result.rows));
    fprintf('system=%s  S_base=%s VA (%s MVA)\n', result.system, ...
        plain(result.s_base), plain(result.s_base / 1e6));
    fprintf('%-6s %12s %12s %12s\n', 'side', 'V_base_V', 'I_base_A', 'Z_base_ohm');
    fprintf('%-6s %s %s %s\n', 'same', num(result.v_base), num(result.i_base), num(result.z_base));
    fprintf('%-6s %s %s %s\n', 'hv', num(result.v_base_hv), num(result.i_base_hv), num(result.z_base_hv));
    fprintf('%-6s %s %s %s\n', 'lv', num(result.v_base_lv), num(result.i_base_lv), num(result.z_base_lv));
    fprintf('\n');
    fprintf('%-18s %3s %6s %5s %5s %12s %8s %10s %12s %7s %12s %8s\n', ...
        'name', 'qty', 'dir', 'side', 'refer', 'value_in', 'unit_in', ...
        'pu', 'value_si', 'si_unit', 'value_out', 'unit_out');
    for index = 1:numel(result.rows)
        row = result.rows(index);
        if isempty(row.refer_to)
            refer = '-';
        else
            refer = row.refer_to;
        end
        if strcmp(row.unit_out, 'pu')
            valueOut = sprintf('%12.4f', row.value_out);
        else
            valueOut = num(row.value_out);
        end
        fprintf('%-18s %3s %6s %5s %5s %s %8s %10.4f %s %7s %s %8s\n', ...
            row.name, row.quantity, row.direction, row.side, refer, ...
            num(row.value_in), row.unit_in, row.value_pu, num(row.value_si), ...
            row.si_unit, valueOut, row.unit_out);
    end
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
end

function text = plain(value)
    text = compact_num(value);
end

function text = num(value)
    text = sprintf('%12s', compact_num(value));
end

function text = compact_num(value)
    % Short decimal text. Large integers stay in fixed point (100000000, not 1e+08).
    if ~isfinite(value)
        text = 'nan';
        return
    end
    text = sprintf('%.6g', value);
    if contains(lower(text), 'e')
        if abs(value - round(value)) <= 1e-6 * max(abs(value), 1)
            text = sprintf('%.0f', value);
        else
            text = sprintf('%.4f', value);
        end
    end
end
