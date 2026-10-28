function result = pwm_waveform(source, varargin)
%PWM_WAVEFORM Sine-triangle PWM for a single-phase full bridge.
%   RESULT = PWM_WAVEFORM()
%   RESULT = PWM_WAVEFORM('cases.csv', 'name', 'bipolar_ma08', ...
%       'output_png', 'pwm.png', 'show', false)
%   RESULT = PWM_WAVEFORM('mode', 'unipolar', 'm_a', 0.8, 'm_f', 21)
%
%   Same waveform as python/pwm_waveform.py, in base MATLAB (no toolbox).
%
%   Carrier peak is ±1. A period starts at -1 and reaches +1 at mid-period:
%       phase = mod(k, samples_per_carrier) / samples_per_carrier
%       carrier = 1 - 4 * abs(phase - 0.5)
%   Modulation is m_a*sin(2*pi*f_m*t + phase). A tie turns the upper device on.
%
%   Bipolar: gate_b = 1 - gate_a, v_out is +V_dc or -V_dc.
%   Unipolar: leg B follows -m. v_out is +V_dc, 0, or -V_dc.
%   Linear range (m_a <= 1): fundamental peak approaches m_a*V_dc.
%   m_f*cycles must be an integer number of carrier periods.
%
%   THD is the full-band Parseval ratio. The harmonic table is a separate
%   integer-order sine fit; amp_floor_ratio only sets above_floor.
%
%   Name-value keys match Python: name, mode, f_m, f_c, m_f, m_a, v_dc,
%   phase_deg, cycles, samples_per_carrier, n_harmonics, amp_floor_ratio,
%   csv_path, output_csv, output_png, show.

    if nargin < 1
        source = [];
    end
    [source, rest] = split_source(source, varargin);
    parser = inputParser;
    parser.FunctionName = 'pwm_waveform';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('name', '', @is_text_scalar);
    parser.addParameter('mode', 'bipolar', @is_text_scalar);
    parser.addParameter('f_m', 50, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('f_c', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('m_f', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('m_a', 0.8, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_dc', 100, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('phase_deg', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('cycles', 2, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('samples_per_carrier', 200, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('n_harmonics', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('amp_floor_ratio', 0.01, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = apply_csv(parser.Results, source, rest);

    showFig = as_bool('show', opt.show);
    mode = normalize_mode(opt.mode);
    fM = positive_number('f_m', opt.f_m);
    mA = finite_number('m_a', opt.m_a);
    if mA < 0 || mA > 10
        error('pwm_waveform:BadOption', 'm_a must be between 0 and 10');
    end
    vDc = positive_number('v_dc', opt.v_dc);
    phaseDeg = finite_number('phase_deg', opt.phase_deg);
    cycles = positive_int('cycles', opt.cycles, 1, 50);
    samplesPerCarrier = positive_int('samples_per_carrier', opt.samples_per_carrier, 8, 20000);
    [fC, mF, nCarrier] = resolve_carrier(fM, opt.f_c, opt.m_f, cycles);
    nSamples = samplesPerCarrier * nCarrier;
    if nSamples > 2000000
        error('pwm_waveform:BadOption', ...
            'record is too long; lower samples_per_carrier, m_f, or cycles');
    end
    ampFloor = finite_number('amp_floor_ratio', opt.amp_floor_ratio);
    if ~(ampFloor >= 0)
        error('pwm_waveform:BadOption', 'amp_floor_ratio must be >= 0');
    end
    fs = nSamples * fM / cycles;
    if is_blank(opt.n_harmonics)
        nHarmonics = auto_harmonics(mF, fs, fM);
    else
        nHarmonics = positive_int('n_harmonics', opt.n_harmonics, 1, 500);
    end

    phaseRad = phaseDeg * pi / 180;
    k = (0:nSamples - 1).';
    theta = 2 * pi * (cycles * k / nSamples) + phaseRad;
    modulation = mA * sin(theta);
    carrierPhase = mod(k, samplesPerCarrier) ./ samplesPerCarrier;
    carrier = 1 - 4 * abs(carrierPhase - 0.5);
    gateA = double(modulation >= carrier);
    if strcmp(mode, 'bipolar')
        gateB = 1 - gateA;
        vOut = vDc * (2 * gateA - 1);
    else
        gateB = double((-modulation) >= carrier);
        vOut = (vDc / 2) * (2 * gateA - 1) - (vDc / 2) * (2 * gateB - 1);
    end
    time = k / fs;
    vRef = modulation * vDc;

    dc = mean(vOut);
    harmonics = harmonic_table(vOut, fs, fM, cycles, nHarmonics, ampFloor, vDc);
    fundamental = harmonics(1);
    analytic = mA * vDc;
    fundError = fundamental.amplitude - analytic;
    if abs(analytic) <= 1e-15 * max(vDc, 1)
        errorPercent = NaN;
    else
        errorPercent = 100 * fundError / analytic;
    end
    ac = vOut - dc;
    signalRms = sqrt(sum(ac .^ 2) / nSamples);
    thd = thd_ratio(signalRms, fundamental.amplitude, vDc);
    if isfinite(thd)
        thdPercent = 100 * thd;
    else
        thdPercent = NaN;
    end

    outputCsv = char(strtrim(string(opt.output_csv)));
    outputPng = char(strtrim(string(opt.output_png)));
    caseName = char(strtrim(string(opt.name)));

    result = struct();
    result.name = caseName;
    result.mode = mode;
    result.f_m = fM;
    result.f_c = fC;
    result.m_f = mF;
    result.m_a = mA;
    result.v_dc = vDc;
    result.phase_deg = phaseDeg;
    result.phase_rad = phaseRad;
    result.cycles = cycles;
    result.samples_per_carrier = samplesPerCarrier;
    result.fs = fs;
    result.n_samples = nSamples;
    result.n_carrier = nCarrier;
    result.linear_range = mA <= 1 + 1e-12;
    result.n_pulses_a = pulse_count(gateA);
    result.n_pulses_b = pulse_count(gateB);
    result.dc = dc;
    result.fundamental_amplitude = fundamental.amplitude;
    result.fundamental_rms = fundamental.rms;
    result.fundamental_phase_rad = fundamental.phase_rad;
    result.fundamental_phase_deg = fundamental.phase_deg;
    result.fundamental_analytic = analytic;
    result.fundamental_error = fundError;
    result.fundamental_error_percent = errorPercent;
    result.signal_rms = signalRms;
    result.thd = thd;
    result.thd_percent = thdPercent;
    result.n_harmonics = nHarmonics;
    result.amp_floor_ratio = ampFloor;
    result.harmonics = harmonics;
    result.time = time;
    result.modulation = modulation;
    result.carrier = carrier;
    result.gate_a = gateA;
    result.gate_b = gateB;
    result.v_out = vOut;
    result.v_ref = vRef;
    result.output_csv = outputCsv;
    result.output_png = outputPng;
    result.fig = [];
    if ~isempty(outputCsv)
        write_harmonics_csv(outputCsv, result.harmonics);
    end
    if ~isempty(outputPng) || showFig
        result.fig = render_figure(result, outputPng, showFig);
    end
end

function [source, rest] = split_source(source, args)
    rest = args;
    if is_parameter_name(source)
        if isempty(args)
            rest = {source};
        else
            rest = [{source}, args];
        end
        source = [];
    end
end

function opt = apply_csv(opt, source, rest)
    csvPath = char(strtrim(string(opt.csv_path)));
    if isnumeric(source) && ~isempty(source)
        error('pwm_waveform:BadOption', ...
            'pass parameters by name; the first argument is a CSV path');
    end
    if is_text_scalar(source) && strlength(strtrim(string(source))) > 0
        text = char(strtrim(string(source)));
        if is_parameter_name(text)
            error('pwm_waveform:BadOption', ...
                '''%s'' is a parameter name. Pass the CSV path as the first argument or as csv_path=', ...
                text);
        end
        if was_passed(rest, 'csv_path')
            error('pwm_waveform:BadOption', ...
                'pass a CSV path once, either positionally or as csv_path=');
        end
        csvPath = text;
    elseif ~isempty(source) && ~(is_text_scalar(source) && strlength(strtrim(string(source))) == 0)
        error('pwm_waveform:BadOption', 'source must be a CSV path or omitted');
    end
    if isempty(csvPath)
        return
    end
    opt.csv_path = csvPath;
    rows = read_case_csv(csvPath);
    selected = select_row(rows, char(strtrim(string(opt.name))));
    opt = merge_row(opt, selected);
end

function rows = read_case_csv(csvPath)
    if ~isfile(csvPath)
        error('pwm_waveform:FileNotFound', 'CSV not found: %s', csvPath);
    end
    try
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
    catch
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve');
    end
    tableData = readtable(csvPath, opts);
    if height(tableData) == 0
        error('pwm_waveform:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
    names = string(tableData.Properties.VariableNames);
    nRows = height(tableData);
    rows = {};
    for rowIndex = 1:nRows
        item = struct();
        blankRow = true;
        for col = 1:numel(names)
            value = unwrap_cell(tableData{rowIndex, col});
            item.(char(names(col))) = value;
            if ~is_blank(value)
                blankRow = false;
            end
        end
        if ~blankRow
            rows{end + 1} = item; %#ok<AGROW>
        end
    end
    if isempty(rows)
        error('pwm_waveform:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
end

function row = select_row(rows, name)
    if isempty(name)
        if numel(rows) == 1
            row = rows{1};
            return
        end
        error('pwm_waveform:BadOption', 'CSV has multiple rows; pass name to select one');
    end
    for index = 1:numel(rows)
        rowName = char(as_text(struct_lookup(rows{index}, {'name'})));
        if strcmp(rowName, name)
            row = rows{index};
            return
        end
    end
    error('pwm_waveform:BadOption', 'name ''%s'' was not found in the CSV', name);
end

function opt = merge_row(opt, row)
    pairs = { ...
        'name', {'name'}; ...
        'mode', {'mode'}; ...
        'f_m', {'fm'}; ...
        'f_c', {'fc'}; ...
        'm_f', {'mf'}; ...
        'm_a', {'ma'}; ...
        'v_dc', {'vdc'}; ...
        'phase_deg', {'phasedeg', 'phase'}; ...
        'cycles', {'cycles'}; ...
        'samples_per_carrier', {'samplespercarrier'}; ...
        'n_harmonics', {'nharmonics'}; ...
        'amp_floor_ratio', {'ampfloorratio'}};
    for index = 1:size(pairs, 1)
        value = struct_lookup(row, pairs{index, 2});
        if ~is_blank(value)
            opt.(pairs{index, 1}) = value;
        end
    end
end

function [fC, mF, nCarrier] = resolve_carrier(fM, fCIn, mFIn, cycles)
    mFValue = [];
    fCValue = [];
    if ~is_blank(mFIn)
        mFValue = finite_number('m_f', mFIn);
        if ~(mFValue > 0)
            error('pwm_waveform:BadOption', 'm_f must be a positive finite number');
        end
    end
    if ~is_blank(fCIn)
        fCValue = positive_number('f_c', fCIn);
    end
    if isempty(mFValue) && isempty(fCValue)
        mFValue = 21;
    end
    if ~isempty(mFValue) && ~isempty(fCValue)
        expected = mFValue * fM;
        if abs(fCValue - expected) > 1e-6 * max(abs(expected), 1)
            error('pwm_waveform:BadOption', 'f_c does not match m_f * f_m');
        end
    elseif isempty(mFValue)
        mFValue = fCValue / fM;
    end
    if mFValue < 1
        error('pwm_waveform:BadOption', ...
            'm_f must be >= 1 (carrier at least as fast as the modulation)');
    end
    product = mFValue * cycles;
    nearest = round(product);
    if abs(product - nearest) > 1e-6 || nearest < 1
        error('pwm_waveform:BadOption', ...
            ['m_f * cycles must be an integer so the record holds ', ...
             'an integer number of carrier periods']);
    end
    nCarrier = nearest;
    mF = nCarrier / cycles;
    fC = nCarrier * fM / cycles;
end

function nHarm = auto_harmonics(mF, fs, fM)
    nyquistOrder = floor((fs / 2) / fM - 1e-9);
    want = ceil(2 * mF + 4);
    nHarm = max(1, min([150, nyquistOrder, want]));
end

function count = pulse_count(gate)
    previous = gate(end);
    count = 0;
    for index = 1:numel(gate)
        current = gate(index);
        if previous < 0.5 && current >= 0.5
            count = count + 1;
        end
        previous = current;
    end
end

function thd = thd_ratio(signalRms, amplitude, vDc)
    if amplitude <= 1e-8 * max(abs(vDc), 1)
        thd = NaN;
        return
    end
    fundRms = amplitude / sqrt(2);
    distMs = signalRms ^ 2 - fundRms ^ 2;
    if distMs < 0
        if distMs < -1e-8 * max(signalRms ^ 2, 1)
            error('pwm_waveform:BadOption', ...
                'THD residual is negative; the fundamental estimate is inconsistent');
        end
        distMs = 0;
    end
    thd = sqrt(distMs) / fundRms;
end

function harmonics = harmonic_table(vOut, fs, fM, cycles, nHarmonics, ampFloor, vDc)
    vOut = vOut(:);
    n = numel(vOut);
    k = (0:n - 1).';
    nKeep = 0;
    for order = 1:nHarmonics
        if order * fM >= fs / 2 - 1e-9
            break
        end
        nKeep = nKeep + 1;
    end
    if nKeep < 1
        error('pwm_waveform:BadOption', ...
            'no harmonic fits under the Nyquist frequency; increase samples_per_carrier');
    end
    bSin = zeros(1, nKeep);
    bCos = zeros(1, nKeep);
    orders = zeros(1, nKeep);
    kept = 0;
    for order = 1:nHarmonics
        if order * fM >= fs / 2 - 1e-9
            break
        end
        kept = kept + 1;
        theta = 2 * pi * (order * cycles * k / n);
        orders(kept) = order;
        bSin(kept) = (2 / n) * sum(vOut .* sin(theta));
        bCos(kept) = (2 / n) * sum(vOut .* cos(theta));
    end
    a1 = hypot(bSin(1), bCos(1));
    defined = a1 > 1e-8 * max(abs(vDc), 1);
    harmonics = repmat(empty_harmonic(), 1, nKeep);
    for index = 1:nKeep
        amplitude = hypot(bSin(index), bCos(index));
        phase = atan2(bCos(index), bSin(index));
        if amplitude <= max(1e-9, 1e-8 * max(a1, 1e-30))
            phase = 0;
        end
        order = orders(index);
        if defined
            percent = 100 * amplitude / a1;
            aboveFloor = order > 1 && amplitude >= ampFloor * a1;
        else
            percent = NaN;
            aboveFloor = false;
        end
        harmonics(index).order = order;
        harmonics(index).frequency_hz = order * fM;
        harmonics(index).amplitude = amplitude;
        harmonics(index).rms = amplitude / sqrt(2);
        harmonics(index).percent = percent;
        harmonics(index).phase_rad = phase;
        harmonics(index).phase_deg = phase * 180 / pi;
        harmonics(index).above_floor = aboveFloor;
    end
end

function row = empty_harmonic()
    row = struct( ...
        'order', 0, ...
        'frequency_hz', 0, ...
        'amplitude', 0, ...
        'rms', 0, ...
        'percent', NaN, ...
        'phase_rad', 0, ...
        'phase_deg', 0, ...
        'above_floor', false);
end

function write_harmonics_csv(csvPath, harmonics)
    folder = fileparts(csvPath);
    if ~isempty(folder) && ~exist(folder, 'dir')
        mkdir(folder);
    end
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('pwm_waveform:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, 'order,frequency_hz,amplitude,rms,percent,phase_rad,phase_deg,above_floor\n');
    for index = 1:numel(harmonics)
        row = harmonics(index);
        if isfinite(row.percent)
            percent = sprintf('%.12g', row.percent);
        else
            percent = 'nan';
        end
        fprintf(fid, '%d,%.12g,%.12g,%.12g,%s,%.12g,%.12g,%d\n', ...
            row.order, row.frequency_hz, row.amplitude, row.rms, percent, ...
            row.phase_rad, row.phase_deg, double(row.above_floor));
    end
end

function fig = render_figure(result, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    n = result.n_samples;
    if result.cycles > 2
        nShow = round(n * 2 / result.cycles);
        nShow = max(2, min(n, nShow));
    else
        nShow = n;
    end
    time = result.time(1:nShow);
    tEnd = nShow / result.fs;
    if nShow == n
        suffix = '';
    else
        suffix = ' (first 2 cycles)';
    end
    navy = [31, 78, 121] / 255;
    red = [192, 57, 43] / 255;
    green = [14, 124, 102] / 255;

    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 60 1040 860], ...
        'Name', 'pwm-waveform', 'NumberTitle', 'off');

    axMod = subplot(3, 1, 1, 'Parent', fig);
    plot(axMod, time, result.modulation(1:nShow), 'Color', navy, 'LineWidth', 1.25);
    hold(axMod, 'on');
    plot(axMod, time, result.carrier(1:nShow), 'Color', red, 'LineWidth', 0.9);
    hold(axMod, 'off');
    ylabel(axMod, 'Amplitude');
    title(axMod, ['Modulation and carrier' suffix]);
    ylim(axMod, [-1.35, 1.45]);
    xlim(axMod, [time(1), tEnd]);
    style_axes(axMod);
    legend(axMod, {'modulation', 'carrier'}, 'Location', 'northeast', ...
        'Box', 'on', 'EdgeColor', [0.8 0.8 0.8]);

    axGate = subplot(3, 1, 2, 'Parent', fig);
    stairs(axGate, time, result.gate_a(1:nShow), 'Color', navy, 'LineWidth', 1.05);
    hold(axGate, 'on');
    stairs(axGate, time, result.gate_b(1:nShow) + 1.35, 'Color', green, 'LineWidth', 1.05);
    hold(axGate, 'off');
    ylabel(axGate, 'Gate');
    title(axGate, 'Upper-device gates');
    ylim(axGate, [-0.25, 2.7]);
    xlim(axGate, [time(1), tEnd]);
    set(axGate, 'YTick', [0, 1, 1.35, 2.35], 'YTickLabel', {'0', '1', '0', '1'});
    style_axes(axGate);
    legend(axGate, {'gate_a', 'gate_b (+1.35)'}, 'Location', 'northeast', ...
        'Box', 'on', 'EdgeColor', [0.8 0.8 0.8]);

    axOut = subplot(3, 1, 3, 'Parent', fig);
    stairs(axOut, time, result.v_out(1:nShow), 'Color', navy, 'LineWidth', 1.0);
    hold(axOut, 'on');
    plot(axOut, time, result.v_ref(1:nShow), '--', 'Color', red, 'LineWidth', 1.2);
    hold(axOut, 'off');
    xlabel(axOut, 'Time (s)');
    ylabel(axOut, 'Voltage');
    title(axOut, 'Bridge output');
    yPeak = max([result.v_dc, max(abs(result.v_ref(1:nShow))), 1e-9]);
    ylim(axOut, [-1.25 * yPeak, 1.45 * yPeak]);
    xlim(axOut, [time(1), tEnd]);
    style_axes(axOut);
    legend(axOut, {'v_out', 'm_a*Vdc*sin'}, 'Location', 'northeast', ...
        'Box', 'on', 'EdgeColor', [0.8 0.8 0.8]);
    if isfinite(result.thd_percent)
        thdLine = sprintf('THD = %.2f%%', result.thd_percent);
    else
        thdLine = 'THD undefined';
    end
    note = sprintf('%s\nm_a = %.2f    m_f = %s\nV1 = %.2f\nm_a*Vdc = %.2f\n%s', ...
        result.mode, result.m_a, compact_num(result.m_f), ...
        result.fundamental_amplitude, result.fundamental_analytic, thdLine);
    if ~result.linear_range
        note = [note newline 'overmodulation'];
    end
    text(axOut, 0.02, 0.04, note, 'Units', 'normalized', ...
        'VerticalAlignment', 'bottom', 'HorizontalAlignment', 'left', ...
        'FontSize', 10, 'Color', navy, ...
        'BackgroundColor', 'w', 'EdgeColor', [0.8 0.8 0.8], 'Margin', 4);

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

function style_axes(ax)
    grid(ax, 'on');
    ax.GridColor = [0.82 0.82 0.82];
    ax.GridAlpha = 0.8;
    box(ax, 'on');
    set(ax, 'FontSize', 11);
end

function mode = normalize_mode(value)
    key = normalize_key(value);
    if any(strcmp(key, {'bipolar', 'bi', char("双极性")}))
        mode = 'bipolar';
        return
    end
    if any(strcmp(key, {'unipolar', 'uni', char("单极性")}))
        mode = 'unipolar';
        return
    end
    error('pwm_waveform:BadOption', 'mode must be ''bipolar'' or ''unipolar''');
end

function value = struct_lookup(data, keys)
    names = string(fieldnames(data));
    norms = strings(size(names));
    for index = 1:numel(names)
        norms(index) = string(normalize_key(names(index)));
    end
    keys = string(keys);
    for index = 1:numel(keys)
        found = find(norms == string(normalize_key(keys(index))), 1, 'first');
        if ~isempty(found)
            value = data.(char(names(found)));
            return
        end
    end
    value = [];
end

function value = unwrap_cell(value)
    if iscell(value) && numel(value) == 1
        value = value{1};
    end
end

function tf = is_blank(value)
    if isempty(value)
        tf = true;
        return
    end
    if iscell(value)
        if numel(value) == 1
            value = value{1};
        else
            tf = false;
            return
        end
        if isempty(value)
            tf = true;
            return
        end
    end
    if ismissing(value)
        tf = true;
        return
    end
    if isstring(value) || ischar(value)
        tf = all(strlength(strtrim(string(value))) == 0);
        return
    end
    if isnumeric(value) && all(~isfinite(value))
        tf = true;
        return
    end
    tf = false;
end

function text = as_text(value)
    if is_blank(value)
        text = "";
        return
    end
    if iscell(value)
        value = value{1};
    end
    text = strtrim(string(value));
end

function key = normalize_key(value)
    text = lower(strtrim(as_text(value)));
    key = char(regexprep(text, '[\s_\-]', ''));
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('pwm_waveform:BadOption', '%s must be a positive finite number', name);
    end
end

function number = positive_int(name, value, minimum, maximum)
    number = finite_number(name, value);
    if abs(number - round(number)) > 1e-9
        error('pwm_waveform:BadOption', '%s must be an integer from %d to %d', ...
            name, minimum, maximum);
    end
    number = round(number);
    if number < minimum || number > maximum
        error('pwm_waveform:BadOption', '%s must be an integer from %d to %d', ...
            name, minimum, maximum);
    end
end

function number = finite_number(name, value)
    if iscell(value)
        if numel(value) ~= 1
            error('pwm_waveform:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if isstring(value) || ischar(value)
        number = str2double(strtrim(string(value)));
    elseif isnumeric(value)
        number = double(value);
    else
        error('pwm_waveform:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('pwm_waveform:BadOption', '%s must be a finite number', name);
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
    error('pwm_waveform:BadOption', '%s must be true or false', name);
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = isstring(value) && isscalar(value);
end

function tf = is_parameter_name(value)
    if isempty(value)
        tf = false;
        return
    end
    if ischar(value)
        text = value;
    elseif isstring(value) && isscalar(value)
        text = char(value);
    else
        tf = false;
        return
    end
    keys = {'name', 'mode', 'f_m', 'f_c', 'm_f', 'm_a', 'v_dc', 'phase_deg', ...
        'cycles', 'samples_per_carrier', 'n_harmonics', 'amp_floor_ratio', ...
        'csv_path', 'output_csv', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(text), keys));
end

function tf = was_passed(rest, key)
    tf = false;
    for index = 1:2:numel(rest)
        if is_parameter_name(rest{index}) && strcmpi(strtrim(char(string(rest{index}))), key)
            tf = true;
            return
        end
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
