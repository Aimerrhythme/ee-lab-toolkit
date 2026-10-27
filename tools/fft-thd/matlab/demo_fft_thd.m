function demo_fft_thd()
%DEMO_FFT_THD Spectrum and THD of the synthetic 50 Hz waveform.
%   From this folder, call demo_fft_thd. The figure is written to
%   examples/output/fft_thd_demo_matlab.png (gitignored). Set
%   'show', true on the fft_thd call below to leave the window open.

    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_waveform.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    if ~exist(outDir, 'dir')
        mkdir(outDir);
    end
    outPng = fullfile(outDir, 'fft_thd_demo_matlab.png');
    outCsv = fullfile(outDir, 'fft_thd_demo_matlab.csv');
    result = fft_thd(csvPath, ...
        'f0', 50, ...
        'n_harmonics', 7, ...
        'window', 'auto', ...
        'amp_floor_ratio', 0.002, ...
        'output_png', outPng, ...
        'output_csv', outCsv, ...
        'show', false);
    fprintf('fft-thd: f0=%s Hz fs=%s Hz N=%d window=%s THD=%.4f%%\n', ...
        compact_num(result.f0), compact_num(result.fs), result.n_samples, ...
        result.window, result.thd_percent);
    fprintf('f0=%s Hz (%s)  fs=%s Hz  N=%d  cycles=%.4f  window=%s\n', ...
        compact_num(result.f0), result.f0_source, compact_num(result.fs), ...
        result.n_samples, result.cycles, result.window);
    fprintf('dc=%s  A1=%s  THD=%.4f%%  floor=%s\n', ...
        compact_num(result.dc), compact_num(result.fundamental_amplitude), ...
        result.thd_percent, compact_num(result.amp_floor_ratio));
    fprintf('%5s %14s %12s %12s %10s %10s %6s\n', ...
        'order', 'frequency_Hz', 'amplitude', 'rms', 'percent', 'phase_deg', 'in_thd');
    for index = 1:numel(result.harmonics)
        row = result.harmonics(index);
        fprintf('%5d %14.4f %12.4f %12.4f %10.4f %10.3f %6d\n', ...
            row.order, row.frequency_hz, row.amplitude, row.rms, ...
            row.percent, row.phase_deg, double(row.in_thd));
    end
    fprintf('analytic noise-free THD for 8%%, 5%%, and 2%% harmonics: 9.6437%%\n');
    fprintf('saved %s\n', result.output_png);
    fprintf('saved %s\n', result.output_csv);
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
