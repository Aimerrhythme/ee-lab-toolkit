function demo_bode_demo()
%DEMO_BODE_DEMO Bode plots for the sample systems in examples/data/systems.csv.
%   From this folder, call demo_bode_demo. Figures are written to
%   examples/output/bode_demo_*_matlab.png (gitignored). Set 'show', true
%   on a bode_demo call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'systems.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end

    groups = { ...
        'first-order', {'tau=1', 'tau=0.2'}, 'bode_demo_first_order_matlab.png'; ...
        'damping sweep', {'zeta=0.2', 'zeta=0.5', 'zeta=0.707', 'zeta=1', 'zeta=1.5'}, ...
            'bode_demo_damping_matlab.png'; ...
        'PID/plant open loop', {'P', 'PI', 'PID'}, 'bode_demo_pid_loop_matlab.png'; ...
        'textbook margins', {'textbook'}, 'bode_demo_textbook_matlab.png' ...
    };
    for index = 1:size(groups, 1)
        png = fullfile(outDir, groups{index, 3});
        result = bode_demo(csvPath, 'names', groups{index, 2}, 'output_png', png, 'show', false);
        fprintf('bode-demo %s: n=%d w=[%.6g, %.6g]\n', ...
            groups{index, 1}, result.n_points, result.w_min, result.w_max);
        for row = 1:numel(result.margins)
            item = result.margins(row);
            fprintf('  %s: num=[%s] den=[%s]\n', item.name, coeff_text(item.num), coeff_text(item.den));
        end
        fprintf('%s\n', format_margins_table(result.margins));
        fprintf('saved %s\n', result.output_png);
    end
end

function text = format_margins_table(margins)
    lines = cell(1, numel(margins) + 1);
    lines{1} = sprintf('%-16s %-14s %10s %10s %10s %10s', ...
        'name', 'form', 'w_gc', 'PM_deg', 'w_pc', 'GM_dB');
    for index = 1:numel(margins)
        row = margins(index);
        lines{index + 1} = sprintf('%-16s %-14s %s %s %s %s', ...
            row.name, row.form, ...
            fmt_freq(row.phase_margin_rad_s), fmt_margin(row.phase_margin_deg), ...
            fmt_freq(row.gain_margin_rad_s), fmt_margin(row.gain_margin_db));
    end
    text = strjoin(lines, newline);
end

function text = fmt_freq(value)
    special = fmt_special(value);
    if ~isempty(special)
        text = sprintf('%10s', special);
        return
    end
    text = sprintf('%10.4g', value);
end

function text = fmt_margin(value)
    special = fmt_special(value);
    if ~isempty(special)
        text = sprintf('%10s', special);
        return
    end
    text = sprintf('%10.4f', value);
end

function text = fmt_special(value)
    if isnan(value)
        text = 'nan';
    elseif isinf(value)
        if value > 0
            text = 'inf';
        else
            text = '-inf';
        end
    else
        text = '';
    end
end

function text = coeff_text(coeff)
    parts = strings(1, numel(coeff));
    for index = 1:numel(coeff)
        parts(index) = string(sprintf('%g', coeff(index)));
    end
    text = char(strjoin(parts, ', '));
end
