function result = bode_demo(varargin)
%BODE_DEMO Bode magnitude, phase, and stability margins.
%   RESULT = BODE_DEMO() uses G(s) = 1/(s^2 + s + 1).
%   RESULT = BODE_DEMO(NUM, DEN) evaluates one transfer function.
%   RESULT = BODE_DEMO(SYSTEMS) takes a struct array, a cell of structs,
%   or a CSV path. SYSTEMS can also be passed as the name-value 'systems'.
%   RESULT = BODE_DEMO(NUM, DEN, 'w_min', 0.1, 'w_max', 100, ...
%       'output_png', 'bode.png', 'show', false)
%   RESULT = BODE_DEMO('form', 'first_order', 'tau', 1, 'name', 'lag')
%
%   Coefficients are highest power first. Name-value keys match Python:
%   form, name, names, k, tau, wn, zeta, kp, ki, kd, kd_n, w_min, w_max,
%   n_points, frequency_rad_s, output_png, show, num, den, systems.
%   Pass [] or omit a system to use the default. w_min and w_max default
%   to NaN, which means "choose from the poles and zeros".
%
%   H(jw) = polyval(num, jw) / polyval(den, jw). Base MATLAB only.
%   Python uses scipy.signal.freqs for the same polynomial evaluation.
%   Keep the numeric thresholds in this file aligned with python/bode_demo.py.
%
%   PM = wrap_180(phase_deg(w_gc) + 180)
%   GM_dB = -magnitude_db(w_pc)
%   The reported margin is the smallest one when several crossings exist.
%   Magnitude below 0 dB on the whole grid -> PM = +Inf.
%   No negative-real crossing -> GM = +Inf.
%   Magnitude above 0 dB with no crossing -> PM = NaN.
%
%   RESULT fields: frequency_rad_s (column), magnitude_db, phase_deg
%   (rows are frequencies, columns are systems), names, margins, w_min,
%   w_max, n_points, output_png, fig.
%   margins(i) holds name, form, num, den, gain_crossover_rad_s,
%   phase_crossover_rad_s, phase_margin_deg, gain_margin_db,
%   phase_margin_rad_s, gain_margin_rad_s.

    [src, den, paramArgs] = split_inputs(varargin{:});
    opt = parse_options(paramArgs{:});
    [src, den] = apply_system_override(src, den, opt);
    specs = collect_specs(src, den, opt);
    specs = select_names(specs, opt.names);
    nPoints = positive_int('n_points', opt.n_points, 2, 20000);
    frequency = frequency_grid(specs, opt.w_min, opt.w_max, nPoints, opt.frequency_rad_s);

    nSys = numel(specs);
    magnitude = zeros(numel(frequency), nSys);
    phase = zeros(numel(frequency), nSys);
    margins = repmat(blank_margins(), 1, nSys);
    labels = cell(1, nSys);
    names = strings(nSys, 1);
    for index = 1:nSys
        [magnitude(:, index), phase(:, index)] = frequency_response( ...
            specs{index}.num, specs{index}.den, frequency);
        margins(index) = system_margins(specs{index}, frequency, ...
            magnitude(:, index), phase(:, index));
        names(index) = string(margins(index).name);
        labels{index} = legend_label(margins(index).name, ...
            margins(index).phase_margin_deg, margins(index).gain_margin_db);
    end

    outputPng = char(strtrim(string(opt.output_png)));
    if strlength(strtrim(string(outputPng))) == 0
        outputPng = '';
    end
    showFig = logical(opt.show);
    if ~isempty(outputPng) || showFig
        fig = render_figure(frequency, magnitude, phase, labels, margins, outputPng, showFig);
    else
        fig = [];
    end

    result = struct();
    result.frequency_rad_s = frequency;
    result.magnitude_db = magnitude;
    result.phase_deg = phase;
    result.names = names;
    result.margins = margins;
    result.w_min = frequency(1);
    result.w_max = frequency(end);
    result.n_points = numel(frequency);
    result.output_png = outputPng;
    result.fig = fig;
end

function [src, den, paramArgs] = split_inputs(varargin)
    src = [];
    den = [];
    if nargin == 0
        paramArgs = {};
        return
    end
    first = varargin{1};
    if isnumeric(first)
        if nargin < 2 || ~isnumeric(varargin{2})
            error('bode_demo:BadOption', 'den is required when num is a coefficient vector');
        end
        src = first;
        den = varargin{2};
        paramArgs = varargin(3:end);
        return
    end
    if isstruct(first) || iscell(first)
        src = first;
        paramArgs = varargin(2:end);
        return
    end
    if is_text(first)
        key = lower(strtrim(char(string(first))));
        if is_known_key(key)
            paramArgs = varargin;
            return
        end
        src = char(string(first));
        paramArgs = varargin(2:end);
        return
    end
    error('bode_demo:BadOption', ...
        'num must be coefficients, a system, a list of systems, or a CSV path');
end

function opt = parse_options(varargin)
    parser = inputParser;
    parser.FunctionName = 'bode_demo';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('form', '', @is_text_scalar);
    parser.addParameter('name', '', @is_text_scalar);
    parser.addParameter('names', {}, @(x) iscell(x) || isstring(x) || ischar(x) || isempty(x));
    parser.addParameter('k', 1, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('tau', 1, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('wn', 1, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('zeta', 0.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('kp', 1, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('ki', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('kd', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('kd_n', 10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('w_min', NaN, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('w_max', NaN, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('n_points', 800, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('frequency_rad_s', [], @(x) isnumeric(x));
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('num', [], @(x) isnumeric(x));
    parser.addParameter('den', [], @(x) isnumeric(x));
    parser.addParameter('systems', [], @(x) isstruct(x) || iscell(x) || is_text(x) || isempty(x));
    parser.parse(varargin{:});
    opt = parser.Results;
end

function [src, den] = apply_system_override(src, den, opt)
    hasSystems = ~isempty(opt.systems);
    hasPositional = ~(isnumeric(src) && isempty(src)) && ~isempty(src);
    if hasSystems
        if hasPositional || ~isempty(den) || ~isempty(opt.num)
            error('bode_demo:BadOption', 'pass systems or num/den, not both');
        end
        src = opt.systems;
        den = [];
        return
    end
    if isnumeric(src) && isempty(src) && ~isempty(opt.num)
        if ~isempty(den)
            error('bode_demo:BadOption', 'pass systems or num/den, not both');
        end
        src = opt.num;
        den = opt.den;
    end
end

function specs = collect_specs(src, den, opt)
    scalars = struct('k', double(opt.k), 'tau', double(opt.tau), 'wn', double(opt.wn), ...
        'zeta', double(opt.zeta), 'kp', double(opt.kp), 'ki', double(opt.ki), ...
        'kd', double(opt.kd), 'kd_n', double(opt.kd_n));
    if is_text(src)
        if ~isempty(den) || ~isempty(strtrim(char(string(opt.form)))) || ~isempty(strtrim(char(string(opt.name))))
            error('bode_demo:BadOption', 'a CSV path does not take den, form, or name');
        end
        reject_unused_scalars(scalars);
        specs = read_systems(char(string(src)));
        return
    end
    if isstruct(src) || iscell(src)
        if ~isempty(den) || ~isempty(strtrim(char(string(opt.form)))) || ~isempty(strtrim(char(string(opt.name))))
            error('bode_demo:BadOption', 'a system list does not take den, form, or name');
        end
        reject_unused_scalars(scalars);
        specs = normalize_systems(src);
        return
    end
    if isnumeric(src) && isempty(src) && isempty(den)
        form = char(strtrim(string(opt.form)));
        if isempty(form)
            form = 'second_order';
        end
        raw = scalars;
        raw.form = form;
        raw.name = char(strtrim(string(opt.name)));
        specs = {build_system(raw)};
        return
    end
    if isnumeric(src) && isnumeric(den) && ~isempty(src)
        if ~isvector(src) || isempty(den) || ~isvector(den)
            error('bode_demo:BadOption', 'num and den must be non-empty coefficient vectors');
        end
        form = char(strtrim(string(opt.form)));
        if ~isempty(form) && ~strcmp(form, 'tf')
            error('bode_demo:BadOption', 'num and den imply form ''tf''');
        end
        reject_unused_scalars(scalars);
        raw = struct('form', 'tf', 'name', char(strtrim(string(opt.name))), 'num', src, 'den', den);
        specs = {build_system(raw)};
        return
    end
    error('bode_demo:BadOption', ...
        'num must be coefficients, a system, a list of systems, or a CSV path');
end

function reject_unused_scalars(scalars)
    defaults = struct('k', 1, 'tau', 1, 'wn', 1, 'zeta', 0.5, 'kp', 1, 'ki', 0, 'kd', 0, 'kd_n', 10);
    fields = fieldnames(defaults);
    extra = {};
    for index = 1:numel(fields)
        key = fields{index};
        if scalars.(key) ~= defaults.(key)
            extra{end + 1} = key; %#ok<AGROW>
        end
    end
    if ~isempty(extra)
        error('bode_demo:BadOption', ...
            'k, tau, wn, zeta, kp, ki, kd, and kd_n apply only when form builds one system; got %s', ...
            strjoin(extra, ', '));
    end
end

function specs = normalize_systems(systems)
    if isstruct(systems)
        nSys = numel(systems);
        items = cell(1, nSys);
        for index = 1:nSys
            items{index} = systems(index);
        end
    elseif iscell(systems)
        nSys = numel(systems);
        items = systems;
    else
        error('bode_demo:BadOption', 'systems must be a struct array, a cell of structs, or a CSV path');
    end
    if nSys == 0
        error('bode_demo:BadOption', 'systems must contain at least one transfer function');
    end
    specs = cell(1, nSys);
    for index = 1:nSys
        if ~isstruct(items{index})
            error('bode_demo:BadOption', 'each system must be a struct');
        end
        specs{index} = build_system(items{index});
    end
end

function spec = build_system(raw)
    formValue = struct_lookup(raw, {'form'});
    if is_missing(formValue)
        form = 'tf';
    else
        form = canonical_form(formValue);
    end
    kGain = optional_number('k', struct_lookup(raw, {'k', 'gain'}), 1);
    tau = optional_number('tau', struct_lookup(raw, {'tau'}), 1);
    wn = optional_number('wn', struct_lookup(raw, {'wn', 'omegan'}), 1);
    zeta = optional_number('zeta', struct_lookup(raw, {'zeta'}), 0.5);
    kp = optional_number('kp', struct_lookup(raw, {'kp'}), 1);
    ki = optional_number('ki', struct_lookup(raw, {'ki'}), 0);
    kd = optional_number('kd', struct_lookup(raw, {'kd'}), 0);
    kdN = optional_number('kd_n', struct_lookup(raw, {'kdn', 'n'}), 10);

    if strcmp(form, 'first_order')
        if ~(tau > 0)
            error('bode_demo:BadOption', 'tau must be positive');
        end
        num = kGain;
        den = [tau, 1];
    elseif strcmp(form, 'second_order')
        if ~(wn > 0)
            error('bode_demo:BadOption', 'wn must be positive');
        end
        num = kGain * wn * wn;
        den = [1, 2 * zeta * wn, wn * wn];
    elseif strcmp(form, 'pid_loop')
        if ~(wn > 0)
            error('bode_demo:BadOption', 'wn must be positive');
        end
        [cNum, cDen] = pid_coefficients(kp, ki, kd, kdN);
        num = conv(cNum, kGain * wn * wn);
        den = conv(cDen, [1, 2 * zeta * wn, wn * wn]);
    else
        num = struct_lookup(raw, {'num', 'numerator'});
        den = struct_lookup(raw, {'den', 'denominator'});
        if is_missing(num) || is_missing(den)
            error('bode_demo:BadOption', 'form ''tf'' requires num and den coefficients');
        end
        num = coeff_vector(num, 'num');
        den = coeff_vector(den, 'den');
    end
    [num, den] = prepare_coefficients(num, den);
    reject_jw_poles(den);
    nameValue = struct_lookup(raw, {'name'});
    if is_missing(nameValue)
        nameText = '';
    else
        nameText = strtrim(char(string(nameValue)));
    end
    explicit = ~isempty(nameText);
    if explicit
        builtName = nameText;
    else
        builtName = default_name(form, tau, zeta, kp, ki, kd);
    end
    spec = struct('name', builtName, 'form', form, 'num', num, 'den', den, 'explicitName', explicit);
end

function name = default_name(form, tau, zeta, kp, ki, kd)
    if strcmp(form, 'first_order')
        name = sprintf('tau=%g', tau);
    elseif strcmp(form, 'second_order')
        name = sprintf('zeta=%g', zeta);
    elseif strcmp(form, 'pid_loop')
        name = pid_kind(kp, ki, kd);
    else
        name = 'tf';
    end
end

function name = pid_kind(~, ki, kd)
    if ki == 0 && kd == 0
        name = 'P';
    elseif kd == 0
        name = 'PI';
    elseif ki == 0
        name = 'PD';
    else
        name = 'PID';
    end
end

function [num, den] = pid_coefficients(kp, ki, kd, kdN)
    if kd ~= 0 && ~(isfinite(kdN) && kdN > 0)
        error('bode_demo:BadOption', 'kd_n must be a positive finite number when kd is nonzero');
    end
    if ki == 0 && kd == 0
        num = kp;
        den = 1;
        return
    end
    if kd == 0
        num = [kp, ki];
        den = [1, 0];
        return
    end
    num = [kp + kd * kdN, kp * kdN + ki, ki * kdN];
    den = [1, kdN, 0];
end

function form = canonical_form(value)
    key = lower(strtrim(char(string(value))));
    key = regexprep(key, '[\s_\-]', '');
    switch key
        case {'tf', 'transferfunction'}
            form = 'tf';
        case 'firstorder'
            form = 'first_order';
        case 'secondorder'
            form = 'second_order';
        case {'pidloop', 'pid'}
            form = 'pid_loop';
        otherwise
            error('bode_demo:BadOption', ...
                'form must be one of: tf, first_order, second_order, pid_loop');
    end
end

function [num, den] = prepare_coefficients(num, den)
    num = strip_leading(num, 'num');
    den = strip_leading(den, 'den');
    if den(1) == 0
        error('bode_demo:BadOption', 'denominator leading coefficient must be nonzero');
    end
    if numel(num) - 1 > 8 || numel(den) - 1 > 8
        error('bode_demo:BadOption', 'transfer-function order must be <= 8');
    end
end

function coeff = strip_leading(coeff, name)
    coeff = double(coeff(:)).';
    if isempty(coeff) || any(~isfinite(coeff))
        error('bode_demo:BadOption', '%s must be a finite coefficient vector', name);
    end
    while numel(coeff) > 1 && coeff(1) == 0
        coeff = coeff(2:end);
    end
end

function reject_jw_poles(den)
    if numel(den) <= 1
        return
    end
    poles = roots(den(:));
    for index = 1:numel(poles)
        if ~isfinite(poles(index))
            continue
        end
        radius = abs(poles(index));
        if radius <= 1e-8
            continue
        end
        if abs(real(poles(index))) <= 1e-8 * max(1, radius)
            error('bode_demo:BadOption', ...
                ['denominator has a pole on the imaginary axis; ', ...
                'Bode magnitude is unbounded there. A pole at the origin is allowed.']);
        end
    end
end

function specs = select_names(specs, names)
    if isempty(specs)
        error('bode_demo:BadOption', 'systems must contain at least one transfer function');
    end
    specs = claim_names(specs);
    wanted = name_list(names);
    if isempty(wanted)
        return
    end
    available = cell(1, numel(specs));
    for index = 1:numel(specs)
        available{index} = specs{index}.name;
    end
    chosen = cell(1, numel(wanted));
    for index = 1:numel(wanted)
        found = find(strcmp(available, wanted{index}), 1, 'first');
        if isempty(found)
            error('bode_demo:BadOption', 'unknown system name: %s. Available: %s', ...
                wanted{index}, strjoin(available, ', '));
        end
        chosen{index} = specs{found};
    end
    specs = chosen;
end

function specs = claim_names(specs)
    used = strings(0, 1);
    for index = 1:numel(specs)
        spec = specs{index};
        if spec.explicitName
            if any(used == string(spec.name))
                error('bode_demo:BadOption', 'duplicate system name: %s', spec.name);
            end
            used(end + 1, 1) = string(spec.name); %#ok<AGROW>
        else
            base = string(spec.name);
            candidate = base;
            suffix = 2;
            while any(used == candidate)
                candidate = base + "-" + string(suffix);
                suffix = suffix + 1;
            end
            spec.name = char(candidate);
            used(end + 1, 1) = candidate; %#ok<AGROW>
            specs{index} = spec;
        end
    end
end

function list = name_list(names)
    if isempty(names)
        list = {};
        return
    end
    if ischar(names)
        list = cellstr(names);
        return
    end
    if isstring(names)
        list = cellstr(names(:));
        return
    end
    if iscell(names)
        list = cell(1, numel(names));
        for index = 1:numel(names)
            list{index} = strtrim(char(string(names{index})));
        end
        return
    end
    error('bode_demo:BadOption', 'names must be a string array or a cell of names');
end

function frequency = frequency_grid(specs, wMin, wMax, nPoints, frequencyIn)
    if ~isempty(frequencyIn)
        if ~isnan(wMin) || ~isnan(wMax)
            error('bode_demo:BadOption', 'pass frequency_rad_s or w_min/w_max, not both');
        end
        freq = double(frequencyIn(:));
        if isempty(freq) || any(~isfinite(freq)) || any(freq <= 0)
            error('bode_demo:BadOption', 'frequency_rad_s must contain positive finite values');
        end
        frequency = unique(freq);
        return
    end
    autoLo = inf;
    autoHi = 0;
    for index = 1:numel(specs)
        [lo, hi] = auto_span(specs{index}.num, specs{index}.den);
        autoLo = min(autoLo, lo);
        autoHi = max(autoHi, hi);
    end
    if isnan(wMin)
        lo = autoLo;
    else
        lo = double(wMin);
    end
    if isnan(wMax)
        hi = autoHi;
    else
        hi = double(wMax);
    end
    if ~(isfinite(lo) && isfinite(hi) && lo > 0 && hi > 0)
        error('bode_demo:BadOption', 'w_min and w_max must be positive finite numbers');
    end
    if isnan(wMin)
        lo = extend_low(specs, lo);
    end
    if isnan(wMax)
        hi = extend_high(specs, hi);
    end
    if ~(hi > lo)
        error('bode_demo:BadOption', 'w_max must be greater than w_min');
    end
    if hi / lo > 1e12
        error('bode_demo:BadOption', 'frequency span is too wide; set w_min and w_max');
    end
    frequency = logspace(log10(lo), log10(hi), nPoints).';
end

function [lo, hi] = auto_span(num, den)
    mags = zeros(1, 0);
    coeffs = {num, den};
    for part = 1:2
        coeff = coeffs{part};
        if numel(coeff) <= 1
            continue
        end
        poles = roots(coeff(:));
        for index = 1:numel(poles)
            if ~isfinite(poles(index))
                continue
            end
            radius = abs(poles(index));
            if radius > 1e-8
                mags(end + 1) = radius; %#ok<AGROW>
            end
        end
    end
    if isempty(mags)
        lo = 1e-2;
        hi = 1e2;
        return
    end
    lo = min(mags) / 10;
    hi = max(mags) * 10;
end

function hi = extend_high(specs, hi)
    steps = 0;
    while steps < 4 && needs_edge(specs, hi, 'high')
        hi = hi * 10;
        steps = steps + 1;
    end
end

function lo = extend_low(specs, lo)
    steps = 0;
    while steps < 4 && needs_edge(specs, lo, 'low')
        lo = lo / 10;
        steps = steps + 1;
    end
end

function needed = needs_edge(specs, wValue, which)
    needed = false;
    for index = 1:numel(specs)
        spec = specs{index};
        relative = (numel(spec.den) - 1) - (numel(spec.num) - 1);
        magnitude = mag_db_scalar(spec.num, spec.den, wValue);
        if strcmp(which, 'high')
            if relative > 0 && isfinite(magnitude) && magnitude >= 0
                needed = true;
                return
            end
        elseif origin_excess_poles(spec.num, spec.den) > 0 && isfinite(magnitude) && magnitude <= 0
            needed = true;
            return
        end
    end
end

function excess = origin_excess_poles(num, den)
    excess = trailing_zeros(den) - trailing_zeros(num);
end

function count = trailing_zeros(coeff)
    count = 0;
    for index = numel(coeff):-1:1
        if coeff(index) == 0
            count = count + 1;
        else
            break
        end
    end
end

function number = positive_int(name, value, low, high)
    if ~(isnumeric(value) && isscalar(value) && isfinite(value) && value == floor(value))
        error('bode_demo:BadOption', '%s must be an integer', name);
    end
    number = double(value);
    if number < low || number > high
        error('bode_demo:BadOption', '%s must be between %d and %d', name, low, high);
    end
end

function h = eval_response(num, den, w)
    w = double(w(:));
    s = 1j * w;
    h = polyval(num, s) ./ polyval(den, s);
    denAbs = abs(polyval(den, s));
    scale = max(max(abs(den)), 1);
    h(denAbs <= 1e-12 * scale) = NaN;
end

function db = mag_db_scalar(num, den, wValue)
    h = eval_response(num, den, wValue);
    if ~isscalar(h)
        h = h(1);
    end
    if ~isfinite(h)
        db = NaN;
        return
    end
    amplitude = abs(h);
    if amplitude == 0
        db = -Inf;
        return
    end
    db = 20 * log10(amplitude);
end

function [magnitude, phase] = frequency_response(num, den, frequency)
    h = eval_response(num, den, frequency);
    magnitude = nan(numel(frequency), 1);
    phase = nan(numel(frequency), 1);
    for index = 1:numel(frequency)
        value = h(index);
        if ~isfinite(value) || value == 0
            if isfinite(value) && value == 0
                magnitude(index) = -Inf;
            else
                magnitude(index) = NaN;
            end
            phase(index) = NaN;
            continue
        end
        magnitude(index) = 20 * log10(abs(value));
        raw = angle(value) * 180 / pi;
        if index == 1 || ~isfinite(phase(index - 1))
            phase(index) = raw;
        else
            phase(index) = carry_phase(num, den, frequency(index - 1), phase(index - 1), ...
                frequency(index), raw, 0);
        end
    end
end

function candidate = carry_phase(num, den, w0, phase0, w1, raw1, depth)
    candidate = raw1 + 360 * round((phase0 - raw1) / 360);
    if abs(candidate - phase0) <= 150 || depth >= 10
        return
    end
    midpoint = sqrt(w0 * w1);
    value = eval_response(num, den, midpoint);
    if ~isscalar(value)
        value = value(1);
    end
    if ~isfinite(value) || value == 0
        return
    end
    rawMid = angle(value) * 180 / pi;
    phaseMid = carry_phase(num, den, w0, phase0, midpoint, rawMid, depth + 1);
    candidate = carry_phase(num, den, midpoint, phaseMid, w1, raw1, depth + 1);
end

function value = wrap180(x)
    value = mod(x + 180, 360) - 180;
end

function row = system_margins(spec, frequency, magnitude, phase)
    gainCross = level_crossings(frequency, magnitude, 0, 1e-12, spec.num, spec.den, 'mag');
    phaseCross = zeros(1, 0);
    levels = phase_levels(phase);
    for index = 1:numel(levels)
        found = level_crossings(frequency, phase, levels(index), 1e-9, spec.num, spec.den, 'phase');
        phaseCross = [phaseCross, found]; %#ok<AGROW>
    end
    phaseCross = dedupe_frequencies(phaseCross);

    pm = zeros(1, 0);
    wpm = zeros(1, 0);
    for index = 1:numel(gainCross)
        phaseValue = phase_at(spec.num, spec.den, frequency, phase, gainCross(index));
        if ~isfinite(phaseValue)
            continue
        end
        pm(end + 1) = wrap180(phaseValue + 180); %#ok<AGROW>
        wpm(end + 1) = gainCross(index); %#ok<AGROW>
    end
    if ~isempty(pm)
        best = pick_smallest(pm, wpm);
        phaseMargin = pm(best);
        phaseMarginW = wpm(best);
    else
        usable = magnitude(~isnan(magnitude));
        if ~isempty(usable) && max(usable) < 0
            phaseMargin = Inf;
            phaseMarginW = NaN;
        else
            phaseMargin = NaN;
            phaseMarginW = NaN;
        end
    end

    gm = zeros(1, 0);
    wgm = zeros(1, 0);
    for index = 1:numel(phaseCross)
        magValue = mag_db_scalar(spec.num, spec.den, phaseCross(index));
        if isnan(magValue)
            continue
        end
        gm(end + 1) = -magValue; %#ok<AGROW>
        wgm(end + 1) = phaseCross(index); %#ok<AGROW>
    end
    if ~isempty(gm)
        best = pick_smallest(gm, wgm);
        gainMargin = gm(best);
        gainMarginW = wgm(best);
    else
        gainMargin = Inf;
        gainMarginW = NaN;
    end

    row = blank_margins();
    row.name = spec.name;
    row.form = spec.form;
    row.num = spec.num;
    row.den = spec.den;
    row.gain_crossover_rad_s = gainCross;
    row.phase_crossover_rad_s = phaseCross;
    row.phase_margin_deg = phaseMargin;
    row.gain_margin_db = gainMargin;
    row.phase_margin_rad_s = phaseMarginW;
    row.gain_margin_rad_s = gainMarginW;
end

function best = pick_smallest(marginValues, frequencies)
    best = 1;
    for index = 2:numel(marginValues)
        if marginValues(index) < marginValues(best) || ...
                (marginValues(index) == marginValues(best) && frequencies(index) < frequencies(best))
            best = index;
        end
    end
end

function levels = phase_levels(phase)
    usable = phase(isfinite(phase));
    if isempty(usable)
        levels = zeros(1, 0);
        return
    end
    low = min(usable);
    high = max(usable);
    kMin = ceil((low + 180) / 360 - 1e-12);
    kMax = floor((high + 180) / 360 + 1e-12);
    if kMax < kMin
        levels = zeros(1, 0);
        return
    end
    levels = -180 + 360 * (kMin:kMax);
end

function found = level_crossings(frequency, values, level, tol, num, den, kind)
    found = zeros(1, 0);
    exact = false(numel(values), 1);
    for index = 1:numel(values)
        value = values(index);
        if isnan(value)
            continue
        end
        if abs(value - level) <= tol
            if index == 1 || ~exact(index - 1)
                found(end + 1) = frequency(index); %#ok<AGROW>
            end
            exact(index) = true;
        end
    end
    for index = 1:(numel(values) - 1)
        if exact(index) || exact(index + 1)
            continue
        end
        left = values(index);
        right = values(index + 1);
        if isnan(left) || isnan(right)
            continue
        end
        if (left - level) * (right - level) < 0
            found(end + 1) = bisect_cross(frequency(index), frequency(index + 1), ...
                left, right, level, tol, num, den, kind); %#ok<AGROW>
        end
    end
    found = dedupe_frequencies(found);
end

function w = bisect_cross(w0, w1, v0, v1, level, tol, num, den, kind)
    lo = w0;
    hi = w1;
    fLo = v0 - level;
    for step = 1:60 %#ok<NASGU>
        mid = sqrt(lo * hi);
        value = eval_curve(kind, num, den, mid, level);
        if ~isfinite(value)
            break
        end
        fMid = value - level;
        if abs(fMid) <= tol
            w = mid;
            return
        end
        if fLo * fMid <= 0
            hi = mid;
        else
            lo = mid;
            fLo = fMid;
        end
    end
    w = sqrt(lo * hi);
end

function value = eval_curve(kind, num, den, wValue, level)
    if strcmp(kind, 'mag')
        value = mag_db_scalar(num, den, wValue);
    else
        value = phase_near(num, den, wValue, level);
    end
end

function uniqueW = dedupe_frequencies(frequencies)
    frequencies = double(frequencies(:)).';
    frequencies = frequencies(isfinite(frequencies) & frequencies > 0);
    frequencies = sort(frequencies);
    uniqueW = zeros(1, 0);
    for index = 1:numel(frequencies)
        value = frequencies(index);
        if isempty(uniqueW) || abs(value - uniqueW(end)) / value > 1e-6
            uniqueW(end + 1) = value; %#ok<AGROW>
        end
    end
end

function value = phase_near(num, den, wValue, reference)
    h = eval_response(num, den, wValue);
    if ~isscalar(h)
        h = h(1);
    end
    if ~isfinite(h) || h == 0
        value = NaN;
        return
    end
    raw = angle(h) * 180 / pi;
    value = raw + 360 * round((reference - raw) / 360);
end

function value = phase_at(num, den, frequency, phase, wValue)
    finite = isfinite(phase);
    if ~any(finite)
        value = NaN;
        return
    end
    idx = find(finite);
    [~, local] = min(abs(log(frequency(idx)) - log(wValue)));
    reference = phase(idx(local));
    value = phase_near(num, den, wValue, reference);
end

function row = blank_margins()
    row = struct( ...
        'name', '', ...
        'form', '', ...
        'num', [], ...
        'den', [], ...
        'gain_crossover_rad_s', [], ...
        'phase_crossover_rad_s', [], ...
        'phase_margin_deg', NaN, ...
        'gain_margin_db', NaN, ...
        'phase_margin_rad_s', NaN, ...
        'gain_margin_rad_s', NaN);
end

function label = legend_label(name, phaseMargin, gainMargin)
    label = sprintf('%s (PM=%s deg, GM=%s dB)', name, legend_number(phaseMargin), legend_number(gainMargin));
end

function text = legend_number(value)
    if isnan(value)
        text = 'nan';
    elseif isinf(value)
        if value > 0
            text = 'inf';
        else
            text = '-inf';
        end
    else
        text = sprintf('%.4g', value);
    end
end

function fig = render_figure(frequency, magnitude, phase, labels, margins, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 80 980 680], ...
        'Name', 'bode-demo', 'NumberTitle', 'off');
    layout = tiledlayout(fig, 2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
    axMag = nexttile(layout);
    axPhase = nexttile(layout);
    colors = [
        31, 78, 121
        192, 57, 43
        61, 122, 106
        230, 126, 34
        108, 52, 131
        26, 82, 118
    ] / 255;
    styles = {'-', '--', '-.', ':'};
    hold(axMag, 'on');
    hold(axPhase, 'on');
    nSys = size(magnitude, 2);
    for index = 1:nSys
        color = colors(mod(index - 1, size(colors, 1)) + 1, :);
        style = styles{mod(index - 1, numel(styles)) + 1};
        mag = magnitude(:, index);
        ph = phase(:, index);
        mag(~isfinite(mag)) = NaN;
        ph(~isfinite(ph)) = NaN;
        semilogx(axMag, frequency, mag, 'Color', color, 'LineStyle', style, ...
            'LineWidth', 1.8, 'DisplayName', labels{index});
        semilogx(axPhase, frequency, ph, 'Color', color, 'LineStyle', style, 'LineWidth', 1.8);
        for wValue = margins(index).gain_crossover_rad_s(:).'
            plot(axMag, wValue, 0, 'o', 'Color', color, 'MarkerSize', 5.5, ...
                'HandleVisibility', 'off');
        end
        for wValue = margins(index).phase_crossover_rad_s(:).'
            markerPhase = interp_log(frequency, phase(:, index), wValue);
            if isfinite(markerPhase)
                plot(axPhase, wValue, markerPhase, 's', 'Color', color, 'MarkerSize', 5.5, ...
                    'HandleVisibility', 'off');
            end
        end
    end
    plot(axMag, [frequency(1) frequency(end)], [0 0], ':', 'Color', [0.4 0.4 0.4], ...
        'LineWidth', 1, 'HandleVisibility', 'off');
    refLevels = reference_phase_levels(phase);
    for level = refLevels(:).'
        plot(axPhase, [frequency(1) frequency(end)], [level level], ':', ...
            'Color', [0.4 0.4 0.4], 'LineWidth', 1, 'HandleVisibility', 'off');
    end
    padded_ylim(axMag, magnitude, 0, 12, 10);
    padded_ylim(axPhase, phase, -180, 25, 20);
    title(axMag, 'Bode diagram', 'Interpreter', 'none');
    ylabel(axMag, 'Magnitude (dB)');
    grid(axMag, 'on');
    axMag.XScale = 'log';
    axMag.GridColor = [0.82 0.82 0.82];
    axMag.GridAlpha = 0.35;
    box(axMag, 'on');
    legend(axMag, 'Location', 'best', 'Interpreter', 'none');
    set(axMag, 'FontSize', 11);
    xlabel(axPhase, 'Frequency (rad/s)');
    ylabel(axPhase, 'Phase (deg)');
    grid(axPhase, 'on');
    axPhase.XScale = 'log';
    axPhase.GridColor = [0.82 0.82 0.82];
    axPhase.GridAlpha = 0.35;
    box(axPhase, 'on');
    set(axPhase, 'FontSize', 11);
    linkaxes([axMag, axPhase], 'x');
    xlim(axPhase, [frequency(1), frequency(end)]);
    drawnow;
    if ~isempty(outputPng)
        folder = fileparts(outputPng);
        if ~isempty(folder) && exist(folder, 'dir') ~= 7
            mkdir(folder);
        end
        exportgraphics(fig, outputPng, 'Resolution', 150);
    end
    if ~showFig
        close(fig);
        fig = [];
    end
end

function y = interp_log(frequency, values, wValue)
    mask = isfinite(values) & isfinite(frequency) & frequency > 0;
    if nnz(mask) < 2
        y = NaN;
        return
    end
    y = interp1(log(frequency(mask)), values(mask), log(wValue), 'linear');
end

function levels = reference_phase_levels(phase)
    levels = -180;
    for index = 1:size(phase, 2)
        levels = [levels, phase_levels(phase(:, index))]; %#ok<AGROW>
    end
    levels = unique(levels);
end

function padded_ylim(ax, values, reference, includeWithin, minimumSpan)
    finite = values(isfinite(values));
    if isempty(finite)
        return
    end
    low = min(finite);
    high = max(finite);
    if low - includeWithin <= reference && reference <= high + includeWithin
        low = min(low, reference);
        high = max(high, reference);
    end
    span = max(high - low, minimumSpan);
    ylim(ax, [low - 0.12 * span, high + 0.22 * span]);
end

function specs = read_systems(csvPath)
    tbl = read_csv_table(csvPath);
    names = string(tbl.Properties.VariableNames);
    nSys = height(tbl);
    specs = cell(1, nSys);
    for row = 1:nSys
        item = struct();
        for index = 1:numel(names)
            item.(char(names(index))) = unwrap_cell(tbl{row, index});
        end
        specs{row} = build_system(item);
    end
end

function tbl = read_csv_table(csvPath)
    csvPath = char(strtrim(string(csvPath)));
    if exist(csvPath, 'file') ~= 2
        error('bode_demo:FileNotFound', 'CSV not found: %s', csvPath);
    end
    try
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
    catch
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve');
    end
    tbl = readtable(csvPath, opts);
    if height(tbl) == 0
        error('bode_demo:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
end

function value = unwrap_cell(value)
    if iscell(value) && numel(value) == 1
        value = value{1};
    end
end

function value = struct_lookup(data, keys)
    names = string(fieldnames(data));
    norms = strings(size(names));
    for index = 1:numel(names)
        norms(index) = normalize_key(names(index));
    end
    keys = string(keys);
    for index = 1:numel(keys)
        found = find(norms == normalize_key(keys(index)), 1, 'first');
        if ~isempty(found)
            value = data.(char(names(found)));
            return
        end
    end
    value = [];
end

function key = normalize_key(name)
    key = lower(strtrim(string(name)));
    key = regexprep(key, '[\s_\-]', '');
end

function tf = is_missing(value)
    if isempty(value)
        tf = true;
        return
    end
    if iscell(value)
        if isempty(value)
            tf = true;
            return
        end
        value = value{1};
        if isempty(value)
            tf = true;
            return
        end
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

function number = required_number(name, value)
    if is_missing(value)
        error('bode_demo:BadOption', '%s is required', name);
    end
    if iscell(value)
        value = value{1};
    end
    if isstring(value) || ischar(value)
        number = str2double(strtrim(string(value)));
    else
        number = double(value);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('bode_demo:BadOption', '%s must be a finite number', name);
    end
end

function number = optional_number(name, value, defaultValue)
    if is_missing(value)
        number = defaultValue;
        return
    end
    number = required_number(name, value);
end

function coeff = coeff_vector(value, name)
    if iscell(value)
        value = value{1};
    end
    if isstring(value) || ischar(value)
        text = strtrim(string(value));
        text = replace(text, ",", " ");
        text = replace(text, ";", " ");
        parts = split(text);
        parts = parts(strlength(parts) > 0);
        if isempty(parts)
            error('bode_demo:BadOption', '%s must be a coefficient vector', name);
        end
        coeff = zeros(1, numel(parts));
        for index = 1:numel(parts)
            coeff(index) = required_number(name, parts(index));
        end
        return
    end
    coeff = double(value(:)).';
    if isempty(coeff) || any(~isfinite(coeff))
        error('bode_demo:BadOption', '%s must be a finite coefficient vector', name);
    end
end

function ok = is_text(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = isstring(value) && isscalar(value);
end

function ok = is_text_scalar(value)
    ok = is_text(value);
end

function ok = is_known_key(key)
    keys = {'form', 'name', 'names', 'k', 'tau', 'wn', 'zeta', 'kp', 'ki', 'kd', ...
        'kd_n', 'w_min', 'w_max', 'n_points', 'frequency_rad_s', 'output_png', ...
        'show', 'num', 'den', 'systems'};
    ok = any(strcmp(key, keys));
end
