function result = fft_thd(source, varargin)
%FFT_THD Single-sided spectrum, harmonic table, and THD.
%   RESULT = FFT_THD(CSVPATH, 'f0', 50, 'n_harmonics', 7, ...
%       'output_png', 'spectrum.png', 'show', false)
%   RESULT = FFT_THD(SIGNAL, 'fs', 5000, 'f0', 50)
%   RESULT = FFT_THD(TIME, SIGNAL, 'f0', 50)
%
%   Same pipeline as python/fft_thd.py, in base MATLAB (no toolbox):
%   1. Read a uniform record.
%   2. Single-sided peak spectrum. window 'auto' is rectangular when the
%      record is within 0.02 cycle of an integer number of periods, and a
%      periodic Hann window otherwise.
%   3. Use f0 when it is passed. Otherwise detect it from a Hann spectrum
%      (log-magnitude parabola, then three Newton steps on the harmonic
%      residual). A peak that already sits on a bin stays on that bin.
%   4. Fit dc + sum Ah*sin(2*pi*h*f0*t + phih) by least squares. t is
%      (0:N-1)/fs, so phase is referenced to the first sample.
%   5. THD = sqrt(sum Ah^2) / A1 for orders that pass amp_floor_ratio.
%      DC is not in the sum. Peak and RMS ratios match.
%
%   Name-value keys match Python: fs, f0, n_harmonics, window, remove_dc,
%   f_search_min, f_search_max, amp_floor_ratio, output_csv, output_png, show.
%
%   RESULT fields: fs, f0, f0_source, n_samples, cycles, window, remove_dc,
%   dc, fundamental_amplitude, fundamental_rms, signal_rms, thd, thd_percent,
%   n_harmonics, amp_floor_ratio, spectrum_frequency, spectrum_amplitude,
%   harmonics, time, signal, output_csv, output_png, fig.
%   harmonics(i) holds order, frequency_hz, amplitude, rms, percent,
%   phase_rad, phase_deg, in_thd.

    if nargin < 1
        source = [];
    end
    [source, signal, rest] = split_inputs(source, varargin);
    parser = inputParser;
    parser.FunctionName = 'fft_thd';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('fs', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('f0', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('n_harmonics', 25, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('window', 'auto', @is_text_scalar);
    parser.addParameter('remove_dc', true, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('f_search_min', 10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('f_search_max', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('amp_floor_ratio', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    [time, samples] = resolve_inputs(source, signal);
    nHarmonics = positive_int('n_harmonics', opt.n_harmonics, 500);
    removeDc = as_bool('remove_dc', opt.remove_dc);
    showFig = as_bool('show', opt.show);
    fSearchMin = finite_number('f_search_min', opt.f_search_min);
    ampFloor = finite_number('amp_floor_ratio', opt.amp_floor_ratio);
    if ~(ampFloor >= 0)
        error('fft_thd:BadOption', 'amp_floor_ratio must be >= 0');
    end
    fsUsed = resolve_fs(time, opt.fs);
    if ~(fSearchMin >= 0) || fSearchMin >= fsUsed / 2
        error('fft_thd:BadOption', ...
            'f_search_min must be >= 0 and below the Nyquist frequency');
    end
    if isempty(opt.f_search_max)
        searchMax = fsUsed / 2;
    else
        searchMax = finite_number('f_search_max', opt.f_search_max);
    end
    if ~(searchMax > fSearchMin) || searchMax > fsUsed / 2 + 1e-9
        error('fft_thd:BadOption', ...
            'f_search_max must be above f_search_min and at most the Nyquist frequency');
    end

    if isempty(opt.f0)
        f0Used = detect_f0(samples, fsUsed, nHarmonics, fSearchMin, searchMax);
        f0Source = 'detected';
    else
        f0Given = finite_number('f0', opt.f0);
        if ~(f0Given > 0) || f0Given >= fsUsed / 2
            error('fft_thd:BadOption', ...
                'f0 must be positive and below the Nyquist frequency');
        end
        f0Used = f0Given;
        f0Source = 'given';
    end

    n = numel(samples);
    windowUsed = resolve_window(opt.window, n, fsUsed, f0Used);
    [spectrumFrequency, spectrumAmplitude] = single_sided(samples, fsUsed, windowUsed, removeDc);
    [dc, harmonics, signalRms] = harmonic_table(samples, fsUsed, f0Used, nHarmonics, ampFloor);
    if isempty(time)
        time = (0:n - 1).' / fsUsed;
    else
        time = time(:);
    end

    outputCsv = char(strtrim(string(opt.output_csv)));
    outputPng = char(strtrim(string(opt.output_png)));
    if ~isempty(outputCsv)
        write_harmonics_csv(outputCsv, harmonics);
    end

    result = struct();
    result.fs = fsUsed;
    result.f0 = f0Used;
    result.f0_source = f0Source;
    result.n_samples = n;
    result.cycles = n * f0Used / fsUsed;
    result.window = windowUsed;
    result.remove_dc = removeDc;
    result.dc = dc;
    result.fundamental_amplitude = harmonics(1).amplitude;
    result.fundamental_rms = harmonics(1).rms;
    result.signal_rms = signalRms;
    result.thd = thd_fraction(harmonics);
    result.thd_percent = 100 * result.thd;
    result.n_harmonics = nHarmonics;
    result.amp_floor_ratio = ampFloor;
    result.spectrum_frequency = spectrumFrequency;
    result.spectrum_amplitude = spectrumAmplitude;
    result.harmonics = harmonics;
    result.time = time;
    result.signal = samples(:);
    result.output_csv = outputCsv;
    result.output_png = outputPng;
    result.fig = [];
    if ~isempty(outputPng) || showFig
        result.fig = render_figure(result, outputPng, showFig);
    end
end

function [source, signal, rest] = split_inputs(source, args)
    signal = [];
    rest = args;
    if isempty(args)
        return
    end
    first = args{1};
    if isnumeric(first) && isvector(first) && ~isempty(first)
        if numel(first) < 16
            error('fft_thd:BadOption', ...
                ['the second argument is not a signal vector. ', ...
                 'Pass fs and f0 as name-value pairs']);
        end
        signal = first;
        if numel(args) == 1
            rest = {};
        else
            rest = args(2:end);
        end
    end
end

function [time, samples] = resolve_inputs(source, signal)
    time = [];
    if is_text_scalar(source) && strlength(strtrim(string(source))) > 0
        if ~isempty(signal)
            error('fft_thd:BadOption', 'pass a CSV path or arrays, not both');
        end
        text = char(strtrim(string(source)));
        if is_parameter_name(text)
            error('fft_thd:BadOption', ...
                '''%s'' is a parameter name. Pass the CSV path as the first argument', text);
        end
        [time, samples] = read_waveform_csv(text);
        return
    end
    if isempty(source) && isempty(signal)
        error('fft_thd:BadOption', ...
            'pass a CSV path, a signal array, or time and signal arrays');
    end
    if ~isempty(source) && ~isempty(signal)
        time = as_signal('time', source);
        samples = as_signal('signal', signal);
        if numel(time) ~= numel(samples)
            error('fft_thd:BadOption', 'time and signal must have the same length');
        end
        return
    end
    if ~isempty(source)
        samples = as_signal('signal', source);
        return
    end
    samples = as_signal('signal', signal);
end

function samples = as_signal(name, value)
    if ~isnumeric(value) || ~isvector(value)
        error('fft_thd:BadOption', '%s must be a one-dimensional numeric array', name);
    end
    samples = double(value(:));
    if numel(samples) < 16
        error('fft_thd:BadOption', '%s must contain at least 16 samples', name);
    end
    if any(~isfinite(samples))
        error('fft_thd:BadOption', '%s contains a non-finite value', name);
    end
end

function fsUsed = resolve_fs(time, fsGiven)
    if isempty(time)
        inferred = [];
    else
        inferred = fs_from_time(time);
    end
    if isempty(fsGiven)
        given = [];
    else
        given = positive_number('fs', fsGiven);
    end
    if isempty(inferred) && isempty(given)
        error('fft_thd:BadOption', 'fs is required when the input has no time column');
    end
    if ~isempty(inferred) && ~isempty(given)
        if abs(inferred - given) > 1e-3 * inferred
            error('fft_thd:BadOption', 'fs does not match the time step in the data');
        end
        fsUsed = inferred;
        return
    end
    if ~isempty(inferred)
        fsUsed = inferred;
    else
        fsUsed = given;
    end
end

function fs = fs_from_time(time)
    dt = diff(time(:));
    if any(dt <= 0)
        error('fft_thd:BadOption', 'time must be strictly increasing');
    end
    medianDt = median(dt);
    if ~(medianDt > 0) || ~isfinite(medianDt)
        error('fft_thd:BadOption', 'time step must be a positive finite number');
    end
    if (max(dt) - min(dt)) > 1e-4 * medianDt
        error('fft_thd:BadOption', ...
            'time step is not uniform; resample before calling fft_thd');
    end
    fs = 1 / medianDt;
end

function [time, samples] = read_waveform_csv(csvPath)
    if ~isfile(csvPath)
        error('fft_thd:FileNotFound', 'CSV not found: %s', csvPath);
    end
    try
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
    catch
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve');
    end
    tableData = readtable(csvPath, opts);
    if height(tableData) == 0
        error('fft_thd:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
    names = string(tableData.Properties.VariableNames);
    norms = strings(1, numel(names));
    for index = 1:numel(names)
        norms(index) = string(norm_key(names(index)));
    end
    timeIdx = first_alias(norms, ["times", "time", "timestamp", "t"]);
    signalIdx = first_alias(norms, ["signal", "value", "voltage", "current", ...
        "waveform", "samples", "sample", "x", "v", "i"]);
    if signalIdx == 0
        candidates = [];
        for index = 1:numel(names)
            if index ~= timeIdx && strlength(strtrim(names(index))) > 0
                candidates(end + 1) = index; %#ok<AGROW>
            end
        end
        if numel(candidates) ~= 1
            error('fft_thd:BadOption', ...
                'CSV needs a signal column (signal, value, voltage, current, ...)');
        end
        signalIdx = candidates(1);
    end
    if timeIdx == signalIdx
        timeIdx = 0;
    end
    samples = column_as_double(tableData, signalIdx, 'signal');
    samples = as_signal('signal', samples);
    if timeIdx == 0
        time = [];
    else
        time = as_signal('time', column_as_double(tableData, timeIdx, 'time'));
    end
end

function values = column_as_double(tableData, col, label)
    name = tableData.Properties.VariableNames{col};
    raw = tableData.(name);
    if iscell(raw)
        values = zeros(numel(raw), 1);
        for index = 1:numel(raw)
            item = raw{index};
            if is_blank_cell(item)
                error('fft_thd:BadOption', '%s is missing on CSV row %d', label, index);
            end
            values(index) = finite_number(sprintf('%s row %d', label, index), item);
        end
        return
    end
    if isstring(raw)
        values = zeros(numel(raw), 1);
        for index = 1:numel(raw)
            if ismissing(raw(index)) || strlength(strtrim(raw(index))) == 0
                error('fft_thd:BadOption', '%s is missing on CSV row %d', label, index);
            end
            values(index) = finite_number(sprintf('%s row %d', label, index), raw(index));
        end
        return
    end
    if isnumeric(raw)
        values = double(raw(:));
        for index = 1:numel(values)
            if ~isfinite(values(index))
                error('fft_thd:BadOption', '%s is missing on CSV row %d', label, index);
            end
        end
        return
    end
    error('fft_thd:BadOption', '%s column could not be read', label);
end

function tf = is_blank_cell(value)
    if isempty(value)
        tf = true;
        return
    end
    if isstring(value) || ischar(value)
        tf = strlength(strtrim(string(value))) == 0;
        return
    end
    if isnumeric(value) && all(~isfinite(value))
        tf = true;
        return
    end
    tf = false;
end

function idx = first_alias(norms, aliases)
    idx = 0;
    for alias = aliases
        found = find(norms == alias, 1, 'first');
        if ~isempty(found)
            idx = found;
            return
        end
    end
end

function kind = resolve_window(window, n, fs, f0)
    key = norm_key(window);
    if strcmp(key, 'auto')
        cycles = n * f0 / fs;
        if abs(cycles - round(cycles)) <= 0.02
            kind = 'rect';
        else
            kind = 'hann';
        end
        return
    end
    if any(strcmp(key, {'rect', 'rectangular', 'boxcar', 'none'}))
        kind = 'rect';
        return
    end
    if any(strcmp(key, {'hann', 'hanning'}))
        kind = 'hann';
        return
    end
    error('fft_thd:BadOption', 'window must be ''auto'', ''rect'', or ''hann''');
end

function weights = window_weights(n, kind)
    if strcmp(kind, 'rect')
        weights = ones(n, 1);
        return
    end
    % Periodic Hann. sum(w) = n/2 for n > 1. An on-bin sine still reads its
    % true peak; the shoulders land on the adjacent bins.
    k = (0:n - 1).';
    weights = 0.5 - 0.5 * cos(2 * pi * k / n);
end

function [frequency, amplitude] = single_sided(samples, fs, window, removeDc)
    x = samples(:);
    if removeDc
        x = x - mean(x);
    end
    weights = window_weights(numel(x), window);
    spectrum = fft(x .* weights);
    n = numel(x);
    nHalf = floor(n / 2);
    amplitude = abs(spectrum(1:nHalf + 1)) / sum(weights);
    if n > 1
        amplitude(2:end) = 2 * amplitude(2:end);
        if mod(n, 2) == 0
            amplitude(end) = 0.5 * amplitude(end);
        end
    end
    frequency = (0:nHalf).' * (fs / n);
end

function f0 = detect_f0(samples, fs, nHarmonics, fSearchMin, fSearchMax)
    % Constants match python/fft_thd.py: BIN_TOL = 0.02, NEWTON_STEPS = 3,
    % NEWTON_STEP_BINS = 0.2, NEWTON_SHIFT_BINS = 0.6, NEWTON_SHRINK = 0.2.
    [frequency, amplitude] = single_sided(samples, fs, 'hann', true);
    band = find(frequency >= fSearchMin & frequency <= fSearchMax & frequency > 0);
    if isempty(band)
        error('fft_thd:BadOption', ...
            'no spectrum bin falls inside the fundamental search band');
    end
    [~, relative] = max(amplitude(band));
    local = band(relative);
    if amplitude(local) <= 1e-15
        error('fft_thd:BadOption', ...
            'no spectral peak in the search band; pass f0 or widen f_search_min/f_search_max');
    end
    delta = log_parabolic_delta(amplitude, local);
    df = fs / numel(samples);
    bin = local - 1;
    if abs(delta) <= 0.02
        f0 = bin * df;
        return
    end
    fhat = (bin + delta) * df;
    orders = orders_for(fs, fhat, nHarmonics);
    step = 0.2 * df;
    fCap = (fs / 2) / orders(end) - 1e-9;
    fFloor = max(fSearchMin, df);
    for stepIndex = 1:3 %#ok<FXSET>
        center = min(max(fhat, fFloor), fCap);
        plusEdge = min(max(center + step, fFloor), fCap);
        minusEdge = min(max(center - step, fFloor), fCap);
        half = min(center - minusEdge, plusEdge - center);
        if half <= 0
            fhat = center;
            break
        end
        energyPlus = residual_energy(samples, fs, center + half, orders);
        energyMinus = residual_energy(samples, fs, center - half, orders);
        energyCenter = residual_energy(samples, fs, center, orders);
        denom = energyPlus - 2 * energyCenter + energyMinus;
        slope = (energyPlus - energyMinus) / (2 * half);
        curvature = denom / (half * half);
        if ~isfinite(curvature) || curvature <= 0 || ~isfinite(slope)
            fhat = center;
            break
        end
        shift = slope / curvature;
        limit = 0.6 * df;
        if abs(shift) > limit
            shift = sign(shift) * limit;
        end
        fhat = min(max(center - shift, fFloor), fCap);
        step = max(step * 0.2, 1e-6 * max(fhat, 1));
    end
    f0 = fhat;
end

function delta = log_parabolic_delta(amplitude, local)
    nBins = numel(amplitude);
    if local <= 1 || local >= nBins
        delta = 0;
        return
    end
    left = amplitude(local - 1);
    center = amplitude(local);
    right = amplitude(local + 1);
    if left <= 0 || center <= 0 || right <= 0
        delta = 0;
        return
    end
    logLeft = log(left);
    logCenter = log(center);
    logRight = log(right);
    denom = logLeft - 2 * logCenter + logRight;
    if abs(denom) < 1e-18
        delta = 0;
        return
    end
    delta = 0.5 * (logLeft - logRight) / denom;
    if ~isfinite(delta)
        delta = 0;
        return
    end
    delta = max(-0.5, min(0.5, delta));
end

function orders = orders_for(fs, f0, nHarmonics)
    orders = zeros(1, 0);
    nyquist = fs / 2;
    for order = 1:nHarmonics
        if order * f0 >= nyquist - 1e-9
            break
        end
        orders(end + 1) = order; %#ok<AGROW>
    end
    if isempty(orders) || orders(1) ~= 1
        error('fft_thd:BadOption', ...
            'fundamental frequency is not below the Nyquist frequency');
    end
end

function phi = design_matrix(n, fs, f0, orders)
    t = (0:n - 1).' / fs;
    nOrders = numel(orders);
    phi = zeros(n, 1 + 2 * nOrders);
    phi(:, 1) = 1;
    for index = 1:nOrders
        omega = 2 * pi * orders(index) * f0;
        phi(:, 2 * index) = sin(omega * t);
        phi(:, 2 * index + 1) = cos(omega * t);
    end
end

function energy = residual_energy(samples, fs, f0, orders)
    phi = design_matrix(numel(samples), fs, f0, orders);
    if size(phi, 1) <= size(phi, 2)
        energy = inf;
        return
    end
    beta = phi \ samples(:);
    residual = samples(:) - phi * beta;
    energy = sum(residual .^ 2);
    if ~isfinite(energy)
        energy = inf;
    end
end

function [dc, harmonics, signalRms] = harmonic_table(samples, fs, f0, nHarmonics, ampFloor)
    samples = samples(:);
    orders = orders_for(fs, f0, nHarmonics);
    phi = design_matrix(numel(samples), fs, f0, orders);
    if size(phi, 1) <= size(phi, 2)
        error('fft_thd:BadOption', ...
            'harmonic fit needs more samples than coefficients; lower n_harmonics or use a longer record');
    end
    if rank(phi) < size(phi, 2)
        error('fft_thd:BadOption', ...
            'harmonic fit is rank deficient; lower n_harmonics or use a longer record');
    end
    beta = phi \ samples;
    nOrders = numel(orders);
    amplitudes = zeros(1, nOrders);
    phases = zeros(1, nOrders);
    for index = 1:nOrders
        bSin = beta(2 * index);
        bCos = beta(2 * index + 1);
        amplitudes(index) = hypot(bSin, bCos);
        phases(index) = atan2(bCos, bSin);
    end
    a1 = amplitudes(1);
    scale = max(abs(samples));
    if ~isfinite(a1) || a1 <= 1e-8 * max(scale, 1e-30)
        error('fft_thd:BadOption', 'fundamental amplitude is zero; THD is undefined');
    end
    harmonics = repmat(empty_harmonic(), 1, nOrders);
    for index = 1:nOrders
        amplitude = amplitudes(index);
        phase = phases(index);
        if amplitude <= max(1e-12, 1e-8 * a1)
            phase = 0;
        end
        order = orders(index);
        harmonics(index).order = order;
        harmonics(index).frequency_hz = order * f0;
        harmonics(index).amplitude = amplitude;
        harmonics(index).rms = amplitude / sqrt(2);
        harmonics(index).percent = 100 * amplitude / a1;
        harmonics(index).phase_rad = phase;
        harmonics(index).phase_deg = phase * 180 / pi;
        harmonics(index).in_thd = order > 1 && amplitude >= ampFloor * a1;
    end
    ac = samples - beta(1);
    signalRms = sqrt(sum(ac .^ 2) / numel(samples));
    dc = beta(1);
end

function fraction = thd_fraction(harmonics)
    a1 = harmonics(1).amplitude;
    total = 0;
    for index = 1:numel(harmonics)
        if harmonics(index).in_thd
            total = total + harmonics(index).amplitude ^ 2;
        end
    end
    fraction = sqrt(total) / a1;
end

function row = empty_harmonic()
    row = struct( ...
        'order', 0, ...
        'frequency_hz', 0, ...
        'amplitude', 0, ...
        'rms', 0, ...
        'percent', 0, ...
        'phase_rad', 0, ...
        'phase_deg', 0, ...
        'in_thd', false);
end

function write_harmonics_csv(csvPath, harmonics)
    folder = fileparts(csvPath);
    if ~isempty(folder) && ~exist(folder, 'dir')
        mkdir(folder);
    end
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('fft_thd:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, 'order,frequency_hz,amplitude,rms,percent,phase_rad,phase_deg,in_thd\n');
    for index = 1:numel(harmonics)
        row = harmonics(index);
        fprintf(fid, '%d,%.12g,%.12g,%.12g,%.12g,%.12g,%.12g,%d\n', ...
            row.order, row.frequency_hz, row.amplitude, row.rms, row.percent, ...
            row.phase_rad, row.phase_deg, double(row.in_thd));
    end
end

function fig = render_figure(result, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    n = result.n_samples;
    nLimit = round(10 * result.fs / result.f0);
    if nLimit < 8
        nShow = n;
    else
        nShow = min(n, nLimit);
    end
    tRel = (0:nShow - 1).' / result.fs;
    recon = result.dc * ones(nShow, 1);
    markF = [];
    markA = [];
    for index = 1:numel(result.harmonics)
        row = result.harmonics(index);
        recon = recon + row.amplitude * sin(2 * pi * row.frequency_hz * tRel + row.phase_rad);
        if row.order == 1 || (row.in_thd && row.percent >= 0.2)
            markF(end + 1) = row.frequency_hz; %#ok<AGROW>
            markA(end + 1) = row.amplitude; %#ok<AGROW>
        end
    end
    maxOrder = result.harmonics(end).order;
    xMax = min(result.fs / 2, max(8 * result.f0, (maxOrder + 1) * result.f0) * 1.02);
    visibleBins = result.spectrum_frequency <= xMax + 1e-12;
    if any(visibleBins)
        yPeak = max(result.spectrum_amplitude(visibleBins));
    else
        yPeak = 1;
    end
    yTop = max([yPeak, result.fundamental_amplitude, 1e-12]);

    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 80 980 740], ...
        'Name', 'fft-thd', 'NumberTitle', 'off');
    axWave = subplot(2, 1, 1, 'Parent', fig);
    hSignal = plot(axWave, result.time(1:nShow), result.signal(1:nShow), ...
        'Color', [31, 78, 121] / 255, 'LineWidth', 1.1);
    hold(axWave, 'on');
    hFit = plot(axWave, result.time(1:nShow), recon, '--', ...
        'Color', [192, 57, 43] / 255, 'LineWidth', 1.15);
    hold(axWave, 'off');
    xlabel(axWave, 'Time (s)');
    ylabel(axWave, 'Signal');
    if nShow == n
        title(axWave, 'Waveform');
    else
        title(axWave, 'Waveform (first 10 cycles)');
    end
    grid(axWave, 'on');
    axWave.GridColor = [0.82 0.82 0.82];
    axWave.GridAlpha = 0.8;
    box(axWave, 'on');
    set(axWave, 'FontSize', 11);
    legend(axWave, [hSignal, hFit], {'signal', 'harmonic fit'}, ...
        'Location', 'northeast', 'Box', 'on', 'EdgeColor', [0.8 0.8 0.8]);

    axSpec = subplot(2, 1, 2, 'Parent', fig);
    hSpec = plot(axSpec, result.spectrum_frequency, result.spectrum_amplitude, ...
        'Color', [31, 78, 121] / 255, 'LineWidth', 1.0);
    hold(axSpec, 'on');
    if ~isempty(markF)
        hMark = plot(axSpec, markF, markA, 'o', ...
            'Color', [192, 57, 43] / 255, 'MarkerFaceColor', [192, 57, 43] / 255, ...
            'MarkerSize', 5.5, 'LineStyle', 'none');
        legendHandles = [hSpec, hMark];
        legendLabels = {'spectrum', 'harmonics'};
    else
        legendHandles = hSpec;
        legendLabels = {'spectrum'};
    end
    hold(axSpec, 'off');
    xlim(axSpec, [0, xMax]);
    ylim(axSpec, [0, yTop * 1.18]);
    xlabel(axSpec, 'Frequency (Hz)');
    ylabel(axSpec, 'Peak amplitude');
    title(axSpec, 'Single-sided amplitude spectrum');
    grid(axSpec, 'on');
    axSpec.GridColor = [0.82 0.82 0.82];
    axSpec.GridAlpha = 0.8;
    box(axSpec, 'on');
    set(axSpec, 'FontSize', 11);
    legend(axSpec, legendHandles, legendLabels, ...
        'Location', 'northeast', 'Box', 'on', 'EdgeColor', [0.8 0.8 0.8]);
    text(axSpec, 0.02, 0.95, sprintf('f1 = %.2f Hz\nTHD = %.2f%%', result.f0, result.thd_percent), ...
        'Units', 'normalized', 'VerticalAlignment', 'top', 'HorizontalAlignment', 'left', ...
        'FontSize', 11, 'Color', [31, 78, 121] / 255, ...
        'BackgroundColor', 'w', 'EdgeColor', [0.8 0.8 0.8]);

    if ~isempty(outputPng)
        folder = fileparts(outputPng);
        if ~isempty(folder) && ~exist(folder, 'dir')
            mkdir(folder);
        end
        exportgraphics(fig, outputPng, 'Resolution', 150);
    end
    if ~showFig
        close(fig);
        fig = [];
    end
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('fft_thd:BadOption', '%s must be a positive finite number', name);
    end
end

function number = positive_int(name, value, maximum)
    number = finite_number(name, value);
    if abs(number - round(number)) > 1e-9
        error('fft_thd:BadOption', '%s must be a positive integer', name);
    end
    number = round(number);
    if number < 1 || number > maximum
        error('fft_thd:BadOption', '%s must be an integer from 1 to %d', name, maximum);
    end
end

function number = finite_number(name, value)
    if iscell(value)
        if numel(value) ~= 1
            error('fft_thd:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if isstring(value) || ischar(value)
        number = str2double(strtrim(string(value)));
    elseif isnumeric(value)
        number = double(value);
    else
        error('fft_thd:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('fft_thd:BadOption', '%s must be a finite number', name);
    end
end

function tf = as_bool(name, value)
    if islogical(value) && isscalar(value)
        tf = value;
        return
    end
    if isnumeric(value) && isscalar(value) && (value == 0 || value == 1)
        tf = logical(value);
        return
    end
    error('fft_thd:BadOption', '%s must be true or false', name);
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = isstring(value) && isscalar(value);
end

function tf = is_parameter_name(value)
    keys = {'fs', 'f0', 'n_harmonics', 'window', 'remove_dc', 'f_search_min', ...
        'f_search_max', 'amp_floor_ratio', 'output_csv', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(value), keys));
end

function key = norm_key(value)
    text = lower(strtrim(string(value)));
    key = char(regexprep(text, '[\s_\-]', ''));
end
