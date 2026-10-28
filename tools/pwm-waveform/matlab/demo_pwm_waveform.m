function demo_pwm_waveform()
%DEMO_PWM_WAVEFORM Bipolar and unipolar sine-triangle PWM.
%   From this folder, call demo_pwm_waveform. Figures are written to
%   examples/output/pwm_waveform_demo_matlab_<name>.png (gitignored).
%   Set 'show', true on the pwm_waveform call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'pwm_cases.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    names = {'bipolar_ma08', 'unipolar_ma08'};
    for index = 1:numel(names)
        name = names{index};
        outPng = fullfile(outDir, ['pwm_waveform_demo_matlab_' name '.png']);
        outCsv = fullfile(outDir, ['pwm_waveform_demo_matlab_' name '.csv']);
        result = pwm_waveform(csvPath, ...
            'name', name, ...
            'output_png', outPng, ...
            'output_csv', outCsv, ...
            'show', false);
        if isfinite(result.thd_percent)
            thdText = sprintf('%.4f%%', result.thd_percent);
        else
            thdText = 'undefined';
        end
        fprintf('pwm-waveform: name=%s mode=%s m_a=%s m_f=%s V1=%.4f V1_analytic=%.4f THD=%s\n', ...
            result.name, result.mode, compact_num(result.m_a), compact_num(result.m_f), ...
            result.fundamental_amplitude, result.fundamental_analytic, thdText);
        print_table(result);
        fprintf('saved %s\n', result.output_png);
        fprintf('saved %s\n', result.output_csv);
    end
end

function print_table(result)
    if isempty(result.name)
        head = '';
    else
        head = sprintf('name=%s  ', result.name);
    end
    fprintf('%smode=%s  f_m=%s Hz  f_c=%s Hz  m_f=%s  m_a=%s  Vdc=%s  phase_deg=%s\n', ...
        head, result.mode, compact_num(result.f_m), compact_num(result.f_c), ...
        compact_num(result.m_f), compact_num(result.m_a), compact_num(result.v_dc), ...
        compact_num(result.phase_deg));
    fprintf(['fs=%s Hz  N=%d  cycles=%d  samples_per_carrier=%d  linear=%d  ', ...
        'pulses_a=%d  pulses_b=%d\n'], ...
        compact_num(result.fs), result.n_samples, result.cycles, ...
        result.samples_per_carrier, double(result.linear_range), ...
        result.n_pulses_a, result.n_pulses_b);
    fprintf('dc=%s  V1=%s  V1_analytic=%s  err=%s  THD=%s  floor=%s\n', ...
        compact_num(result.dc), compact_num(result.fundamental_amplitude), ...
        compact_num(result.fundamental_analytic), ...
        percent_text(result.fundamental_error_percent), ...
        percent_text(result.thd_percent), compact_num(result.amp_floor_ratio));
    fprintf('%5s %14s %12s %12s %10s %10s %12s\n', ...
        'order', 'frequency_Hz', 'amplitude', 'rms', 'percent', 'phase_deg', 'above_floor');
    for index = 1:numel(result.harmonics)
        row = result.harmonics(index);
        if isfinite(row.percent)
            percent = sprintf('%10.4f', row.percent);
        else
            percent = sprintf('%10s', 'nan');
        end
        fprintf('%5d %14.4f %12.4f %12.4f %s %10.3f %12d\n', ...
            row.order, row.frequency_hz, row.amplitude, row.rms, percent, ...
            row.phase_deg, double(row.above_floor));
    end
end

function text = percent_text(value)
    if ~isfinite(value)
        text = 'undefined';
    else
        text = sprintf('%.4f%%', value);
    end
end

function text = compact_num(value)
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
