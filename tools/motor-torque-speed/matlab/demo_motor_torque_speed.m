function demo_motor_torque_speed()
%DEMO_MOTOR_TORQUE_SPEED Induction and DC torque-speed comparison.
%   From this folder, call demo_motor_torque_speed. The figure is written to
%   examples/output/motor_torque_speed_demo_matlab.png (gitignored). Set
%   'show', true on the motor_torque_speed call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'motor_cases.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if exist(outDir, 'dir') ~= 7
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'motor_torque_speed_demo_matlab.png');
    outCsv = fullfile(outDir, 'motor_torque_speed_demo_matlab.csv');
    result = motor_torque_speed(csvPath, ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    for index = 1:numel(result.cases)
        item = result.cases(index);
        if strcmp(item.motor, 'induction')
            fprintf(['motor-torque-speed: name=%s motor=induction ', ...
                'T_start=%.4f T_bd=%.4f s_bd=%.6f n_rated=%s T_rated=%s\n'], ...
                item.name, item.torque_start_nm, item.torque_breakdown_nm, ...
                item.slip_breakdown, fixed_num(item.speed_rated_rpm), ...
                fixed_num(item.torque_rated_nm));
        else
            fprintf('motor-torque-speed: name=%s motor=%s n0=%s T_stall=%.4f I_stall=%.4f\n', ...
                item.name, item.motor, fixed_num(item.speed_noload_rpm), ...
                item.torque_stall_nm, item.i_stall_a);
        end
    end
    fprintf('%s\n', result.summary);
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
end

function text = fixed_num(value)
    if isnan(value)
        text = 'nan';
    elseif isinf(value)
        if value > 0
            text = 'inf';
        else
            text = '-inf';
        end
    else
        text = sprintf('%.4f', value);
    end
end
