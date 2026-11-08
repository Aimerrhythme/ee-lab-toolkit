function result = load_curve_dnn_fit(source, varargin)
%LOAD_CURVE_DNN_FIT Fit one daily load curve with a polynomial and a tanh MLP.
%   RESULT = LOAD_CURVE_DNN_FIT(CSVPATH, 'degree', 5, 'hidden', 8, ...
%       'epochs', 2000, 'seed', 0, 'normalize', 'peak')
%   RESULT = LOAD_CURVE_DNN_FIT(POWER)
%   RESULT = LOAD_CURVE_DNN_FIT(HOURS, POWER, 'time_unit', 'hour')
%   RESULT = LOAD_CURVE_DNN_FIT(TIMESTAMPS, POWER)
%
%   Same algorithm as python/load_curve_dnn_fit.py, in base MATLAB (no
%   toolbox). Time of day is scaled to u = 2*(minute/1440)-1. Load is
%   normalized with peak (default), minmax, or none. Both models fit y.
%   RMSE, MAE, and max absolute error are reported in kW after mapping back.
%
%   The network is 1-hidden-1 with tanh and a linear output, trained by
%   full-batch Adam. beta^t is a running product. Weights use the shared
%   32-bit LCG and Glorot uniform limits; biases start at 0.

    if nargin < 1
        source = [];
    end
    [source, power, rest] = split_source(source, varargin);
    parser = inputParser;
    parser.FunctionName = 'load_curve_dnn_fit';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('degree', 5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('hidden', 8, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('epochs', 2000, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('learning_rate', 0.05, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('beta1', 0.9, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('beta2', 0.999, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('epsilon', 1e-8, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('seed', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('normalize', 'peak', @is_text_scalar);
    parser.addParameter('time_unit', 'auto', @is_text_scalar);
    parser.addParameter('time_col', '', @is_text_scalar);
    parser.addParameter('power_col', '', @is_text_scalar);
    parser.addParameter('day', '', @is_text_scalar);
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    degree = integral_number('degree', opt.degree, 0, 'degree must be a non-negative integer');
    hidden = integral_number('hidden', opt.hidden, 1, 'hidden must be a positive integer');
    epochs = integral_number('epochs', opt.epochs, 1, 'epochs must be a positive integer');
    seed = integral_number('seed', opt.seed, 0, 'seed must be a non-negative integer');
    learningRate = positive_number('learning_rate', opt.learning_rate);
    beta1 = unit_interval('beta1', opt.beta1);
    beta2 = unit_interval('beta2', opt.beta2);
    epsilon = positive_number('epsilon', opt.epsilon);
    normalize = normalize_name(opt.normalize);
    timeUnit = time_unit_name(opt.time_unit);
    showFig = as_bool('show', opt.show);

    [minute, powerKw, date, dates, averaged, nRows, nMissing, nDuplicates] = resolve_input( ...
        opt, source, power, timeUnit);
    nSamples = numel(powerKw);
    if nSamples < 2
        error('load_curve_dnn_fit:BadOption', 'a load curve needs at least 2 samples');
    end
    if degree >= nSamples
        error('load_curve_dnn_fit:BadOption', ...
            'degree must be lower than the number of samples (%d)', nSamples);
    end
    [y, scale, offset, peakKw, minKw] = normalize_power(powerKw, normalize);
    u = zeros(nSamples, 1);
    hour = zeros(nSamples, 1);
    for index = 1:nSamples
        u(index) = 2 * (minute(index) / 1440) - 1;
        hour(index) = minute(index) / 60;
    end
    polyCoeff = fit_polynomial(u, y, degree);
    polyY = eval_polynomial(u, polyCoeff);
    [w1, b1, w2, b2] = train_mlp(u, y, hidden, epochs, learningRate, beta1, beta2, epsilon, seed);
    dnnY = predict_mlp(u, w1, b1, w2, b2);
    polyKw = zeros(nSamples, 1);
    dnnKw = zeros(nSamples, 1);
    polyResidual = zeros(nSamples, 1);
    dnnResidual = zeros(nSamples, 1);
    for index = 1:nSamples
        polyKw(index) = polyY(index) * scale + offset;
        dnnKw(index) = dnnY(index) * scale + offset;
        polyResidual(index) = polyKw(index) - powerKw(index);
        dnnResidual(index) = dnnKw(index) - powerKw(index);
    end
    [polyRmse, polyMae, polyMaxAbs] = error_metrics(polyResidual);
    [dnnRmse, dnnMae, dnnMaxAbs] = error_metrics(dnnResidual);
    polyMse = mse_value(y, polyY);
    dnnMse = mse_value(y, dnnY);
    step = step_minutes(minute);
    summary = format_result(nSamples, degree, hidden, epochs, learningRate, seed, normalize, ...
        date, averaged, step, polyRmse, polyMae, polyMaxAbs, polyMse, ...
        dnnRmse, dnnMae, dnnMaxAbs, dnnMse, nRows, nMissing, nDuplicates, ...
        numel(dates), peakKw, minKw);

    outputCsv = as_char(opt.output_csv);
    outputPng = as_char(opt.output_png);
    if ~isempty(outputCsv)
        write_curve(outputCsv, hour, minute, powerKw, polyKw, dnnKw, polyResidual, dnnResidual);
    end
    if ~isempty(outputPng) || showFig
        fig = render_figure(hour, powerKw, polyKw, dnnKw, polyResidual, dnnResidual, ...
            degree, hidden, polyRmse, dnnRmse, outputPng, showFig);
    else
        fig = [];
    end

    result = struct();
    result.hour = hour(:);
    result.minute = minute(:);
    result.power_kw = powerKw(:);
    result.u = u(:);
    result.y = y(:);
    result.poly_y = polyY(:);
    result.dnn_y = dnnY(:);
    result.poly_kw = polyKw(:);
    result.dnn_kw = dnnKw(:);
    result.poly_residual_kw = polyResidual(:);
    result.dnn_residual_kw = dnnResidual(:);
    result.poly_coeff = polyCoeff(:);
    result.w1 = w1(:);
    result.b1 = b1(:);
    result.w2 = w2(:);
    result.b2 = b2;
    result.degree = degree;
    result.hidden = hidden;
    result.epochs = epochs;
    result.learning_rate = learningRate;
    result.beta1 = beta1;
    result.beta2 = beta2;
    result.epsilon = epsilon;
    result.seed = seed;
    result.normalize = normalize;
    result.activation = 'tanh';
    result.poly_rmse = polyRmse;
    result.poly_mae = polyMae;
    result.poly_max_abs = polyMaxAbs;
    result.poly_mse = polyMse;
    result.dnn_rmse = dnnRmse;
    result.dnn_mae = dnnMae;
    result.dnn_max_abs = dnnMaxAbs;
    result.dnn_mse = dnnMse;
    result.peak_kw = peakKw;
    result.min_kw = minKw;
    result.scale_kw = scale;
    result.offset_kw = offset;
    result.date = date;
    result.dates = dates(:);
    result.n_samples = nSamples;
    result.n_days = numel(dates);
    result.n_rows = nRows;
    result.n_missing = nMissing;
    result.n_duplicates = nDuplicates;
    result.averaged = logical(averaged);
    result.step_minutes = step;
    result.summary = summary;
    result.output_csv = outputCsv;
    result.output_png = outputPng;
    result.fig = fig;
end

function [source, power, rest] = split_source(source, args)
    power = [];
    rest = args;
    if is_parameter_name(source)
        if isempty(args)
            rest = {source};
        else
            rest = [{source}, args];
        end
        source = [];
        return
    end
    if isnumeric(source) && isscalar(source)
        error('load_curve_dnn_fit:BadOption', ...
            'pass a CSV path, a power vector, or time and power; the first argument is not a scalar');
    end
    if is_time_vector(source) && ~isempty(args) && is_numeric_vector(args{1})
        power = args{1};
        if numel(args) < 2
            rest = {};
        else
            rest = args(2:end);
        end
    elseif ~isempty(source) && ~is_text_scalar(source) && ~is_numeric_vector(source) && ~is_time_vector(source)
        error('load_curve_dnn_fit:BadOption', ...
            'source must be a CSV path, a power vector, or time with power');
    end
end

function tf = is_time_vector(value)
    if is_numeric_vector(value)
        tf = true;
        return
    end
    if is_datetime_value(value) && ~isempty(value)
        tf = true;
        return
    end
    if iscell(value) && ~isempty(value)
        tf = true;
        return
    end
    if is_string_value(value) && numel(value) > 1
        tf = true;
        return
    end
    tf = false;
end

function tf = is_numeric_vector(value)
    tf = isnumeric(value) && ~isempty(value) && isvector(value);
end

function [minute, powerKw, date, dates, averaged, nRows, nMissing, nDuplicates] = resolve_input(opt, source, power, timeUnit)
    if ~isempty(power)
        if ~isempty(as_char(opt.csv_path))
            error('load_curve_dnn_fit:BadOption', 'pass time and power, or a CSV path, not both');
        end
        if ~isempty(as_char(opt.time_col)) || ~isempty(as_char(opt.power_col))
            error('load_curve_dnn_fit:BadOption', ...
                'time_col and power_col apply to a CSV, not to time and power vectors');
        end
        values = power_vector(power, 'power');
        if is_numeric_vector(source)
            [minutes, ~] = numeric_minutes(power_vector(source, 'time'), timeUnit);
            if numel(minutes) ~= numel(values)
                error('load_curve_dnn_fit:BadOption', 'time and power must have the same length');
            end
            label = vector_day(as_char(opt.day));
            datesIn = cell(numel(values), 1);
            for index = 1:numel(values)
                datesIn{index} = label;
            end
            [minute, powerKw, date, dates, averaged, nRows, nDuplicates] = pack_samples( ...
                datesIn, minutes, values);
            nMissing = 0;
            return
        end
        if ~strcmp(timeUnit, 'auto')
            error('load_curve_dnn_fit:BadOption', 'time_unit applies to numeric time, not timestamps');
        end
        if ~isempty(as_char(opt.day))
            error('load_curve_dnn_fit:BadOption', ...
                'day applies to numeric time or a power vector, not to timestamps');
        end
        [datesIn, minutes] = timestamp_samples(source);
        if numel(minutes) ~= numel(values)
            error('load_curve_dnn_fit:BadOption', 'time and power must have the same length');
        end
        [minute, powerKw, date, dates, averaged, nRows, nDuplicates] = pack_samples(datesIn, minutes, values);
        nMissing = 0;
        return
    end
    if is_numeric_vector(source)
        if ~isempty(as_char(opt.csv_path))
            error('load_curve_dnn_fit:BadOption', 'pass a power vector or a CSV path, not both');
        end
        if ~strcmp(timeUnit, 'auto')
            error('load_curve_dnn_fit:BadOption', 'time_unit applies when time is passed');
        end
        if ~isempty(as_char(opt.time_col)) || ~isempty(as_char(opt.power_col))
            error('load_curve_dnn_fit:BadOption', ...
                'time_col and power_col apply to a CSV, not to a power vector');
        end
        values = power_vector(source, 'power');
        count = numel(values);
        step = 1440 / count;
        minutes = zeros(count, 1);
        datesIn = cell(count, 1);
        label = vector_day(as_char(opt.day));
        for index = 1:count
            minutes(index) = (index - 1) * step;
            datesIn{index} = label;
        end
        [minute, powerKw, date, dates, averaged, nRows, nDuplicates] = pack_samples(datesIn, minutes, values);
        nMissing = 0;
        return
    end
    if ~strcmp(timeUnit, 'auto')
        error('load_curve_dnn_fit:BadOption', 'time_unit applies to numeric time, not a CSV');
    end
    if ~isempty(as_char(opt.day))
        error('load_curve_dnn_fit:BadOption', 'day applies to numeric time or a power vector, not a CSV');
    end
    csvPath = as_char(opt.csv_path);
    if is_text_scalar(source) && ~isempty(as_char(source))
        if ~isempty(csvPath)
            error('load_curve_dnn_fit:BadOption', 'pass a CSV path once, either positionally or as csv_path=');
        end
        csvPath = as_char(source);
    elseif ~isempty(source)
        error('load_curve_dnn_fit:BadOption', 'source must be a CSV path, a power vector, or time with power');
    end
    if isempty(csvPath)
        error('load_curve_dnn_fit:BadOption', 'pass a CSV path, a power vector, or time and power');
    end
    [rows, nMissing] = read_power_csv(csvPath, as_char(opt.time_col), as_char(opt.power_col));
    if isempty(rows)
        error('load_curve_dnn_fit:BadOption', 'No power samples remain after cleaning');
    end
    count = size(rows, 1);
    datesIn = cell(count, 1);
    minutes = rows(:, 4);
    values = rows(:, 5);
    for index = 1:count
        datesIn{index} = sprintf('%04d-%02d-%02d', rows(index, 1), rows(index, 2), rows(index, 3));
    end
    [minute, powerKw, date, dates, averaged, nRows, nDuplicates] = pack_samples(datesIn, minutes, values);
end

function values = power_vector(value, name)
    if ischar(value) || is_string_value(value) || iscell(value) || is_datetime_value(value)
        error('load_curve_dnn_fit:BadOption', '%s must be a numeric vector', name);
    end
    if ~isnumeric(value) || isempty(value) || ~isvector(value)
        if isempty(value)
            error('load_curve_dnn_fit:BadOption', '%s must not be empty', name);
        end
        error('load_curve_dnn_fit:BadOption', '%s must be a numeric vector', name);
    end
    values = double(value(:));
    if any(~isfinite(values))
        error('load_curve_dnn_fit:BadOption', '%s must be finite', name);
    end
end

function [minutes, basis] = numeric_minutes(values, timeUnit)
    if strcmp(timeUnit, 'auto')
        timeUnit = infer_time_unit(values);
    end
    if strcmp(timeUnit, 'hour')
        if any(values < 0 | values >= 24)
            error('load_curve_dnn_fit:BadOption', 'numeric hours must be in [0, 24)');
        end
        minutes = values(:) * 60;
        basis = 'hour';
        return
    end
    if strcmp(timeUnit, 'minute')
        if any(values < 0 | values >= 1440)
            error('load_curve_dnn_fit:BadOption', 'numeric minutes must be in [0, 1440)');
        end
        minutes = values(:);
        basis = 'minute';
        return
    end
    if any(values < 0 | values >= 1)
        error('load_curve_dnn_fit:BadOption', 'day fractions must be in [0, 1)');
    end
    minutes = values(:) * 1440;
    basis = 'dayfrac';
end

function unit = infer_time_unit(values)
    lowest = min_value(values);
    highest = max_value(values);
    if lowest >= 0 && highest < 24
        unit = 'hour';
        return
    end
    if lowest >= 0 && highest < 1440
        unit = 'minute';
        return
    end
    error('load_curve_dnn_fit:BadOption', 'could not infer time_unit; pass hour, minute, or dayfrac');
end

function [datesIn, minutes] = timestamp_samples(time)
    parts = time_parts(time);
    count = size(parts, 1);
    datesIn = cell(count, 1);
    minutes = parts(:, 4);
    for index = 1:count
        datesIn{index} = sprintf('%04d-%02d-%02d', parts(index, 1), parts(index, 2), parts(index, 3));
    end
end

function parts = time_parts(time)
    if is_datetime_value(time)
        parts = parts_from_datetime(time);
        return
    end
    if iscell(time)
        texts = time(:);
    elseif is_string_value(time)
        texts = cell(numel(time), 1);
        for index = 1:numel(time)
            texts{index} = as_char(time(index));
        end
    elseif is_text_scalar(time)
        texts = {as_char(time)};
    else
        error('load_curve_dnn_fit:BadOption', 'time must be a vector of timestamps or numbers');
    end
    parts = zeros(numel(texts), 4);
    for index = 1:numel(texts)
        item = texts{index};
        if is_datetime_value(item)
            parts(index, :) = parts_from_datetime(item);
            continue
        end
        [year, month, dayNumber, minuteOfDay, ok] = parse_timestamp(item);
        if ~ok
            error('load_curve_dnn_fit:BadOption', 'could not parse timestamp ''%s''', as_char(item));
        end
        parts(index, :) = [year, month, dayNumber, minuteOfDay];
    end
end

function parts = parts_from_datetime(value)
    if ~isempty(value.TimeZone)
        error('load_curve_dnn_fit:BadOption', 'timestamps must be naive local time');
    end
    value = value(:);
    parts = [double(year(value)), double(month(value)), double(day(value)), ...
        double(hour(value) * 60 + minute(value) + second(value) / 60)];
end

function label = vector_day(dayText)
    if isempty(dayText)
        label = 'day-01';
        return
    end
    label = parse_day(dayText);
end

function [minute, powerKw, date, dates, averaged, nRows, nDuplicates] = pack_samples(datesIn, minutes, powers)
    [datesIn, minutes, powers, nDuplicates] = drop_duplicates(datesIn, minutes(:), powers(:));
    if isempty(minutes)
        error('load_curve_dnn_fit:BadOption', 'No power samples remain after cleaning');
    end
    [minute, powerKw, date, dates, averaged] = curve_from_samples(datesIn, minutes, powers);
    % Count rows after duplicate removal and before a multi-day average.
    nRows = numel(powers);
end

function [datesOut, minutesOut, powersOut, nDuplicates] = drop_duplicates(datesIn, minutes, powers)
    count = numel(minutes);
    keys = zeros(count, 3);
    for index = 1:count
        keys(index, :) = [date_key(datesIn{index}), minutes(index), index];
    end
    [~, order] = sortrows(keys);
    keep = false(count, 1);
    nDuplicates = 0;
    last = 0;
    for position = 1:count
        index = order(position);
        if last > 0 && date_key(datesIn{index}) == date_key(datesIn{last}) ...
                && abs(minutes(index) - minutes(last)) <= 1e-9
            nDuplicates = nDuplicates + 1;
        else
            keep(index) = true;
            last = index;
        end
    end
    selected = find(keep);
    % Restore chronological order. find() follows the original index, so sort again.
    selectedKeys = keys(selected, :);
    [~, selectedOrder] = sortrows(selectedKeys);
    selected = selected(selectedOrder);
    datesOut = datesIn(selected);
    minutesOut = minutes(selected);
    powersOut = powers(selected);
end

function key = date_key(text)
    raw = as_char(text);
    if numel(raw) == 10 && raw(5) == '-' && raw(8) == '-' && all_digits(raw([1:4, 6:7, 9:10]))
        key = str2double(raw(1:4)) * 10000 + str2double(raw(6:7)) * 100 + str2double(raw(9:10));
        return
    end
    key = 0;
end

function [minute, powerKw, date, dates, averaged] = curve_from_samples(datesIn, minutes, powers)
    dates = {};
    buckets = {};
    for index = 1:numel(minutes)
        if isempty(dates) || ~strcmp(dates{end}, datesIn{index})
            dates{end + 1} = datesIn{index}; %#ok<AGROW>
            buckets{end + 1} = []; %#ok<AGROW>
        end
        buckets{end}(end + 1, :) = [minutes(index), powers(index)]; %#ok<AGROW>
    end
    for index = 1:numel(dates)
        bucket = buckets{index};
        if size(bucket, 1) < 2
            error('load_curve_dnn_fit:BadOption', ...
                'each day needs at least 2 samples (date %s)', dates{index});
        end
        for sample = 2:size(bucket, 1)
            if bucket(sample, 1) <= bucket(sample - 1, 1)
                error('load_curve_dnn_fit:BadOption', ...
                    'timestamps on %s must be strictly increasing', dates{index});
            end
        end
    end
    if numel(dates) == 1
        minute = buckets{1}(:, 1);
        powerKw = buckets{1}(:, 2);
        date = dates{1};
        averaged = false;
        return
    end
    grid = buckets{1}(:, 1);
    for index = 2:numel(dates)
        bucket = buckets{index};
        if size(bucket, 1) ~= numel(grid)
            error('load_curve_dnn_fit:BadOption', ...
                'each day must share the same minute-of-day grid to build a typical day');
        end
        for sample = 1:numel(grid)
            if abs(bucket(sample, 1) - grid(sample)) > 1e-6
                error('load_curve_dnn_fit:BadOption', ...
                    'each day must share the same minute-of-day grid to build a typical day (date %s)', ...
                    dates{index});
            end
        end
    end
    minute = grid;
    powerKw = zeros(numel(grid), 1);
    nDays = numel(dates);
    for sample = 1:numel(grid)
        acc = 0;
        for index = 1:nDays
            acc = acc + buckets{index}(sample, 2);
        end
        powerKw(sample) = acc / nDays;
    end
    date = 'typical';
    averaged = true;
end

function [w1, b1, w2, b2] = init_mlp(hidden, seed)
    state = mod(double(seed), 4294967296);
    limit = sqrt(6 / (1 + hidden));
    w1 = zeros(hidden, 1);
    w2 = zeros(hidden, 1);
    for unit = 1:hidden
        [state, draw] = lcg_random(state);
        w1(unit) = (2 * draw - 1) * limit;
    end
    b1 = zeros(hidden, 1);
    for unit = 1:hidden
        [state, draw] = lcg_random(state);
        w2(unit) = (2 * draw - 1) * limit;
    end
    b2 = 0;
end

function [state, value] = lcg_random(state)
    state = mod(1664525 * state + 1013904223, 4294967296);
    value = state / 4294967296;
end

function [w1, b1, w2, b2] = train_mlp(u, y, hidden, epochs, learningRate, beta1, beta2, epsilon, seed)
    [w1, b1, w2, b2] = init_mlp(hidden, seed);
    mw1 = zeros(hidden, 1);
    mb1 = zeros(hidden, 1);
    mw2 = zeros(hidden, 1);
    mb2 = 0;
    vw1 = zeros(hidden, 1);
    vb1 = zeros(hidden, 1);
    vw2 = zeros(hidden, 1);
    vb2 = 0;
    nSamples = numel(u);
    invTwoN = 2 / nSamples;
    oneMinusBeta1 = 1 - beta1;
    oneMinusBeta2 = 1 - beta2;
    beta1Pow = 1;
    beta2Pow = 1;
    for step = 1:epochs %#ok<NASGU>
        beta1Pow = beta1Pow * beta1;
        beta2Pow = beta2Pow * beta2;
        gw1 = zeros(hidden, 1);
        gb1 = zeros(hidden, 1);
        gw2 = zeros(hidden, 1);
        gb2 = 0;
        for index = 1:nSamples
            ui = u(index);
            yhat = b2;
            hiddenOut = zeros(hidden, 1);
            for unit = 1:hidden
                activated = tanh(w1(unit) * ui + b1(unit));
                hiddenOut(unit) = activated;
                yhat = yhat + w2(unit) * activated;
            end
            residual = invTwoN * (yhat - y(index));
            gb2 = gb2 + residual;
            for unit = 1:hidden
                activated = hiddenOut(unit);
                gw2(unit) = gw2(unit) + residual * activated;
                slope = residual * w2(unit) * (1 - activated * activated);
                gw1(unit) = gw1(unit) + slope * ui;
                gb1(unit) = gb1(unit) + slope;
            end
        end
        bias1 = 1 - beta1Pow;
        bias2 = 1 - beta2Pow;
        for unit = 1:hidden
            mw1(unit) = beta1 * mw1(unit) + oneMinusBeta1 * gw1(unit);
            mb1(unit) = beta1 * mb1(unit) + oneMinusBeta1 * gb1(unit);
            mw2(unit) = beta1 * mw2(unit) + oneMinusBeta1 * gw2(unit);
            vw1(unit) = beta2 * vw1(unit) + oneMinusBeta2 * gw1(unit) * gw1(unit);
            vb1(unit) = beta2 * vb1(unit) + oneMinusBeta2 * gb1(unit) * gb1(unit);
            vw2(unit) = beta2 * vw2(unit) + oneMinusBeta2 * gw2(unit) * gw2(unit);
            w1(unit) = w1(unit) - learningRate * (mw1(unit) / bias1) / (sqrt(vw1(unit) / bias2) + epsilon);
            b1(unit) = b1(unit) - learningRate * (mb1(unit) / bias1) / (sqrt(vb1(unit) / bias2) + epsilon);
            w2(unit) = w2(unit) - learningRate * (mw2(unit) / bias1) / (sqrt(vw2(unit) / bias2) + epsilon);
        end
        mb2 = beta1 * mb2 + oneMinusBeta1 * gb2;
        vb2 = beta2 * vb2 + oneMinusBeta2 * gb2 * gb2;
        b2 = b2 - learningRate * (mb2 / bias1) / (sqrt(vb2 / bias2) + epsilon);
    end
end

function predicted = predict_mlp(u, w1, b1, w2, b2)
    hidden = numel(w1);
    predicted = zeros(numel(u), 1);
    for index = 1:numel(u)
        ui = u(index);
        yhat = b2;
        for unit = 1:hidden
            yhat = yhat + w2(unit) * tanh(w1(unit) * ui + b1(unit));
        end
        predicted(index) = yhat;
    end
end

function coeff = fit_polynomial(u, y, degree)
    width = degree + 1;
    gram = zeros(width, width);
    moment = zeros(width, 1);
    for index = 1:numel(u)
        row = powers(u(index), degree);
        target = y(index);
        for rowIndex = 1:width
            moment(rowIndex) = moment(rowIndex) + row(rowIndex) * target;
            for colIndex = 1:width
                gram(rowIndex, colIndex) = gram(rowIndex, colIndex) + row(rowIndex) * row(colIndex);
            end
        end
    end
    coeff = solve_linear(gram, moment);
end

function predicted = eval_polynomial(u, coeff)
    predicted = zeros(numel(u), 1);
    for index = 1:numel(u)
        total = 0;
        power = 1;
        for weight = 1:numel(coeff)
            total = total + coeff(weight) * power;
            power = power * u(index);
        end
        predicted(index) = total;
    end
end

function row = powers(value, degree)
    row = zeros(degree + 1, 1);
    power = 1;
    for index = 1:(degree + 1)
        row(index) = power;
        power = power * value;
    end
end

function solution = solve_linear(matrix, rhs)
    width = numel(rhs);
    aug = [matrix, rhs(:)];
    scale = 0;
    for row = 1:width
        for col = 1:width
            magnitude = abs(matrix(row, col));
            if magnitude > scale
                scale = magnitude;
            end
        end
    end
    if scale == 0
        scale = 1;
    end
    tolerance = 1e-12 * scale;
    for col = 1:width
        pivot = col;
        best = abs(aug(col, col));
        for row = (col + 1):width
            magnitude = abs(aug(row, col));
            if magnitude > best
                best = magnitude;
                pivot = row;
            end
        end
        if pivot ~= col
            aug([col, pivot], :) = aug([pivot, col], :);
        end
        divisor = aug(col, col);
        if abs(divisor) <= tolerance
            error('load_curve_dnn_fit:BadOption', ...
                'polynomial design matrix is singular; try a lower degree');
        end
        aug(col, :) = aug(col, :) / divisor;
        for row = 1:width
            if row == col
                continue
            end
            factor = aug(row, col);
            aug(row, :) = aug(row, :) - factor * aug(col, :);
        end
    end
    solution = aug(:, width + 1);
end

function [y, scale, offset, peakKw, minKw] = normalize_power(power, method)
    peakKw = max_value(power);
    minKw = min_value(power);
    if strcmp(method, 'none')
        y = power(:);
        scale = 1;
        offset = 0;
        return
    end
    if strcmp(method, 'peak')
        if ~(peakKw > 0)
            error('load_curve_dnn_fit:BadOption', 'peak normalization needs a positive peak');
        end
        y = power(:) / peakKw;
        scale = peakKw;
        offset = 0;
        return
    end
    span = peakKw - minKw;
    if ~(span > 0)
        error('load_curve_dnn_fit:BadOption', 'min-max normalization needs the load to vary');
    end
    y = (power(:) - minKw) / span;
    scale = span;
    offset = minKw;
end

function [rmse, mae, maxAbs] = error_metrics(residual)
    totalSq = 0;
    totalAbs = 0;
    maxAbs = 0;
    count = numel(residual);
    for index = 1:count
        value = residual(index);
        magnitude = abs(value);
        totalSq = totalSq + value * value;
        totalAbs = totalAbs + magnitude;
        if magnitude > maxAbs
            maxAbs = magnitude;
        end
    end
    rmse = sqrt(totalSq / count);
    mae = totalAbs / count;
end

function value = mse_value(target, predicted)
    total = 0;
    count = numel(target);
    for index = 1:count
        gap = predicted(index) - target(index);
        total = total + gap * gap;
    end
    value = total / count;
end

function best = max_value(values)
    best = values(1);
    for index = 2:numel(values)
        if values(index) > best
            best = values(index);
        end
    end
end

function best = min_value(values)
    best = values(1);
    for index = 2:numel(values)
        if values(index) < best
            best = values(index);
        end
    end
end

function step = step_minutes(minute)
    if numel(minute) < 2
        step = NaN;
        return
    end
    first = minute(2) - minute(1);
    limit = 1e-6 * max(abs(first), 1);
    for index = 2:numel(minute)
        if abs((minute(index) - minute(index - 1)) - first) > limit
            step = NaN;
            return
        end
    end
    step = first;
end

function text = format_result(nSamples, degree, hidden, epochs, learningRate, seed, normalize, ...
        date, averaged, step, polyRmse, polyMae, polyMaxAbs, polyMse, ...
        dnnRmse, dnnMae, dnnMaxAbs, dnnMse, nRows, nMissing, nDuplicates, nDays, peakKw, minKw)
    if averaged
        averagedFlag = 1;
    else
        averagedFlag = 0;
    end
    header = sprintf(['n=%d  degree=%d  hidden=%d  epochs=%d  lr=%s  seed=%d  normalize=%s  ', ...
        'date=%s  averaged=%d  step_min=%s'], ...
        nSamples, degree, hidden, epochs, compact_num(learningRate), seed, normalize, ...
        date, averagedFlag, compact_num(step));
    poly = sprintf('poly_rmse=%s  poly_mae=%s  poly_max_abs=%s  poly_mse=%s', ...
        compact_num(polyRmse), compact_num(polyMae), compact_num(polyMaxAbs), compact_num(polyMse));
    dnn = sprintf('dnn_rmse=%s  dnn_mae=%s  dnn_max_abs=%s  dnn_mse=%s', ...
        compact_num(dnnRmse), compact_num(dnnMae), compact_num(dnnMaxAbs), compact_num(dnnMse));
    rows = sprintf('rows=%d  missing=%d  duplicates=%d  days=%d  peak_kw=%s  min_kw=%s', ...
        nRows, nMissing, nDuplicates, nDays, compact_num(peakKw), compact_num(minKw));
    text = strjoin({header, poly, dnn, rows}, sprintf('\n\n'));
end

function write_curve(csvPath, hour, minute, powerKw, polyKw, dnnKw, polyResidual, dnnResidual)
    folder = fileparts(csvPath);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('load_curve_dnn_fit:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, 'hour,minute,power_kw,poly_kw,dnn_kw,poly_residual_kw,dnn_residual_kw\n');
    for index = 1:numel(hour)
        fprintf(fid, '%s,%s,%s,%s,%s,%s,%s\n', ...
            csv_num(hour(index)), csv_num(minute(index)), csv_num(powerKw(index)), ...
            csv_num(polyKw(index)), csv_num(dnnKw(index)), ...
            csv_num(polyResidual(index)), csv_num(dnnResidual(index)));
    end
end

function fig = render_figure(hour, powerKw, polyKw, dnnKw, polyResidual, dnnResidual, ...
        degree, hidden, polyRmse, dnnRmse, outputPng, showFig)
    use_batch_graphics();
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    measured = [31, 78, 121] / 255;
    polyColor = [192, 57, 43] / 255;
    dnnColor = [14, 124, 102] / 255;
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 40 1040 820], ...
        'Name', 'load-curve-dnn-fit', 'NumberTitle', 'off');
    curveAxis = subplot(2, 1, 1, 'Parent', fig);
    residualAxis = subplot(2, 1, 2, 'Parent', fig);
    hold(curveAxis, 'on');
    hold(residualAxis, 'on');
    plot(curveAxis, hour, powerKw, 'Color', measured, 'LineWidth', 2.2);
    plot(curveAxis, hour, polyKw, '--', 'Color', polyColor, 'LineWidth', 1.8);
    plot(curveAxis, hour, dnnKw, 'Color', dnnColor, 'LineWidth', 2.0);
    plot(residualAxis, hour, polyResidual, '--', 'Color', polyColor, 'LineWidth', 1.6);
    plot(residualAxis, hour, dnnResidual, 'Color', dnnColor, 'LineWidth', 1.8);
    plot(residualAxis, [hour(1), hour(end)], [0, 0], 'Color', [0.533, 0.533, 0.533], ...
        'LineWidth', 0.8, 'HandleVisibility', 'off');
    hold(curveAxis, 'off');
    hold(residualAxis, 'off');
    style_axis(curveAxis, 'Measured load and fits', 'Power (kW)', hour);
    style_axis(residualAxis, 'Residual (fit - measured)', 'Residual (kW)', hour);
    xlabel(residualAxis, 'Hour of day');
    apply_legend(curveAxis, {'measured', sprintf('polynomial (degree %d)', degree), ...
        sprintf('DNN (1-%d-1 tanh)', hidden)});
    apply_legend(residualAxis, {'polynomial residual', 'DNN residual'});
    titleText = sprintf('Daily load fit    poly RMSE=%s kW    DNN RMSE=%s kW', ...
        compact_num(polyRmse), compact_num(dnnRmse));
    if exist('sgtitle', 'file') == 2 || exist('sgtitle', 'builtin') == 5
        sgtitle(titleText);
    else
        title(curveAxis, titleText);
    end
    if ~isempty(outputPng)
        folder = fileparts(outputPng);
        if ~isempty(folder) && exist(folder, 'dir') ~= 7
            mkdir(folder);
        end
        save_png(fig, outputPng);
    end
    if ~showFig
        close(fig);
        fig = [];
    end
end

function style_axis(ax, titleText, yLabel, hour)
    title(ax, titleText);
    ylabel(ax, yLabel);
    grid(ax, 'on');
    box(ax, 'on');
    set(ax, 'FontSize', 11);
    try
        set(ax, 'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.8);
    catch
    end
    if ~isempty(hour)
        if numel(hour) > 1 && hour(end) > hour(1)
            span = hour(end) - hour(1);
        else
            span = 1;
        end
        pad = 0.04 * span;
        if ~(span > 0)
            pad = 0.5;
        end
        xlim(ax, [hour(1) - pad, hour(end) + pad]);
    end
end

function apply_legend(ax, labels)
    try
        legend(ax, labels, 'Location', 'northwest', 'Box', 'on', 'Interpreter', 'none');
    catch
        legend(ax, labels, 'Location', 'northwest', 'Box', 'on');
    end
end

function save_png(fig, outputPng)
    if ~isempty(which('exportgraphics'))
        exportgraphics(fig, outputPng, 'Resolution', 150);
    else
        print(fig, outputPng, '-dpng', '-r150');
    end
end

function use_batch_graphics()
    if exist('available_graphics_toolkits', 'file') == 2 || exist('available_graphics_toolkits', 'builtin') == 5
        kits = available_graphics_toolkits();
        if any(strcmp(kits, 'gnuplot'))
            try
                graphics_toolkit('gnuplot');
            catch
            end
        end
    end
end

function [rows, nMissing] = read_power_csv(csvPath, timeCol, powerCol)
    if exist(csvPath, 'file') ~= 2
        error('load_curve_dnn_fit:FileNotFound', 'CSV not found: %s', csvPath);
    end
    raw = fileread(csvPath);
    if isempty(strtrim(raw))
        error('load_curve_dnn_fit:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    if numel(raw) >= 3 && raw(1) == char(239) && raw(2) == char(187) && raw(3) == char(191)
        raw = raw(4:end);
    end
    raw = strrep(raw, sprintf('\r\n'), sprintf('\n'));
    raw = strrep(raw, sprintf('\r'), sprintf('\n'));
    lines = strsplit(raw, sprintf('\n'));
    first = '';
    for index = 1:numel(lines)
        if ~isempty(strtrim(lines{index}))
            first = lines{index};
            break
        end
    end
    if isempty(first)
        error('load_curve_dnn_fit:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    if numel(strfind(first, ';')) > numel(strfind(first, ',')) %#ok<STREMP>
        delim = ';';
    else
        delim = ',';
    end
    table = {};
    for index = 1:numel(lines)
        if isempty(strtrim(lines{index}))
            continue
        end
        cells = split_line(lines{index}, delim);
        if all(cellfun(@(item) isempty(strtrim(item)), cells))
            continue
        end
        table{end + 1} = cells; %#ok<AGROW>
    end
    if isempty(table)
        error('load_curve_dnn_fit:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    headers = table{1};
    for index = 1:numel(headers)
        headers{index} = strtrim(headers{index});
    end
    timeName = resolve_column(headers, timeCol, time_aliases(), 'time');
    powerName = resolve_column(headers, powerCol, power_aliases(), 'power');
    if strcmp(timeName, powerName)
        error('load_curve_dnn_fit:BadOption', 'time and power columns must be different');
    end
    timeIndex = find(strcmp(headers, timeName), 1, 'first');
    powerIndex = find(strcmp(headers, powerName), 1, 'first');
    rows = zeros(0, 5);
    nMissing = 0;
    dataRows = 0;
    for index = 2:numel(table)
        cells = table{index};
        dataRows = dataRows + 1;
        if numel(cells) < timeIndex || isempty(strtrim(cells{timeIndex}))
            error('load_curve_dnn_fit:BadOption', 'a row is missing its timestamp');
        end
        if numel(cells) < powerIndex
            powerText = '';
        else
            powerText = strtrim(cells{powerIndex});
        end
        if isempty(powerText) || strcmpi(powerText, 'nan')
            nMissing = nMissing + 1;
            continue
        end
        [year, month, dayNumber, minuteOfDay, ok] = parse_timestamp(strtrim(cells{timeIndex}));
        if ~ok
            error('load_curve_dnn_fit:BadOption', 'could not parse timestamp ''%s''', strtrim(cells{timeIndex}));
        end
        value = str2double(powerText);
        if ~isscalar(value) || ~isfinite(value)
            error('load_curve_dnn_fit:BadOption', 'power must be finite');
        end
        rows(end + 1, :) = [year, month, dayNumber, minuteOfDay, value]; %#ok<AGROW>
    end
    if isempty(rows) && nMissing == 0
        if dataRows == 0
            error('load_curve_dnn_fit:EmptyCsv', 'CSV has no data rows: %s', csvPath);
        end
        error('load_curve_dnn_fit:BadOption', 'No power samples remain after cleaning');
    end
end

function name = resolve_column(headers, requested, aliases, kind)
    if ~isempty(requested)
        for index = 1:numel(headers)
            if strcmp(headers{index}, requested)
                name = headers{index};
                return
            end
        end
        reqNorm = normalize_key(requested);
        for index = 1:numel(headers)
            if ~isempty(headers{index}) && strcmp(normalize_key(headers{index}), reqNorm)
                name = headers{index};
                return
            end
        end
        error('load_curve_dnn_fit:BadOption', 'Column ''%s'' not found for %s. Available: %s', ...
            requested, kind, join_headers(headers));
    end
    for aliasIndex = 1:numel(aliases)
        aliasNorm = normalize_key(aliases{aliasIndex});
        for index = 1:numel(headers)
            if ~isempty(headers{index}) && strcmp(normalize_key(headers{index}), aliasNorm)
                name = headers{index};
                return
            end
        end
    end
    error('load_curve_dnn_fit:BadOption', ...
        'Could not find a %s column. Pass %s_col explicitly. Available: %s', ...
        kind, kind, join_headers(headers));
end

function text = join_headers(headers)
    kept = {};
    for index = 1:numel(headers)
        if ~isempty(headers{index})
            kept{end + 1} = headers{index}; %#ok<AGROW>
        end
    end
    if isempty(kept)
        text = '';
    else
        text = strjoin(kept, ', ');
    end
end

function aliases = time_aliases()
    aliases = {'timestamp', 'datetime', 'date_time', 'datestamp', 'time', 'date', 'ts', ...
        '时间戳', '时间', '时刻', '日期'};
end

function aliases = power_aliases()
    aliases = {'power_kw', 'p_kw', 'load_kw', 'load', 'power', 'p', 'kw', ...
        '负荷kw', '功率kw', '功率', '负荷', '有功功率', '有功'};
end

function cells = split_line(line, delim)
    cells = {};
    bucket = '';
    inQuote = false;
    index = 1;
    while index <= numel(line)
        ch = line(index);
        if inQuote
            if ch == '"'
                if index < numel(line) && line(index + 1) == '"'
                    bucket = [bucket, '"']; %#ok<AGROW>
                    index = index + 1;
                else
                    inQuote = false;
                end
            else
                bucket = [bucket, ch]; %#ok<AGROW>
            end
        elseif ch == '"'
            inQuote = true;
        elseif ch == delim
            cells{end + 1} = bucket; %#ok<AGROW>
            bucket = '';
        else
            bucket = [bucket, ch]; %#ok<AGROW>
        end
        index = index + 1;
    end
    cells{end + 1} = bucket; %#ok<AGROW>
end

function [year, month, dayNumber, minuteOfDay, ok] = parse_timestamp(text)
    raw = strtrim(as_char(text));
    year = 0;
    month = 0;
    dayNumber = 0;
    minuteOfDay = 0;
    ok = false;
    n = numel(raw);
    if n ~= 16 && n ~= 19
        return
    end
    if ~(raw(5) == '-' || raw(5) == '/') || raw(8) ~= raw(5) || (raw(11) ~= ' ' && raw(11) ~= 'T')
        return
    end
    if ~all_digits(raw(1:4)) || ~all_digits(raw(6:7)) || ~all_digits(raw(9:10))
        return
    end
    year = str2double(raw(1:4));
    month = str2double(raw(6:7));
    dayNumber = str2double(raw(9:10));
    if n == 16
        clock = raw(12:16);
        if numel(clock) ~= 5 || clock(3) ~= ':' || ~all_digits(clock(1:2)) || ~all_digits(clock(4:5))
            return
        end
        hourValue = str2double(clock(1:2));
        minuteValue = str2double(clock(4:5));
        secondValue = 0;
    else
        clock = raw(12:19);
        if numel(clock) ~= 8 || clock(3) ~= ':' || clock(6) ~= ':' || ~all_digits(clock([1, 2, 4, 5, 7, 8]))
            return
        end
        hourValue = str2double(clock(1:2));
        minuteValue = str2double(clock(4:5));
        secondValue = str2double(clock(7:8));
    end
    if hourValue > 23 || minuteValue > 59 || secondValue > 59 || ~valid_date(year, month, dayNumber)
        return
    end
    minuteOfDay = hourValue * 60 + minuteValue + secondValue / 60;
    ok = true;
end

function text = parse_day(text)
    raw = strtrim(as_char(text));
    if numel(raw) ~= 10 || raw(5) ~= '-' || raw(8) ~= '-' || ~all_digits(raw([1:4, 6:7, 9:10]))
        error('load_curve_dnn_fit:BadOption', 'day must be YYYY-MM-DD');
    end
    year = str2double(raw(1:4));
    month = str2double(raw(6:7));
    dayNumber = str2double(raw(9:10));
    if ~valid_date(year, month, dayNumber)
        error('load_curve_dnn_fit:BadOption', 'day must be a real calendar date');
    end
    text = sprintf('%04d-%02d-%02d', year, month, dayNumber);
end

function tf = all_digits(text)
    tf = ~isempty(text) && all(text >= '0' & text <= '9');
end

function tf = valid_date(year, month, dayNumber)
    if year < 1 || year > 9999 || month < 1 || month > 12 || dayNumber < 1
        tf = false;
        return
    end
    limits = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if month == 2 && is_leap(year)
        limit = 29;
    else
        limit = limits(month + 1);
    end
    tf = dayNumber <= limit;
end

function tf = is_leap(year)
    tf = mod(year, 4) == 0 && (mod(year, 100) ~= 0 || mod(year, 400) == 0);
end

function text = compact_num(value)
    if isempty(value) || ~isscalar(value) || ~isnumeric(value) || isnan(value)
        text = 'nan';
        return
    end
    if isinf(value)
        if value > 0
            text = 'inf';
        else
            text = '-inf';
        end
        return
    end
    text = sprintf('%.6g', value);
    if isempty(strfind(lower(text), 'e')) %#ok<STREMP>
        return
    end
    if abs(value) >= 1 && abs(value - round(value)) <= 1e-6 * max(abs(value), 1)
        text = sprintf('%.0f', value);
    end
end

function text = csv_num(value)
    if isempty(value) || ~isscalar(value) || ~isnumeric(value) || isnan(value)
        text = 'nan';
        return
    end
    if isinf(value)
        if value > 0
            text = 'inf';
        else
            text = '-inf';
        end
        return
    end
    text = sprintf('%.12g', value);
end

function key = normalize_key(value)
    text = lower(as_char(value));
    key = regexprep(text, '[\s_\-()（）]', '');
end

function text = as_char(value)
    if ischar(value)
        text = strtrim(value);
        return
    end
    if is_string_value(value)
        text = strtrim(char(value));
        return
    end
    if isnumeric(value)
        if isempty(value)
            text = '';
        else
            text = strtrim(num2str(value));
        end
        return
    end
    if iscell(value) && numel(value) == 1
        text = as_char(value{1});
        return
    end
    text = strtrim(char(value));
end

function tf = is_string_value(value)
    tf = false;
    if exist('isstring', 'builtin') == 5 || exist('isstring', 'file') == 2
        tf = isstring(value);
    end
end

function tf = is_datetime_value(value)
    tf = false;
    if exist('isdatetime', 'builtin') == 5 || exist('isdatetime', 'file') == 2
        tf = isdatetime(value);
    end
end

function number = finite_number(name, value)
    if ischar(value) || is_string_value(value)
        number = str2double(as_char(value));
    elseif isnumeric(value)
        number = double(value);
    else
        error('load_curve_dnn_fit:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('load_curve_dnn_fit:BadOption', '%s must be a finite number', name);
    end
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('load_curve_dnn_fit:BadOption', '%s must be a positive finite number', name);
    end
end

function number = unit_interval(name, value)
    number = finite_number(name, value);
    if ~(number >= 0) || ~(number < 1)
        error('load_curve_dnn_fit:BadOption', '%s must be in [0, 1)', name);
    end
end

function number = integral_number(name, value, minimum, message) %#ok<INUSL>
    if islogical(value) || ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || value ~= floor(value)
        error('load_curve_dnn_fit:BadOption', '%s', message);
    end
    number = double(value);
    if number < minimum
        error('load_curve_dnn_fit:BadOption', '%s', message);
    end
end

function name = normalize_name(value)
    name = lower(strtrim(as_char(value)));
    if ~(strcmp(name, 'peak') || strcmp(name, 'minmax') || strcmp(name, 'none'))
        error('load_curve_dnn_fit:BadOption', 'normalize must be peak, minmax, or none');
    end
end

function name = time_unit_name(value)
    name = lower(strtrim(as_char(value)));
    if ~(strcmp(name, 'auto') || strcmp(name, 'hour') || strcmp(name, 'minute') || strcmp(name, 'dayfrac'))
        error('load_curve_dnn_fit:BadOption', 'time_unit must be auto, hour, minute, or dayfrac');
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
    error('load_curve_dnn_fit:BadOption', '%s must be true or false', name);
end

function ok = is_text_scalar(value)
    if ischar(value)
        ok = isempty(value) || isrow(value);
        return
    end
    ok = is_string_value(value) && isscalar(value);
end

function tf = is_parameter_name(value)
    if isempty(value) || ~is_text_scalar(value)
        tf = false;
        return
    end
    keys = {'degree', 'hidden', 'epochs', 'learning_rate', 'beta1', 'beta2', 'epsilon', ...
        'seed', 'normalize', 'time_unit', 'time_col', 'power_col', 'day', 'csv_path', ...
        'output_csv', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(as_char(value)), keys));
end
