function result = pid_step_compare(plant, pid_sets, varargin)
%PID_STEP_COMPARE Compare PID step responses for a simple SISO plant.
%   RESULT = PID_STEP_COMPARE() simulates the classroom plant
%   G(s) = 1/(s+1)^2 under three PID sets (P, PI, PID).
%   RESULT = PID_STEP_COMPARE(PLANT, PID_SETS, 't_final', 20, 'dt', 0.01, ...
%       'output_png', 'step.png', 'show', false)
%
%   PLANT is a struct or a CSV path. Fields: form, k, wn, zeta, tau, theta,
%   and for form 'tf' also num and den (highest power first).
%   form is 'second_order', 'fopdt', or 'tf'. Pass [] for the default plant.
%
%   PID_SETS is a struct array with name, kp, ki, kd, an N-by-3 matrix
%   [kp ki kd], or a CSV path. Pass [] for the default P / PI / PID sets.
%
%   Name-value keys match the Python arguments: t_final, dt, setpoint,
%   kd_n, settle_pct, output_png, show.
%
%   Parallel PID with filtered derivative (base MATLAB, no toolbox):
%       C(s) = Kp + Ki/s + Kd * (kd_n * s) / (s + kd_n)
%   Unity negative feedback, fixed-step RK4, zero initial conditions.
%   Dead time is round(theta/dt) input-delay steps.
%
%   RESULT fields: time, y, u, setpoint, names, metrics, plant, t_final,
%   dt, kd_n, settle_pct, output_png, fig.
%   y and u are length(time) by n_sets. metrics(i) holds tr, mp_pct, ts,
%   ess, y_final, y_peak, peak_time, stable for that column.
%
%   Pipeline (same order as python/pid_step_compare.py):
%   1. Build a strictly proper plant.
%   2. Close each parallel PID in unity negative feedback.
%   3. Integrate with fixed-step RK4.
%   4. Measure 10-90 rise time, overshoot, settling time, steady-state error.
%   5. Optionally draw the overlaid responses.

    if nargin < 1
        plant = [];
    end
    if nargin < 2
        pid_sets = [];
    end

    parser = inputParser;
    parser.FunctionName = 'pid_step_compare';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('t_final', 20, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('dt', 0.01, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('setpoint', 1, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('kd_n', 10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('settle_pct', 2, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(varargin{:});
    opt = parser.Results;

    spec = normalize_plant(plant);
    sets = normalize_pid_sets(pid_sets);
    tFinal = double(opt.t_final);
    dt = double(opt.dt);
    setpoint = double(opt.setpoint);
    kdN = double(opt.kd_n);
    settlePct = double(opt.settle_pct);
    validate_simulation(tFinal, dt, setpoint, kdN, settlePct);

    [A, B, C] = transfer_to_ss(spec.num, spec.den);
    for index = 1:numel(sets)
        assert_step_size(A, dt, sets(index).kd, kdN);
    end

    nSets = numel(sets);
    y = [];
    u = [];
    time = [];
    for index = 1:nSets
        [time, yCol, uCol] = simulate_one(A, B, C, spec.theta, dt, tFinal, ...
            sets(index).kp, sets(index).ki, sets(index).kd, kdN, setpoint);
        if index == 1
            y = zeros(numel(time), nSets);
            u = zeros(numel(time), nSets);
        end
        y(:, index) = yCol;
        u(:, index) = uCol;
    end

    metrics = repmat(blank_metrics('x', 0, 0, 0), 1, nSets);
    labels = cell(1, nSets);
    names = strings(nSets, 1);
    for index = 1:nSets
        metrics(index) = step_metrics(time, y(:, index), setpoint, settlePct, ...
            sets(index).name, sets(index).kp, sets(index).ki, sets(index).kd);
        names(index) = string(sets(index).name);
        labels{index} = legend_label(sets(index).name, sets(index).kp, ...
            sets(index).ki, sets(index).kd, metrics(index).stable);
    end

    outputPng = char(strtrim(string(opt.output_png)));
    showFig = logical(opt.show);
    if strlength(strtrim(string(outputPng))) == 0
        outputPng = '';
    end
    if ~isempty(outputPng) || showFig
        fig = render_figure(time, y, u, labels, setpoint, [metrics.stable], outputPng, showFig);
    else
        fig = [];
    end

    result = struct();
    result.time = time;
    result.y = y;
    result.u = u;
    result.setpoint = setpoint;
    result.names = names;
    result.metrics = metrics;
    result.plant = spec;
    result.t_final = tFinal;
    result.dt = dt;
    result.kd_n = kdN;
    result.settle_pct = settlePct;
    result.output_png = outputPng;
    result.fig = fig;
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = isstring(value) && isscalar(value);
end

function validate_simulation(tFinal, dt, setpoint, kdN, settlePct)
    if ~(isfinite(tFinal) && tFinal > 0)
        error('pid_step_compare:BadOption', 't_final must be a positive finite number');
    end
    if ~(isfinite(dt) && dt > 0)
        error('pid_step_compare:BadOption', 'dt must be a positive finite number');
    end
    if ~isfinite(setpoint)
        error('pid_step_compare:BadOption', 'setpoint must be a finite number');
    end
    if ~(isfinite(kdN) && kdN > 0)
        error('pid_step_compare:BadOption', 'kd_n must be a positive finite number');
    end
    if ~(isfinite(settlePct) && settlePct > 0 && settlePct <= 100)
        error('pid_step_compare:BadOption', 'settle_pct must be in the interval (0, 100]');
    end
    nSteps = round(tFinal / dt);
    if nSteps < 2
        error('pid_step_compare:BadOption', 't_final must cover at least 2 steps');
    end
    if nSteps > 2000000
        error('pid_step_compare:BadOption', 't_final/dt is too large; increase dt or shorten t_final');
    end
end

function spec = default_plant()
    spec = struct('form', 'second_order', 'k', 1, 'wn', 1, 'zeta', 1, 'tau', 1, 'theta', 0);
end

function sets = default_pid_sets()
    sets = repmat(struct('name', '', 'kp', 0, 'ki', 0, 'kd', 0), 1, 3);
    sets(1) = struct('name', 'P', 'kp', 2, 'ki', 0, 'kd', 0);
    sets(2) = struct('name', 'PI', 'kp', 2, 'ki', 1.5, 'kd', 0);
    sets(3) = struct('name', 'PID', 'kp', 2, 'ki', 1.5, 'kd', 0.8);
end

function spec = normalize_plant(plant)
    if isempty(plant)
        plant = default_plant();
    elseif ischar(plant) || (isstring(plant) && isscalar(plant))
        plant = read_plant_csv(char(string(plant)));
    end
    if ~isstruct(plant) || numel(plant) ~= 1
        error('pid_step_compare:BadOption', 'plant must be a scalar struct or a CSV path');
    end

    formValue = struct_lookup(plant, {'form'});
    if is_missing(formValue)
        form = 'second_order';
    else
        form = lower(char(strtrim(as_text(formValue))));
    end
    if ~any(strcmp(form, {'second_order', 'fopdt', 'tf'}))
        error('pid_step_compare:BadOption', 'form must be one of: second_order, fopdt, tf');
    end

    kGain = optional_number('k', struct_lookup(plant, {'k', 'gain'}), 1);
    wn = optional_number('wn', struct_lookup(plant, {'wn', 'omegan'}), 1);
    zeta = optional_number('zeta', struct_lookup(plant, {'zeta'}), 1);
    tau = optional_number('tau', struct_lookup(plant, {'tau'}), 1);
    theta = optional_number('theta', struct_lookup(plant, {'theta', 'delay', 'l'}), 0);
    if theta < 0
        error('pid_step_compare:BadOption', 'theta must be >= 0');
    end

    if strcmp(form, 'second_order')
        if ~(wn > 0)
            error('pid_step_compare:BadOption', 'wn must be positive');
        end
        num = kGain * wn * wn;
        den = [1, 2 * zeta * wn, wn * wn];
    elseif strcmp(form, 'fopdt')
        if ~(tau > 0)
            error('pid_step_compare:BadOption', 'tau must be positive');
        end
        num = kGain;
        den = [tau, 1];
    else
        num = struct_lookup(plant, {'num', 'numerator'});
        den = struct_lookup(plant, {'den', 'denominator'});
        if is_missing(num) || is_missing(den)
            error('pid_step_compare:BadOption', 'form ''tf'' requires num and den coefficients');
        end
        num = coeff_vector(num, 'num');
        den = coeff_vector(den, 'den');
    end
    [num, den] = prepare_coefficients(num, den);
    spec = struct('form', form, 'k', kGain, 'wn', wn, 'zeta', zeta, ...
        'tau', tau, 'theta', theta, 'num', num, 'den', den);
end

function sets = normalize_pid_sets(pidSets)
    if isempty(pidSets)
        sets = default_pid_sets();
        return
    end
    if ischar(pidSets) || (isstring(pidSets) && isscalar(pidSets))
        pidSets = read_pid_csv(char(string(pidSets)));
    end

    used = strings(0, 1);
    if isnumeric(pidSets)
        if ndims(pidSets) > 2 || size(pidSets, 2) ~= 3 || isempty(pidSets)
            error('pid_step_compare:BadOption', ...
                'numeric pid_sets must be an N-by-3 matrix of kp, ki, kd');
        end
        nSets = size(pidSets, 1);
        sets = repmat(struct('name', '', 'kp', 0, 'ki', 0, 'kd', 0), 1, nSets);
        for index = 1:nSets
            kp = required_number('kp', pidSets(index, 1));
            ki = required_number('ki', pidSets(index, 2));
            kd = required_number('kd', pidSets(index, 3));
            [name, used] = auto_name(kp, ki, kd, used);
            sets(index) = struct('name', char(name), 'kp', kp, 'ki', ki, 'kd', kd);
        end
        return
    end

    if iscell(pidSets)
        nSets = numel(pidSets);
        items = pidSets;
    elseif isstruct(pidSets)
        nSets = numel(pidSets);
        items = cell(1, nSets);
        for index = 1:nSets
            items{index} = pidSets(index);
        end
    else
        error('pid_step_compare:BadOption', ...
            'pid_sets must be a struct array, an N-by-3 matrix, or a CSV path');
    end
    if nSets == 0
        error('pid_step_compare:BadOption', 'pid_sets must contain at least one controller');
    end

    sets = repmat(struct('name', '', 'kp', 0, 'ki', 0, 'kd', 0), 1, nSets);
    for index = 1:nSets
        item = items{index};
        if ~isstruct(item)
            error('pid_step_compare:BadOption', 'each PID set must be a struct with kp, ki, kd');
        end
        kp = required_number('kp', struct_lookup(item, {'kp'}));
        ki = optional_number('ki', struct_lookup(item, {'ki'}), 0);
        kd = optional_number('kd', struct_lookup(item, {'kd'}), 0);
        nameValue = struct_lookup(item, {'name'});
        if is_missing(nameValue)
            nameText = "";
        else
            nameText = strtrim(as_text(nameValue));
        end
        if strlength(nameText) == 0
            [nameText, used] = auto_name(kp, ki, kd, used);
        elseif any(used == nameText)
            error('pid_step_compare:BadOption', 'duplicate PID name: %s', char(nameText));
        else
            used(end + 1, 1) = nameText; %#ok<AGROW>
        end
        sets(index) = struct('name', char(nameText), 'kp', kp, 'ki', ki, 'kd', kd);
    end
end

function [name, used] = auto_name(kp, ki, kd, used)
    if ki == 0 && kd == 0
        base = "P";
    elseif kd == 0
        base = "PI";
    elseif ki == 0
        base = "PD";
    else
        base = "PID";
    end
    name = base;
    suffix = 2;
    while any(used == name)
        name = base + string(suffix);
        suffix = suffix + 1;
    end
    used(end + 1, 1) = name; %#ok<AGROW>
end

function [A, B, C] = transfer_to_ss(num, den)
    num = double(num(:)).';
    den = double(den(:)).';
    num = num / den(1);
    den = den / den(1);
    order = numel(den) - 1;
    bCoeff = zeros(1, order);
    bCoeff(order - numel(num) + 1:end) = num;
    A = zeros(order, order);
    A(1, :) = -den(2:end);
    if order > 1
        A(2:end, 1:end-1) = eye(order - 1);
    end
    B = zeros(order, 1);
    B(1) = 1;
    C = bCoeff;
end

function assert_step_size(A, dt, kd, kdN)
    poles = eig(A);
    rate = max(abs(poles));
    if isempty(rate)
        rate = 0;
    end
    if kd ~= 0
        rate = max(rate, kdN);
    end
    if rate > 0 && dt * rate > 2
        error('pid_step_compare:BadOption', ...
            ['dt is large for this plant or derivative filter. ', ...
            'Fastest rate is about %.4g rad/s; use dt < %.4g s.'], ...
            rate, 2 / rate);
    end
end

function [time, y, u] = simulate_one(A, B, C, theta, dt, tFinal, kp, ki, kd, kdN, setpoint)
    nSteps = round(tFinal / dt);
    time = (0:nSteps).' * dt;
    order = size(A, 1);
    state = zeros(order + 2, 1);
    nDelay = round(theta / dt);
    buf = zeros(nDelay, 1);
    y = zeros(numel(time), 1);
    u = zeros(numel(time), 1);
    for index = 1:numel(time)
        [y(index), u(index)] = output_of(state, C, kp, ki, kd, kdN, setpoint);
        if index == numel(time)
            break
        end
        if nDelay > 0
            uHold = buf(1);
            holdInput = true;
            buf(1:end-1) = buf(2:end);
            buf(end) = u(index);
        else
            uHold = 0;
            holdInput = false;
        end
        state = rk4_step(state, dt, A, B, C, kp, ki, kd, kdN, setpoint, holdInput, uHold);
    end
end

function [yNow, uNow] = output_of(state, C, kp, ki, kd, kdN, setpoint)
    order = numel(C);
    yNow = C * state(1:order);
    err = setpoint - yNow;
    uNow = kp * err;
    if ki ~= 0
        uNow = uNow + ki * state(order + 1);
    end
    if kd ~= 0
        uNow = uNow + kd * kdN * (err - state(order + 2));
    end
end

function dz = rhs(state, A, B, C, kp, ki, kd, kdN, setpoint, holdInput, uHold)
    order = numel(C);
    yNow = C * state(1:order);
    err = setpoint - yNow;
    uNow = kp * err;
    if ki ~= 0
        uNow = uNow + ki * state(order + 1);
    end
    if kd ~= 0
        uNow = uNow + kd * kdN * (err - state(order + 2));
    end
    if holdInput
        uPlant = uHold;
    else
        uPlant = uNow;
    end
    dz = zeros(order + 2, 1);
    dz(1:order) = A * state(1:order) + B * uPlant;
    if ki ~= 0
        dz(order + 1) = err;
    end
    if kd ~= 0
        dz(order + 2) = kdN * (err - state(order + 2));
    end
end

function state = rk4_step(state, dt, A, B, C, kp, ki, kd, kdN, setpoint, holdInput, uHold)
    k1 = rhs(state, A, B, C, kp, ki, kd, kdN, setpoint, holdInput, uHold);
    k2 = rhs(state + 0.5 * dt * k1, A, B, C, kp, ki, kd, kdN, setpoint, holdInput, uHold);
    k3 = rhs(state + 0.5 * dt * k2, A, B, C, kp, ki, kd, kdN, setpoint, holdInput, uHold);
    k4 = rhs(state + dt * k3, A, B, C, kp, ki, kd, kdN, setpoint, holdInput, uHold);
    state = state + (dt / 6) * (k1 + 2 * k2 + 2 * k3 + k4);
end

function row = step_metrics(time, y, setpoint, settlePct, name, kp, ki, kd)
    y = y(:);
    time = time(:);
    if any(~isfinite(y))
        row = blank_metrics(name, kp, ki, kd);
        return
    end
    nTail = max(5, round(0.05 * numel(y)));
    nTail = min(nTail, numel(y));
    yFinal = mean(y(end - nTail + 1:end));
    stableFlag = response_is_stable(y, setpoint);
    if abs(yFinal) < 1e-9
        if setpoint >= 0
            direction = 1;
        else
            direction = -1;
        end
        tr = NaN;
        mpPct = NaN;
        if direction > 0
            [yPeak, peakIdx] = max(y);
        else
            [yPeak, peakIdx] = min(y);
        end
    else
        if yFinal >= 0
            direction = 1;
        else
            direction = -1;
        end
        tLow = first_reach(time, y, 0.10 * yFinal, direction);
        tHigh = first_reach(time, y, 0.90 * yFinal, direction);
        if isfinite(tLow) && isfinite(tHigh) && tHigh >= tLow
            tr = tHigh - tLow;
        else
            tr = NaN;
        end
        if direction > 0
            [yExt, peakIdx] = max(y);
        else
            [yExt, peakIdx] = min(y);
        end
        yPeak = yExt;
        overshoot = (yExt - yFinal) * direction;
        mpPct = max(overshoot, 0) / abs(yFinal) * 100;
    end

    band = (settlePct / 100) * max(abs(yFinal), 1e-12);
    inside = abs(y - yFinal) <= band;
    if inside(end)
        outside = find(~inside);
        if isempty(outside)
            ts = time(1);
        else
            ts = enter_band(time, y, yFinal, band, outside(end));
        end
    else
        ts = NaN;
    end

    row = struct( ...
        'name', char(name), ...
        'kp', kp, ...
        'ki', ki, ...
        'kd', kd, ...
        'tr', tr, ...
        'mp_pct', mpPct, ...
        'ts', ts, ...
        'ess', setpoint - yFinal, ...
        'y_final', yFinal, ...
        'y_peak', yPeak, ...
        'peak_time', time(peakIdx), ...
        'stable', logical(stableFlag));
end

function row = blank_metrics(name, kp, ki, kd)
    row = struct( ...
        'name', char(name), ...
        'kp', kp, ...
        'ki', ki, ...
        'kd', kd, ...
        'tr', NaN, ...
        'mp_pct', NaN, ...
        'ts', NaN, ...
        'ess', NaN, ...
        'y_final', NaN, ...
        'y_peak', NaN, ...
        'peak_time', NaN, ...
        'stable', false);
end

function ok = response_is_stable(y, setpoint)
    if any(~isfinite(y))
        ok = false;
        return
    end
    mid = y(floor(numel(y) / 2) + 1);
    tail = y(end);
    scale = max(abs(setpoint), 1);
    if abs(tail) > 8 * scale && abs(tail) > 3 * abs(mid) + scale
        ok = false;
        return
    end
    ok = true;
end

function t = first_reach(time, y, level, direction)
    if direction > 0
        hit = find(y >= level, 1, 'first');
    else
        hit = find(y <= level, 1, 'first');
    end
    if isempty(hit)
        t = NaN;
        return
    end
    if hit == 1
        t = time(1);
        return
    end
    y0 = y(hit - 1);
    y1 = y(hit);
    if y1 == y0
        t = time(hit);
        return
    end
    frac = (level - y0) / (y1 - y0);
    frac = min(max(frac, 0), 1);
    t = time(hit - 1) + frac * (time(hit) - time(hit - 1));
end

function t = enter_band(time, y, yFinal, band, outsideIndex)
    nxt = outsideIndex + 1;
    if nxt > numel(y)
        t = time(end);
        return
    end
    y0 = y(outsideIndex);
    y1 = y(nxt);
    t0 = time(outsideIndex);
    t1 = time(nxt);
    if y1 == y0
        t = t1;
        return
    end
    candidates = [];
    levels = [yFinal - band, yFinal + band];
    for level = levels
        if (y0 - level) * (y1 - level) <= 0
            frac = (level - y0) / (y1 - y0);
            if frac > 0 && frac <= 1
                candidates(end + 1) = t0 + frac * (t1 - t0); %#ok<AGROW>
            end
        end
    end
    if isempty(candidates)
        t = t1;
    else
        t = min(candidates);
    end
end

function label = legend_label(name, kp, ki, kd, stableFlag)
    label = sprintf('%s (Kp=%.4g, Ki=%.4g, Kd=%.4g)', name, kp, ki, kd);
    if ~stableFlag
        label = [label, ' diverging'];
    end
end

function fig = render_figure(time, y, u, labels, setpoint, stableFlags, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [100 100 980 680], ...
        'Name', 'pid-step-compare', 'NumberTitle', 'off');
    layout = tiledlayout(fig, 2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
    axY = nexttile(layout);
    axU = nexttile(layout);
    colors = [
        31, 78, 121
        192, 57, 43
        61, 122, 106
        230, 126, 34
        108, 52, 131
        26, 82, 118
    ] / 255;
    styles = {'-', '--', '-.', ':'};
    hold(axY, 'on');
    hold(axU, 'on');
    nSets = size(y, 2);
    for index = 1:nSets
        color = colors(mod(index - 1, size(colors, 1)) + 1, :);
        style = styles{mod(index - 1, numel(styles)) + 1};
        yPlot = y(:, index);
        uPlot = u(:, index);
        yPlot(~isfinite(yPlot)) = NaN;
        uPlot(~isfinite(uPlot)) = NaN;
        plot(axY, time, yPlot, 'Color', color, 'LineStyle', style, ...
            'LineWidth', 1.8, 'DisplayName', labels{index});
        plot(axU, time, uPlot, 'Color', color, 'LineStyle', style, 'LineWidth', 1.5);
    end
    yline(axY, setpoint, ':', 'Color', [0.4 0.4 0.4], 'LineWidth', 1.1, 'DisplayName', 'Setpoint');
    focus_ylim(axY, y, setpoint, stableFlags);
    focus_ylim(axU, u, 0, stableFlags);
    title(axY, 'PID step response comparison', 'Interpreter', 'none');
    ylabel(axY, 'Output y');
    grid(axY, 'on');
    axY.GridColor = [0.82 0.82 0.82];
    axY.GridAlpha = 0.35;
    box(axY, 'on');
    legend(axY, 'Location', 'best', 'Interpreter', 'none');
    set(axY, 'FontSize', 11);
    title(axU, 'Control effort', 'Interpreter', 'none');
    xlabel(axU, 'Time (s)');
    ylabel(axU, 'Control u');
    grid(axU, 'on');
    axU.GridColor = [0.82 0.82 0.82];
    axU.GridAlpha = 0.35;
    box(axU, 'on');
    set(axU, 'FontSize', 11);
    drawnow;
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

function focus_ylim(ax, series, reference, stableFlags)
    kept = [];
    for index = 1:size(series, 2)
        column = series(:, index);
        if stableFlags(index) && all(isfinite(column))
            kept = [kept; column]; %#ok<AGROW>
        end
    end
    if isempty(kept)
        return
    end
    low = min(kept);
    high = max(kept);
    low = min([low, 0, reference]);
    high = max([high, 0, reference]);
    span = max(high - low, 0.5);
    ylim(ax, [low - 0.08 * span, high + 0.22 * span]);
end

function tbl = read_csv_table(csvPath)
    csvPath = char(strtrim(string(csvPath)));
    if ~isfile(csvPath)
        error('pid_step_compare:FileNotFound', 'CSV not found: %s', csvPath);
    end
    try
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
    catch
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve');
    end
    tbl = readtable(csvPath, opts);
    if height(tbl) == 0
        error('pid_step_compare:EmptyCsv', 'CSV has no data rows: %s', csvPath);
    end
end

function plant = read_plant_csv(csvPath)
    tbl = read_csv_table(csvPath);
    names = string(tbl.Properties.VariableNames);
    plant = struct();
    for index = 1:numel(names)
        plant.(char(names(index))) = unwrap_cell(tbl{1, index});
    end
end

function sets = read_pid_csv(csvPath)
    tbl = read_csv_table(csvPath);
    names = string(tbl.Properties.VariableNames);
    nSets = height(tbl);
    sets = cell(1, nSets);
    for row = 1:nSets
        item = struct();
        for index = 1:numel(names)
            item.(char(names(index))) = unwrap_cell(tbl{row, index});
        end
        sets{row} = item;
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

function text = as_text(value)
    if iscell(value)
        if isempty(value)
            text = "";
            return
        end
        value = value{1};
    end
    text = strtrim(string(value));
end

function number = required_number(name, value)
    if is_missing(value)
        error('pid_step_compare:BadOption', '%s is required', name);
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
        error('pid_step_compare:BadOption', '%s must be a finite number', name);
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
            error('pid_step_compare:BadOption', '%s must be a coefficient vector', name);
        end
        coeff = zeros(1, numel(parts));
        for index = 1:numel(parts)
            coeff(index) = required_number(name, parts(index));
        end
        return
    end
    coeff = double(value(:)).';
    if isempty(coeff) || any(~isfinite(coeff))
        error('pid_step_compare:BadOption', '%s must be a finite coefficient vector', name);
    end
end

function [num, den] = prepare_coefficients(num, den)
    num = double(num(:)).';
    den = double(den(:)).';
    if isempty(num) || isempty(den)
        error('pid_step_compare:BadOption', 'num and den must be non-empty');
    end
    if any(~isfinite(num)) || any(~isfinite(den))
        error('pid_step_compare:BadOption', 'num and den must be finite');
    end
    while numel(den) > 1 && den(1) == 0
        den = den(2:end);
    end
    while numel(num) > 1 && num(1) == 0
        num = num(2:end);
    end
    if den(1) == 0
        error('pid_step_compare:BadOption', 'denominator leading coefficient must be nonzero');
    end
    if numel(num) >= numel(den)
        error('pid_step_compare:BadOption', ...
            'plant must be strictly proper (numerator degree < denominator degree)');
    end
    if numel(den) - 1 > 8
        error('pid_step_compare:BadOption', 'plant order must be <= 8');
    end
    if numel(den) < 2
        error('pid_step_compare:BadOption', 'plant order must be at least 1');
    end
end
