function demo_pid_step_compare()
%DEMO_PID_STEP_COMPARE Compare the sample P, PI, and PID step responses.
%   From this folder, call demo_pid_step_compare. The figure is written to
%   examples/output/pid_step_compare_demo_matlab.png (gitignored). Set
%   'show', true on the pid_step_compare call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    plantCsv = fullfile(toolDir, 'examples', 'data', 'plant.csv');
    pidCsv = fullfile(toolDir, 'examples', 'data', 'pid_sets.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'pid_step_compare_demo_matlab.png');
    result = pid_step_compare(plantCsv, pidCsv, ...
        't_final', 20, ...
        'dt', 0.01, ...
        'setpoint', 1, ...
        'output_png', outPng, ...
        'show', false);
    fprintf('pid-step-compare: form=%s num=[%s] den=[%s] setpoint=%g\n', ...
        result.plant.form, coeff_text(result.plant.num), coeff_text(result.plant.den), ...
        result.setpoint);
    fprintf('%-16s %8s %8s %8s %8s %8s %8s %8s\n', ...
        'name', 'kp', 'ki', 'kd', 'tr', 'Mp%', 'ts', 'ess');
    for index = 1:numel(result.metrics)
        row = result.metrics(index);
        fprintf('%-16s %8.3f %8.3f %8.3f %8s %8s %8s %8s\n', ...
            row.name, row.kp, row.ki, row.kd, ...
            fmt_num(row.tr), fmt_num(row.mp_pct), fmt_num(row.ts), fmt_num(row.ess));
    end
    fprintf('saved %s\n', result.output_png);
end

function text = coeff_text(coeff)
    parts = strings(1, numel(coeff));
    for index = 1:numel(coeff)
        parts(index) = string(sprintf('%g', coeff(index)));
    end
    text = char(strjoin(parts, ', '));
end

function text = fmt_num(value)
    if ~isfinite(value)
        text = sprintf('%8s', 'nan');
    elseif abs(value) < 5e-4
        text = sprintf('%8.3f', 0);
    else
        text = sprintf('%8.3f', value);
    end
end
