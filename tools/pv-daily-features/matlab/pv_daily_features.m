function result = pv_daily_features(source, varargin)
%PV_DAILY_FEATURES Daily PV peak, energy, daylight window, and ramps.
%   RESULT = PV_DAILY_FEATURES(CSVPATH, 'p_rated_kw', 100, 'ramp_minutes', 10)
%   RESULT = PV_DAILY_FEATURES(MINUTES, POWER, 'day', '2024-06-21')
%   RESULT = PV_DAILY_FEATURES(TIMESTAMPS, POWER)
%
%   Same features as python/pv_daily_features.py, in base MATLAB (no toolbox).
%   Timestamps are naive local time. A uniform series is kept as recorded.
%   An uneven series, or an explicit step_minutes, is linearly resampled.
%   The last grid step is shortened when that is required to keep the final
%   sample.
%
%       E_kWh = sum 0.5 * (P_i + P_{i+1}) * (t_{i+1} - t_i) / 60
%       CF = E_kWh / (P_rated * 24)          when a nameplate is given
%       ramp_i = (P_j - P_i) / (t_j - t_i)   t_j is the first sample at or
%                                            after t_i + ramp_minutes, kW/min
%       VI = sum |P_{i+1} - P_i| / (2 * P_peak)
%
%   A single rise and fall that starts and ends at the minimum has VI = 1.
%   P_peak is the first sample that attains the maximum. Duplicate timestamps
%   keep the first row. Blank CSV power cells are dropped.
%
%   Name-value keys match Python: time_col, power_col, p_rated_kw, p_on_kw,
%   ramp_minutes, step_minutes, day, csv_path, output_csv, output_png, show.
%   MATLAB name-value pairs are case-insensitive.

    if nargin < 1
        source = [];
    end
    [source, power, rest] = split_source(source, varargin);
    parser = inputParser;
    parser.FunctionName = 'pv_daily_features';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('time_col', '', @is_text_scalar);
    parser.addParameter('power_col', '', @is_text_scalar);
    parser.addParameter('p_rated_kw', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('p_on_kw', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('ramp_minutes', 10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('step_minutes', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('day', '', @is_text_scalar);
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    rampMinutes = positive_number('ramp_minutes', opt.ramp_minutes);
    if isempty(opt.step_minutes)
        stepMinutes = [];
    else
        stepMinutes = positive_number('step_minutes', opt.step_minutes);
    end
    if isempty(opt.p_rated_kw)
        pRated = [];
    else
        pRated = positive_number('p_rated_kw', opt.p_rated_kw);
    end
    if isempty(opt.p_on_kw)
        pOn = [];
    else
        pOn = nonnegative_number('p_on_kw', opt.p_on_kw);
    end
    showFig = as_bool('show', opt.show);
    [samples, nMissing, nDuplicates] = resolve_samples(opt, source, power);
    pvDays = build_all(samples, pRated, pOn, rampMinutes, stepMinutes);
    summary = format_result(pvDays, size(samples, 1), nMissing, nDuplicates, rampMinutes);

    outputCsv = as_char(opt.output_csv);
    outputPng = as_char(opt.output_png);
    if ~isempty(outputCsv)
        write_summary(outputCsv, pvDays);
    end
    if ~isempty(outputPng) || showFig
        fig = render_figure(pvDays, nan_if_empty(pRated), outputPng, showFig);
    else
        fig = [];
    end

    result = struct();
    result.days = pvDays;
    result.summary = summary;
    result.n_rows = size(samples, 1);
    result.n_missing = nMissing;
    result.n_duplicates = nDuplicates;
    result.ramp_minutes = rampMinutes;
    result.p_rated_kw = nan_if_empty(pRated);
    result.p_on_kw = nan_if_empty(pOn);
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
    if isnumeric(source) && isscalar(source) && (isempty(args) || ~is_numeric_vector(args{1}))
        error('pv_daily_features:BadOption', ...
            'pass a CSV path, timestamps, or minutes; the first argument is not a scalar');
    end
    if is_time_vector(source, args)
        if isempty(args) || ~is_numeric_vector(args{1})
            error('pv_daily_features:BadOption', 'pass power together with time');
        end
        power = args{1};
        if isempty(args)
            rest = {};
        else
            rest = args(2:end);
        end
    elseif ~isempty(source) && ~is_text_scalar(source)
        error('pv_daily_features:BadOption', ...
            'source must be a CSV path, timestamps, or minutes from midnight');
    end
end

function tf = is_time_vector(value, args)
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
    if is_text_scalar(value) && ~isempty(as_char(value)) && ~isempty(args) && is_numeric_vector(args{1})
        tf = true;
        return
    end
    tf = false;
end

function tf = is_numeric_vector(value)
    tf = isnumeric(value) && ~isempty(value) && isvector(value);
end

function [samples, nMissing, nDuplicates] = resolve_samples(opt, source, power)
    csvPath = as_char(opt.csv_path);
    if ~isempty(power)
        if ~isempty(csvPath)
            error('pv_daily_features:BadOption', 'pass time and power, or a CSV path, not both');
        end
        if ~isempty(as_char(opt.time_col)) || ~isempty(as_char(opt.power_col))
            error('pv_daily_features:BadOption', ...
                'time_col and power_col apply to a CSV, not to time and power vectors');
        end
        [samples, nDuplicates] = samples_from_vectors(source, power, as_char(opt.day));
        nMissing = 0;
        return
    end
    if ~isempty(as_char(opt.day))
        error('pv_daily_features:BadOption', 'day applies to numeric minutes, not a CSV');
    end
    if is_text_scalar(source) && ~isempty(as_char(source))
        if ~isempty(csvPath)
            error('pv_daily_features:BadOption', ...
                'pass a CSV path once, either positionally or as csv_path=');
        end
        csvPath = as_char(source);
    elseif ~isempty(source)
        error('pv_daily_features:BadOption', ...
            'source must be a CSV path, timestamps, or minutes from midnight');
    end
    if isempty(csvPath)
        error('pv_daily_features:BadOption', 'pass a CSV path, or time and power');
    end
    [rows, nMissing] = read_power_csv(csvPath, as_char(opt.time_col), as_char(opt.power_col));
    [samples, nDuplicates] = clean_samples(rows);
    if isempty(samples)
        error('pv_daily_features:BadOption', 'No power samples remain after cleaning');
    end
end

function [samples, nDuplicates] = samples_from_vectors(time, power, dayText)
    if ~is_numeric_vector(power)
        if isempty(power)
            error('pv_daily_features:BadOption', 'power must not be empty');
        end
        error('pv_daily_features:BadOption', 'power must be a numeric vector');
    end
    values = double(power(:));
    if any(~isfinite(values))
        error('pv_daily_features:BadOption', 'power must be finite');
    end
    parts = time_parts(time, dayText);
    if size(parts, 1) ~= numel(values)
        error('pv_daily_features:BadOption', 'time and power must have the same length');
    end
    [samples, nDuplicates] = clean_samples([parts, values]);
    if isempty(samples)
        error('pv_daily_features:BadOption', 'time must not be empty');
    end
end

function parts = time_parts(time, dayText)
    if is_numeric_vector(time)
        minutes = double(time(:));
        if any(~isfinite(minutes) | minutes < 0)
            error('pv_daily_features:BadOption', ...
                'time in minutes must be zero or a positive finite number');
        end
        if isempty(dayText)
            dayText = '1970-01-01';
        end
        [y0, m0, d0] = parse_day(dayText);
        parts = zeros(numel(minutes), 4);
        for index = 1:numel(minutes)
            offset = floor(minutes(index) / 1440 + 1e-12);
            minuteOfDay = minutes(index) - offset * 1440;
            if minuteOfDay >= 1440 - 1e-9
                offset = offset + 1;
                minuteOfDay = minuteOfDay - 1440;
            end
            [year, month, dayNumber] = add_days(y0, m0, d0, offset);
            parts(index, :) = [year, month, dayNumber, minuteOfDay];
        end
        return
    end
    if ~isempty(dayText)
        error('pv_daily_features:BadOption', ...
            'day applies to numeric minutes, not to timestamps');
    end
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
        error('pv_daily_features:BadOption', 'time must be a vector of timestamps or minutes');
    end
    parts = zeros(numel(texts), 4);
    for index = 1:numel(texts)
        [year, month, dayNumber, minuteOfDay, ok] = parse_timestamp(texts{index});
        if ~ok
            error('pv_daily_features:BadOption', 'could not parse timestamp ''%s''', as_char(texts{index}));
        end
        parts(index, :) = [year, month, dayNumber, minuteOfDay];
    end
end

function parts = parts_from_datetime(value)
    if ~isempty(value.TimeZone)
        error('pv_daily_features:BadOption', 'timestamps must be naive local time');
    end
    value = value(:);
    years = year(value);
    months = month(value);
    days = day(value);
    minutes = hour(value) * 60 + minute(value) + second(value) / 60;
    parts = [double(years), double(months), double(days), double(minutes)];
    for index = 1:size(parts, 1)
        if ~valid_date(parts(index, 1), parts(index, 2), parts(index, 3))
            error('pv_daily_features:BadOption', 'could not parse timestamp');
        end
    end
end

function [rows, nMissing] = read_power_csv(csvPath, timeCol, powerCol)
    if exist(csvPath, 'file') ~= 2
        error('pv_daily_features:FileNotFound', 'CSV not found: %s', csvPath);
    end
    raw = fileread(csvPath);
    if isempty(strtrim(raw))
        error('pv_daily_features:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    if numel(raw) >= 3 && raw(1) == char(239) && raw(2) == char(187) && raw(3) == char(191)
        raw = raw(4:end);
    end
    raw = strrep(raw, sprintf('\r\n'), sprintf('\n'));
    raw = strrep(raw, sprintf('\r'), sprintf('\n'));
    lines = strsplit(raw, sprintf('\n'));
    kept = {};
    for index = 1:numel(lines)
        if ~isempty(strtrim(lines{index}))
            kept{end + 1} = lines{index}; %#ok<AGROW>
        end
    end
    if isempty(kept)
        error('pv_daily_features:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    commaCount = numel(strfind(kept{1}, ','));
    semiCount = numel(strfind(kept{1}, ';'));
    if semiCount > commaCount
        delim = ';';
    else
        delim = ',';
    end
    headers = split_line(kept{1}, delim);
    for index = 1:numel(headers)
        headers{index} = strtrim(headers{index});
    end
    timeName = resolve_column(headers, timeCol, time_aliases(), 'time');
    powerName = resolve_column(headers, powerCol, power_aliases(), 'power');
    if strcmp(timeName, powerName)
        error('pv_daily_features:BadOption', 'time and power columns must be different');
    end
    timeIndex = find(strcmp(headers, timeName), 1, 'first');
    powerIndex = find(strcmp(headers, powerName), 1, 'first');
    rows = zeros(0, 5);
    nMissing = 0;
    dataRows = 0;
    for index = 2:numel(kept)
        cells = split_line(kept{index}, delim);
        while numel(cells) < numel(headers)
            cells{end + 1} = ''; %#ok<AGROW>
        end
        if all(cellfun(@(item) isempty(strtrim(item)), cells))
            continue
        end
        dataRows = dataRows + 1;
        timeText = strtrim(cells{timeIndex});
        powerText = strtrim(cells{powerIndex});
        if isempty(timeText)
            error('pv_daily_features:BadOption', 'a row is missing its timestamp');
        end
        if isempty(powerText) || strcmpi(powerText, 'nan')
            nMissing = nMissing + 1;
            continue
        end
        [year, month, dayNumber, minuteOfDay, ok] = parse_timestamp(timeText);
        if ~ok
            error('pv_daily_features:BadOption', 'could not parse timestamp ''%s''', timeText);
        end
        value = str2double(powerText);
        if ~isscalar(value) || ~isfinite(value)
            error('pv_daily_features:BadOption', 'power must be finite');
        end
        rows(end + 1, :) = [year, month, dayNumber, minuteOfDay, value]; %#ok<AGROW>
    end
    if isempty(rows) && nMissing == 0
        if dataRows == 0
            error('pv_daily_features:EmptyCsv', 'CSV has no data rows: %s', csvPath);
        end
        error('pv_daily_features:BadOption', 'No power samples remain after cleaning');
    end
end

function [kept, nDuplicates] = clean_samples(rows)
    if isempty(rows)
        kept = zeros(0, 5);
        nDuplicates = 0;
        return
    end
    order = (1:size(rows, 1)).';
    [~, idx] = sortrows([rows(:, 1:4), order]);
    rows = rows(idx, :);
    keep = false(size(rows, 1), 1);
    keep(1) = true;
    last = 1;
    nDuplicates = 0;
    for index = 2:size(rows, 1)
        sameDay = rows(index, 1) == rows(last, 1) && rows(index, 2) == rows(last, 2) ...
            && rows(index, 3) == rows(last, 3);
        if sameDay && abs(rows(index, 4) - rows(last, 4)) <= 1e-9
            nDuplicates = nDuplicates + 1;
        else
            keep(index) = true;
            last = index;
        end
    end
    kept = rows(keep, :);
end

function pvDays = build_all(samples, pRated, pOn, rampMinutes, stepMinutes)
    if isempty(samples)
        error('pv_daily_features:BadOption', 'No power samples remain after cleaning');
    end
    breaks = 1;
    for index = 2:size(samples, 1)
        if any(samples(index, 1:3) ~= samples(index - 1, 1:3))
            breaks(end + 1) = index; %#ok<AGROW>
        end
    end
    breaks(end + 1) = size(samples, 1) + 1; %#ok<AGROW>
    built = cell(1, numel(breaks) - 1);
    for group = 1:(numel(breaks) - 1)
        block = samples(breaks(group):(breaks(group + 1) - 1), :);
        date = sprintf('%04d-%02d-%02d', block(1, 1), block(1, 2), block(1, 3));
        built{group} = build_day(date, block(:, 4), block(:, 5), pRated, pOn, rampMinutes, stepMinutes);
    end
    pvDays = [built{:}];
end

function pvDay = build_day(date, minute, values, pRated, pOnGiven, rampMinutes, stepMinutes)
    [grid, series, step, resampled] = prepare_series(minute, values, stepMinutes);
    n = numel(series);
    [pPeak, peakIndex] = max(series);
    tPeak = grid(peakIndex);
    energy = trapezoid_kwh(grid, series);
    if n < 2 || grid(end) == grid(1)
        hoursSpan = 0;
        pMean = series(1);
    else
        hoursSpan = (grid(end) - grid(1)) / 60;
        pMean = energy / hoursSpan;
    end
    if isempty(pRated)
        rated = NaN;
        capacity = NaN;
    else
        rated = pRated;
        capacity = energy / (pRated * 24);
    end
    if isempty(pOnGiven)
        if ~isempty(pRated)
            pOn = 0.02 * pRated;
        elseif pPeak > 0
            pOn = 0.05 * pPeak;
        else
            pOn = 0;
        end
    else
        pOn = pOnGiven;
    end
    on = series >= pOn;
    onIndex = find(on);
    if isempty(onIndex)
        tOn = NaN;
        tOff = NaN;
        hoursWindow = NaN;
    else
        tOn = grid(onIndex(1));
        tOff = grid(onIndex(end));
        hoursWindow = (tOff - tOn) / 60;
    end
    hoursAbove = hours_above(grid, on);
    [windowRamp, windowSpan] = window_ramps(grid, series, rampMinutes);
    [rampUp, upSpan, tUp, upClock] = pick_extreme(windowRamp, windowSpan, grid, 'up');
    [rampDown, downSpan, tDown, downClock] = pick_extreme(windowRamp, windowSpan, grid, 'down');
    [stepUp, stepDown, tStepUp, tStepDown, stepUpClock, stepDownClock] = step_ramps(grid, series);
    if n >= 2 && pPeak > 0
        variability = sum(abs(diff(series))) / (2 * pPeak);
    else
        variability = NaN;
    end

    pvDay = struct();
    pvDay.date = date;
    pvDay.n_samples = n;
    pvDay.step_minutes = step;
    pvDay.resampled = logical(resampled);
    pvDay.p_rated_kw = rated;
    pvDay.p_on_kw = pOn;
    pvDay.p_peak_kw = pPeak;
    pvDay.t_peak = clock_text(tPeak);
    pvDay.t_peak_min = tPeak;
    pvDay.energy_kwh = energy;
    pvDay.hours_span = hoursSpan;
    pvDay.p_mean_kw = pMean;
    pvDay.capacity_factor = capacity;
    pvDay.t_on = clock_text(tOn);
    pvDay.t_off = clock_text(tOff);
    pvDay.t_on_min = tOn;
    pvDay.t_off_min = tOff;
    pvDay.hours_window = hoursWindow;
    pvDay.hours_above = hoursAbove;
    pvDay.ramp_minutes = rampMinutes;
    pvDay.ramp_up_kw_per_min = rampUp;
    pvDay.ramp_down_kw_per_min = rampDown;
    pvDay.ramp_up_span_min = upSpan;
    pvDay.ramp_down_span_min = downSpan;
    pvDay.t_ramp_up = upClock;
    pvDay.t_ramp_down = downClock;
    pvDay.t_ramp_up_min = tUp;
    pvDay.t_ramp_down_min = tDown;
    pvDay.ramp_step_up_kw_per_min = stepUp;
    pvDay.ramp_step_down_kw_per_min = stepDown;
    pvDay.t_step_up = stepUpClock;
    pvDay.t_step_down = stepDownClock;
    pvDay.t_step_up_min = tStepUp;
    pvDay.t_step_down_min = tStepDown;
    pvDay.variability_index = variability;
    pvDay.minute = grid(:);
    pvDay.hour = grid(:) / 60;
    pvDay.power_kw = series(:);
    pvDay.ramp_kw_per_min = windowRamp(:);
end

function [grid, values, step, resampled] = prepare_series(minute, values, stepMinutes)
    minute = double(minute(:));
    values = double(values(:));
    n = numel(minute);
    if n == 0
        error('pv_daily_features:BadOption', 'A day has no samples');
    end
    if n == 1
        grid = minute;
        step = NaN;
        resampled = false;
        return
    end
    dt = diff(minute);
    if any(dt <= 0)
        error('pv_daily_features:BadOption', 'timestamps in a day must be strictly increasing');
    end
    med = median_value(dt);
    uniform = max(abs(dt - med)) <= 1e-6 * max(med, 1);
    if isempty(stepMinutes)
        if uniform
            grid = minute;
            step = med;
            resampled = false;
            return
        end
        step = med;
    else
        step = stepMinutes;
        if uniform && abs(step - med) <= 1e-6 * max(step, 1)
            grid = minute;
            step = med;
            resampled = false;
            return
        end
    end
    span = minute(end) - minute(1);
    if step > span
        error('pv_daily_features:BadOption', 'step_minutes is longer than the series');
    end
    nGrid = floor(span / step + 1e-9) + 1;
    grid = minute(1) + step * (0:(nGrid - 1)).';
    if minute(end) - grid(end) > 1e-6
        grid = [grid; minute(end)];
    end
    values = interp1(minute, values, grid, 'linear');
    resampled = true;
end

function energy = trapezoid_kwh(minute, values)
    if numel(minute) < 2
        energy = 0;
        return
    end
    dtHours = diff(minute) / 60;
    energy = sum(0.5 * (values(1:end - 1) + values(2:end)) .* dtHours);
end

function hours = hours_above(minute, on)
    if numel(minute) < 2
        hours = 0;
        return
    end
    dtHours = diff(minute) / 60;
    indicator = double(on(:));
    hours = sum(0.5 * (indicator(1:end - 1) + indicator(2:end)) .* dtHours);
end

function [ramp, span] = window_ramps(minute, values, rampMinutes)
    n = numel(minute);
    ramp = nan(n, 1);
    span = nan(n, 1);
    if n < 2
        return
    end
    for index = 1:(n - 1)
        target = minute(index) + rampMinutes;
        endIndex = find(minute >= target - 1e-9, 1, 'first');
        if isempty(endIndex)
            break
        end
        if endIndex <= index
            endIndex = index + 1;
        end
        if endIndex > n
            break
        end
        dur = minute(endIndex) - minute(index);
        if dur <= 0
            continue
        end
        ramp(index) = (values(endIndex) - values(index)) / dur;
        span(index) = dur;
    end
end

function [value, spanValue, minuteValue, clock] = pick_extreme(ramp, span, minute, which)
    finiteMask = isfinite(ramp);
    if ~any(finiteMask)
        value = NaN;
        spanValue = NaN;
        minuteValue = NaN;
        clock = 'nan';
        return
    end
    filled = ramp;
    if strcmp(which, 'up')
        filled(~finiteMask) = -inf;
        [~, index] = max(filled);
    else
        filled(~finiteMask) = inf;
        [~, index] = min(filled);
    end
    value = ramp(index);
    spanValue = span(index);
    minuteValue = minute(index);
    clock = clock_text(minuteValue);
end

function [stepUp, stepDown, tUp, tDown, upClock, downClock] = step_ramps(minute, values)
    if numel(minute) < 2
        stepUp = NaN;
        stepDown = NaN;
        tUp = NaN;
        tDown = NaN;
        upClock = 'nan';
        downClock = 'nan';
        return
    end
    step = diff(values) ./ diff(minute);
    [stepUp, upIndex] = max(step);
    [stepDown, downIndex] = min(step);
    tUp = minute(upIndex);
    tDown = minute(downIndex);
    upClock = clock_text(tUp);
    downClock = clock_text(tDown);
end

function text = format_result(pvDays, nRows, nMissing, nDuplicates, rampMinutes)
    parts = cell(1, numel(pvDays) + 1);
    parts{1} = sprintf('rows=%d  missing=%d  duplicates=%d  days=%d  ramp_min=%s', ...
        nRows, nMissing, nDuplicates, numel(pvDays), compact_num(rampMinutes));
    for index = 1:numel(pvDays)
        parts{index + 1} = format_day(pvDays(index));
    end
    text = strjoin(parts, sprintf('\n\n'));
end

function text = format_day(pvDay)
    if isfinite(pvDay.t_on_min)
        onText = sprintf('on=%s-%s', pvDay.t_on, pvDay.t_off);
    else
        onText = 'on=undefined';
    end
    lines = { ...
        sprintf('date=%s  N=%d  step=%s  resampled=%d', pvDay.date, pvDay.n_samples, ...
            compact_num(pvDay.step_minutes), double(pvDay.resampled)), ...
        sprintf('Ppeak=%s  t_peak=%s  E=%s  mean=%s  span=%s  CF=%s  Prated=%s  Pon=%s', ...
            compact_num(pvDay.p_peak_kw), pvDay.t_peak, compact_num(pvDay.energy_kwh), ...
            compact_num(pvDay.p_mean_kw), compact_num(pvDay.hours_span), ...
            compact_num(pvDay.capacity_factor), compact_num(pvDay.p_rated_kw), compact_num(pvDay.p_on_kw)), ...
        sprintf('%s  window=%s  above=%s', onText, compact_num(pvDay.hours_window), ...
            compact_num(pvDay.hours_above)), ...
        sprintf('ramp_min=%s  up=%s  down=%s  up_span=%s  down_span=%s  t_up=%s  t_down=%s', ...
            compact_num(pvDay.ramp_minutes), compact_num(pvDay.ramp_up_kw_per_min), ...
            compact_num(pvDay.ramp_down_kw_per_min), compact_num(pvDay.ramp_up_span_min), ...
            compact_num(pvDay.ramp_down_span_min), pvDay.t_ramp_up, pvDay.t_ramp_down), ...
        sprintf('step_up=%s  t_step_up=%s  step_down=%s  t_step_down=%s  VI=%s', ...
            compact_num(pvDay.ramp_step_up_kw_per_min), pvDay.t_step_up, ...
            compact_num(pvDay.ramp_step_down_kw_per_min), pvDay.t_step_down, ...
            compact_num(pvDay.variability_index))};
    text = strjoin(lines, sprintf('\n'));
end

function write_summary(csvPath, pvDays)
    folder = fileparts(csvPath);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('pv_daily_features:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, ['date,n_samples,step_minutes,resampled,p_rated_kw,p_on_kw,p_peak_kw,t_peak,', ...
        't_peak_min,energy_kwh,hours_span,p_mean_kw,capacity_factor,t_on,t_off,t_on_min,t_off_min,', ...
        'hours_window,hours_above,ramp_minutes,ramp_up_kw_per_min,ramp_down_kw_per_min,', ...
        'ramp_up_span_min,ramp_down_span_min,t_ramp_up,t_ramp_down,t_ramp_up_min,t_ramp_down_min,', ...
        'ramp_step_up_kw_per_min,ramp_step_down_kw_per_min,t_step_up,t_step_down,t_step_up_min,', ...
        't_step_down_min,variability_index\n']);
    for index = 1:numel(pvDays)
        item = pvDays(index);
        fprintf(fid, ['%s,%d,%s,%d,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,', ...
            '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n'], ...
            item.date, item.n_samples, csv_num(item.step_minutes), double(item.resampled), ...
            csv_num(item.p_rated_kw), csv_num(item.p_on_kw), csv_num(item.p_peak_kw), item.t_peak, ...
            csv_num(item.t_peak_min), csv_num(item.energy_kwh), csv_num(item.hours_span), ...
            csv_num(item.p_mean_kw), csv_num(item.capacity_factor), item.t_on, item.t_off, ...
            csv_num(item.t_on_min), csv_num(item.t_off_min), csv_num(item.hours_window), ...
            csv_num(item.hours_above), csv_num(item.ramp_minutes), csv_num(item.ramp_up_kw_per_min), ...
            csv_num(item.ramp_down_kw_per_min), csv_num(item.ramp_up_span_min), ...
            csv_num(item.ramp_down_span_min), item.t_ramp_up, item.t_ramp_down, ...
            csv_num(item.t_ramp_up_min), csv_num(item.t_ramp_down_min), ...
            csv_num(item.ramp_step_up_kw_per_min), csv_num(item.ramp_step_down_kw_per_min), ...
            item.t_step_up, item.t_step_down, csv_num(item.t_step_up_min), ...
            csv_num(item.t_step_down_min), csv_num(item.variability_index));
    end
end

function fig = render_figure(pvDays, pRatedKw, outputPng, showFig)
    use_batch_graphics();
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    palette = [ ...
        31, 78, 121; ...
        192, 57, 43; ...
        14, 124, 102; ...
        230, 126, 34; ...
        108, 52, 131; ...
        26, 82, 118; ...
        146, 43, 33; ...
        27, 79, 114] / 255;
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 40 1040 840], ...
        'Name', 'pv-daily-features', 'NumberTitle', 'off');
    powerAxis = subplot(2, 1, 1, 'Parent', fig);
    rampAxis = subplot(2, 1, 2, 'Parent', fig);
    hold(powerAxis, 'on');
    hold(rampAxis, 'on');
    hours = [];
    powers = [];
    ramps = [];
    labels = cell(1, numel(pvDays));
    for index = 1:numel(pvDays)
        item = pvDays(index);
        color = palette(mod(index - 1, size(palette, 1)) + 1, :);
        labels{index} = item.date;
        plot(powerAxis, item.hour, item.power_kw, 'Color', color, 'LineWidth', 1.7);
        plot(rampAxis, item.hour, item.ramp_kw_per_min, 'Color', color, 'LineWidth', 1.5);
        plot(powerAxis, item.t_peak_min / 60, item.p_peak_kw, 'o', 'Color', color, ...
            'MarkerFaceColor', color, 'MarkerSize', 6, 'HandleVisibility', 'off');
        if isfinite(item.t_ramp_up_min)
            plot(rampAxis, item.t_ramp_up_min / 60, item.ramp_up_kw_per_min, '^', ...
                'Color', color, 'MarkerFaceColor', color, 'MarkerSize', 7, 'HandleVisibility', 'off');
        end
        if isfinite(item.t_ramp_down_min)
            plot(rampAxis, item.t_ramp_down_min / 60, item.ramp_down_kw_per_min, 'v', ...
                'Color', color, 'MarkerFaceColor', color, 'MarkerSize', 7, 'HandleVisibility', 'off');
        end
        hours = [hours; item.hour(:)]; %#ok<AGROW>
        powers = [powers; item.power_kw(isfinite(item.power_kw))]; %#ok<AGROW>
        finiteRamp = item.ramp_kw_per_min(isfinite(item.ramp_kw_per_min));
        ramps = [ramps; finiteRamp(:)]; %#ok<AGROW>
        if isfinite(item.ramp_up_kw_per_min)
            ramps(end + 1, 1) = item.ramp_up_kw_per_min; %#ok<AGROW>
        end
        if isfinite(item.ramp_down_kw_per_min)
            ramps(end + 1, 1) = item.ramp_down_kw_per_min; %#ok<AGROW>
        end
    end
    hold(powerAxis, 'off');
    hold(rampAxis, 'off');
    powerLabels = labels;
    if isfinite(pRatedKw)
        powers(end + 1, 1) = pRatedKw; %#ok<AGROW>
        powerLabels{end + 1} = 'rated'; %#ok<AGROW>
    end
    style_power_axis(powerAxis, hours, powers);
    style_ramp_axis(rampAxis, hours, ramps);
    if isfinite(pRatedKw)
        hold(powerAxis, 'on');
        xLimits = xlim(powerAxis);
        plot(powerAxis, xLimits, [pRatedKw, pRatedKw], '--', 'Color', [136, 136, 136] / 255, 'LineWidth', 1);
        hold(powerAxis, 'off');
        xlim(powerAxis, xLimits);
    end
    apply_legend(powerAxis, powerLabels);
    apply_legend(rampAxis, labels);
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

function style_power_axis(ax, hours, powers)
    title(ax, 'PV power');
    ylabel(ax, 'Power (kW)');
    style_axes(ax);
    pad_time_axis(ax, hours);
    if isempty(powers)
        return
    end
    ymin = min(0, min(powers));
    ymax = max(powers);
    if ymax > ymin
        span = ymax - ymin;
    else
        span = max(abs(ymax), 1);
    end
    pad = 0.08 * span;
    if ymin >= -1e-9
        ypadBottom = 0;
    else
        ypadBottom = pad;
    end
    ylim(ax, [ymin - ypadBottom, ymax + pad]);
end

function style_ramp_axis(ax, hours, ramps)
    title(ax, 'Ramp over the window');
    xlabel(ax, 'Hour of day');
    ylabel(ax, 'Ramp (kW/min)');
    style_axes(ax);
    pad_time_axis(ax, hours);
    xLimits = xlim(ax);
    hold(ax, 'on');
    plot(ax, xLimits, [0, 0], 'Color', [136, 136, 136] / 255, 'LineWidth', 0.8, ...
        'HandleVisibility', 'off');
    hold(ax, 'off');
    xlim(ax, xLimits);
    if isempty(ramps)
        return
    end
    span = max([abs(min(ramps)), abs(max(ramps)), 1e-6]);
    pad = 0.12 * span;
    ylim(ax, [min(ramps) - pad, max(ramps) + pad]);
end

function pad_time_axis(ax, hours)
    if isempty(hours)
        return
    end
    xmin = min(hours);
    xmax = max(hours);
    if xmax > xmin
        span = xmax - xmin;
    else
        span = 1;
    end
    pad = 0.04 * span;
    xlim(ax, [xmin - pad, xmax + pad]);
end

function apply_legend(ax, labels)
    try
        legend(ax, labels, 'Location', 'northeast', 'Box', 'on', 'Interpreter', 'none');
    catch
        legend(ax, labels, 'Location', 'northeast', 'Box', 'on');
    end
end

function style_axes(ax)
    grid(ax, 'on');
    box(ax, 'on');
    set(ax, 'FontSize', 11);
    try
        set(ax, 'GridColor', [0.82 0.82 0.82], 'GridAlpha', 0.8);
    catch
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
        error('pv_daily_features:BadOption', 'Column ''%s'' not found for %s. Available: %s', ...
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
    error('pv_daily_features:BadOption', ...
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
    % UTF-8 literals: MATLAB reads them as characters, Octave as the same
    % bytes fileread returns from a UTF-8 CSV.
    aliases = {'timestamp', 'datetime', 'date_time', 'datestamp', 'time', 'date', 'ts', ...
        '时间戳', '时间', '时刻', '日期'};
end

function aliases = power_aliases()
    aliases = {'power_kw', 'p_kw', 'pv_kw', 'pv_power', 'ac_power', 'power', 'p', 'kw', ...
        '出力kw', '功率kw', '功率', '出力', '有功功率', '有功'};
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

function [year, month, dayNumber] = parse_day(text)
    raw = strtrim(as_char(text));
    if numel(raw) ~= 10 || raw(5) ~= '-' || raw(8) ~= '-' || ~all_digits(raw([1:4, 6:7, 9:10]))
        error('pv_daily_features:BadOption', 'day must be YYYY-MM-DD');
    end
    year = str2double(raw(1:4));
    month = str2double(raw(6:7));
    dayNumber = str2double(raw(9:10));
    if ~valid_date(year, month, dayNumber)
        error('pv_daily_features:BadOption', 'day must be a real calendar date');
    end
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

function [year, month, dayNumber] = add_days(year, month, dayNumber, offset)
    [year, month, dayNumber] = civil_from_days(days_from_civil(year, month, dayNumber) + offset);
end

function n = days_from_civil(year, month, dayNumber)
    if month <= 2
        year2 = year - 1;
    else
        year2 = year;
    end
    if year2 >= 0
        era = floor(year2 / 400);
    else
        era = floor((year2 - 399) / 400);
    end
    yoe = year2 - era * 400;
    if month > 2
        monthPart = month - 3;
    else
        monthPart = month + 9;
    end
    doy = floor((153 * monthPart + 2) / 5) + dayNumber - 1;
    doe = yoe * 365 + floor(yoe / 4) - floor(yoe / 100) + doy;
    n = era * 146097 + doe - 719468;
end

function [year, month, dayNumber] = civil_from_days(z)
    z = z + 719468;
    if z >= 0
        era = floor(z / 146097);
    else
        era = floor((z - 146096) / 146097);
    end
    doe = z - era * 146097;
    yoe = floor((doe - floor(doe / 1460) + floor(doe / 36524) - floor(doe / 146096)) / 365);
    year = yoe + era * 400;
    doy = doe - (365 * yoe + floor(yoe / 4) - floor(yoe / 100));
    mp = floor((5 * doy + 2) / 153);
    dayNumber = doy - floor((153 * mp + 2) / 5) + 1;
    if mp < 10
        month = mp + 3;
    else
        month = mp - 9;
    end
    if month <= 2
        year = year + 1;
    end
end

function value = median_value(values)
    ordered = sort(values(:));
    count = numel(ordered);
    mid = floor(count / 2);
    if mod(count, 2) == 1
        value = ordered(mid + 1);
    else
        value = 0.5 * (ordered(mid) + ordered(mid + 1));
    end
end

function text = clock_text(minutes)
    if isempty(minutes) || ~isscalar(minutes) || ~isnumeric(minutes) || ~isfinite(minutes)
        text = 'nan';
        return
    end
    total = mod(floor(minutes * 60 + 0.5), 86400);
    hourValue = floor(total / 3600);
    minuteValue = floor(mod(total, 3600) / 60);
    secondValue = mod(total, 60);
    text = sprintf('%02d:%02d:%02d', hourValue, minuteValue, secondValue);
end

function value = nan_if_empty(raw)
    if isempty(raw)
        value = NaN;
    else
        value = raw;
    end
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
    if ~isempty(strfind(lower(text), 'e')) %#ok<STREMP>
        if abs(value - round(value)) <= 1e-6 * max(abs(value), 1)
            text = sprintf('%.0f', value);
        else
            text = sprintf('%.4f', value);
        end
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
    key = regexprep(text, '[\s_\-]', '');
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
    if iscell(value)
        if numel(value) ~= 1
            error('pv_daily_features:BadOption', '%s must be a finite number', name);
        end
        value = value{1};
    end
    if ischar(value) || is_string_value(value)
        number = str2double(as_char(value));
    elseif isnumeric(value)
        number = double(value);
    else
        error('pv_daily_features:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('pv_daily_features:BadOption', '%s must be a finite number', name);
    end
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('pv_daily_features:BadOption', '%s must be a positive finite number', name);
    end
end

function number = nonnegative_number(name, value)
    number = finite_number(name, value);
    if number < 0
        error('pv_daily_features:BadOption', '%s must be zero or a positive finite number', name);
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
    error('pv_daily_features:BadOption', '%s must be true or false', name);
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
    keys = {'time_col', 'power_col', 'p_rated_kw', 'p_on_kw', 'ramp_minutes', ...
        'step_minutes', 'day', 'csv_path', 'output_csv', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(as_char(value)), keys));
end
