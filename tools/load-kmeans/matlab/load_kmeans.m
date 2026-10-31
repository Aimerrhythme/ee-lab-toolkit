function result = load_kmeans(source, varargin)
%LOAD_KMEANS Cluster typical daily load shapes with Lloyd k-means.
%   RESULT = LOAD_KMEANS(CSVPATH, 'k', 3, 'seed', 0, 'normalize', 'peak')
%   RESULT = LOAD_KMEANS(PROFILES)
%   RESULT = LOAD_KMEANS(MINUTES, POWER, 'day', '2024-03-04')
%   RESULT = LOAD_KMEANS(TIMESTAMPS, POWER)
%
%   Same algorithm as python/load_kmeans.py, in base MATLAB (no toolbox).
%   Each day is one row. Peak normalization divides that row by its maximum.
%   Centers come from k-means++ and Lloyd updates. n_init restarts keep the
%   lowest within-cluster SSE. Clusters are then renumbered from 1 by the
%   hour of each centroid peak, earliest first.
%
%       x_d = P_d / max(P_d)                  peak normalization
%       SSE = sum_d || x_d - c_label(d) ||^2
%
%   Name-value keys match Python: k, seed, normalize, n_init, max_iter,
%   step_minutes, time_col, power_col, dates, day, csv_path, output_csv,
%   output_png, show. MATLAB name-value pairs are case-insensitive.
%   Numeric minutes must lie in [0, 1440). Duplicate timestamps keep the
%   first row. Blank CSV power cells are dropped.

    if nargin < 1
        source = [];
    end
    [source, power, rest] = split_source(source, varargin);
    parser = inputParser;
    parser.FunctionName = 'load_kmeans';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('k', 3, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('seed', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('normalize', 'peak', @is_text_scalar);
    parser.addParameter('n_init', 10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('max_iter', 100, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('step_minutes', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('time_col', '', @is_text_scalar);
    parser.addParameter('power_col', '', @is_text_scalar);
    parser.addParameter('dates', {}, @(x) iscell(x) || is_text_scalar(x) || is_string_value(x));
    parser.addParameter('day', '', @is_text_scalar);
    parser.addParameter('csv_path', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    k = integral_number('k', opt.k, 1, 'k must be a positive integer');
    seed = integral_number('seed', opt.seed, 0, 'seed must be a non-negative integer');
    nInit = integral_number('n_init', opt.n_init, 1, 'n_init must be a positive integer');
    maxIter = integral_number('max_iter', opt.max_iter, 1, 'max_iter must be a positive integer');
    normalize = normalize_name(opt.normalize);
    if isempty(opt.step_minutes)
        stepMinutes = [];
    else
        stepMinutes = positive_number('step_minutes', opt.step_minutes);
    end
    showFig = as_bool('show', opt.show);
    [raw, dates, minute, step, resampled, nRows, nMissing, nDuplicates] = resolve_input( ...
        opt, source, power, stepMinutes);
    nDays = size(raw, 1);
    if k > nDays
        error('load_kmeans:BadOption', 'k must not exceed the number of days (%d)', nDays);
    end
    profiles = normalize_profiles(raw, normalize, dates);
    [labels, centroids, nIter, attempt] = best_fit(profiles, k, seed, nInit, maxIter);
    hour = minute(:) / 60;
    peakKw = max(raw, [], 2);
    daySse = row_sse(profiles, centroids, labels);
    sse = sum_1d(daySse);
    silhouette = silhouette_score(profiles, labels, k);
    sizes = zeros(k, 1);
    for index = 1:numel(labels)
        sizes(labels(index)) = sizes(labels(index)) + 1;
    end
    peakHour = zeros(k, 1);
    centroidsKw = nan(k, size(raw, 2));
    meanPeak = nan(k, 1);
    for cluster = 1:k
        [~, peakIndex] = max(centroids(cluster, :));
        peakHour(cluster) = hour(peakIndex);
        member = find(labels == cluster);
        if isempty(member)
            continue
        end
        centroidsKw(cluster, :) = mean_rows(raw(member, :));
        meanPeak(cluster) = mean_1d(peakKw(member));
    end
    summary = format_result(dates, labels, peakKw, daySse, sizes, peakHour, meanPeak, ...
        k, seed, nInit, normalize, sse, silhouette, nIter, attempt, step, resampled, ...
        nRows, nMissing, nDuplicates);

    outputCsv = as_char(opt.output_csv);
    outputPng = as_char(opt.output_png);
    if ~isempty(outputCsv)
        write_assignments(outputCsv, dates, labels, peakKw, daySse);
    end
    if ~isempty(outputPng) || showFig
        fig = render_figure(hour, profiles, centroids, labels, sizes, normalize, k, sse, ...
            silhouette, outputPng, showFig);
    else
        fig = [];
    end

    result = struct();
    result.labels = labels(:);
    result.centroids = centroids;
    result.centroids_kw = centroidsKw;
    result.profiles = profiles;
    result.power_kw = raw;
    result.dates = dates(:);
    result.hour = hour(:);
    result.minute = minute(:);
    result.k = k;
    result.seed = seed;
    result.n_init = nInit;
    result.max_iter = maxIter;
    result.normalize = normalize;
    result.sse = sse;
    result.silhouette = silhouette;
    result.cluster_sizes = sizes(:);
    result.n_iter = nIter;
    result.attempt = attempt;
    result.day_sse = daySse(:);
    result.peak_kw = peakKw(:);
    result.centroid_peak_hour = peakHour(:);
    result.mean_peak_kw = meanPeak(:);
    result.step_minutes = step;
    result.resampled = logical(resampled);
    result.summary = summary;
    result.n_rows = nRows;
    result.n_missing = nMissing;
    result.n_duplicates = nDuplicates;
    result.n_days = nDays;
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
        error('load_kmeans:BadOption', ...
            'pass a CSV path, a profile matrix, or time and power; the first argument is not a scalar');
    end
    if is_time_vector(source) && ~isempty(args) && is_numeric_vector(args{1})
        power = args{1};
        if numel(args) < 2
            rest = {};
        else
            rest = args(2:end);
        end
    elseif ~isempty(source) && ~is_text_scalar(source) && ~isnumeric(source)
        error('load_kmeans:BadOption', ...
            'source must be a CSV path, a profile matrix, or time with power');
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

function [raw, dates, minute, step, resampled, nRows, nMissing, nDuplicates] = resolve_input(opt, source, power, stepMinutes)
    if ~isempty(power)
        if ~isempty(as_char(opt.csv_path))
            error('load_kmeans:BadOption', 'pass time and power, or a CSV path, not both');
        end
        if ~isempty(opt.dates)
            error('load_kmeans:BadOption', 'dates applies to a profile matrix, not a time series');
        end
        if ~isempty(as_char(opt.time_col)) || ~isempty(as_char(opt.power_col))
            error('load_kmeans:BadOption', ...
                'time_col and power_col apply to a CSV, not to time and power vectors');
        end
        [samples, nDuplicates] = samples_from_vectors(source, power, as_char(opt.day));
        [raw, dates, minute, step, resampled, nRows, nMissing, nDuplicates] = pack_days( ...
            group_days(samples), stepMinutes, size(samples, 1), 0, nDuplicates);
        return
    end
    if isnumeric(source) && ~isempty(source)
        if ~isempty(as_char(opt.csv_path))
            error('load_kmeans:BadOption', 'pass a profile matrix or a CSV path, not both');
        end
        if ~isempty(as_char(opt.day))
            error('load_kmeans:BadOption', 'day applies to numeric minutes, not a profile matrix');
        end
        if ~isempty(as_char(opt.time_col)) || ~isempty(as_char(opt.power_col))
            error('load_kmeans:BadOption', ...
                'time_col and power_col apply to a CSV, not to a profile matrix');
        end
        if ~isempty(stepMinutes)
            error('load_kmeans:BadOption', 'step_minutes applies to a time series, not a profile matrix');
        end
        raw = coerce_matrix(source);
        nDays = size(raw, 1);
        nTimes = size(raw, 2);
        dates = matrix_dates(opt.dates, nDays);
        step = 1440 / nTimes;
        minute = (0:(nTimes - 1)).' * step;
        resampled = false;
        nRows = nDays * nTimes;
        nMissing = 0;
        nDuplicates = 0;
        return
    end
    if ~isempty(opt.dates)
        error('load_kmeans:BadOption', 'dates applies to a profile matrix, not a CSV');
    end
    if ~isempty(as_char(opt.day))
        error('load_kmeans:BadOption', 'day applies to numeric minutes, not a CSV');
    end
    csvPath = as_char(opt.csv_path);
    if is_text_scalar(source) && ~isempty(as_char(source))
        if ~isempty(csvPath)
            error('load_kmeans:BadOption', 'pass a CSV path once, either positionally or as csv_path=');
        end
        csvPath = as_char(source);
    elseif ~isempty(source)
        error('load_kmeans:BadOption', 'source must be a CSV path, a profile matrix, or time with power');
    end
    if isempty(csvPath)
        error('load_kmeans:BadOption', 'pass a CSV path, a profile matrix, or time and power');
    end
    [rows, nMissing] = read_power_csv(csvPath, as_char(opt.time_col), as_char(opt.power_col));
    [samples, nDuplicates] = clean_samples(rows);
    if isempty(samples)
        error('load_kmeans:BadOption', 'No power samples remain after cleaning');
    end
    [raw, dates, minute, step, resampled, nRows, nMissing, nDuplicates] = pack_days( ...
        group_days(samples), stepMinutes, size(samples, 1), nMissing, nDuplicates);
end

function raw = coerce_matrix(source)
    if isvector(source)
        raw = double(source(:)).';
    else
        raw = double(source);
    end
    if ndims(raw) ~= 2 || size(raw, 1) < 1 || size(raw, 2) < 2
        error('load_kmeans:BadOption', 'a daily profile needs at least 2 samples');
    end
    if any(~isfinite(raw(:)))
        error('load_kmeans:BadOption', 'profiles must be finite');
    end
end

function labels = matrix_dates(dates, nDays)
    if isempty(dates)
        labels = cell(nDays, 1);
        for index = 1:nDays
            labels{index} = sprintf('day-%02d', index);
        end
        return
    end
    if is_text_scalar(dates)
        if nDays ~= 1
            error('load_kmeans:BadOption', 'dates must have one entry per day');
        end
        labels = {as_char(dates)};
    elseif iscell(dates)
        labels = cell(numel(dates), 1);
        for index = 1:numel(dates)
            labels{index} = strtrim(as_char(dates{index}));
        end
    elseif is_string_value(dates)
        labels = cell(numel(dates), 1);
        for index = 1:numel(dates)
            labels{index} = strtrim(as_char(dates(index)));
        end
    else
        error('load_kmeans:BadOption', 'dates must have one entry per day');
    end
    if numel(labels) ~= nDays
        error('load_kmeans:BadOption', 'dates must have one entry per day');
    end
    for index = 1:numel(labels)
        if isempty(labels{index})
            error('load_kmeans:BadOption', 'dates must not be blank');
        end
    end
end

function [samples, nDuplicates] = samples_from_vectors(time, power, dayText)
    if ~is_numeric_vector(power)
        if isempty(power)
            error('load_kmeans:BadOption', 'power must not be empty');
        end
        error('load_kmeans:BadOption', 'power must be a numeric vector');
    end
    values = double(power(:));
    if any(~isfinite(values))
        error('load_kmeans:BadOption', 'power must be finite');
    end
    parts = time_parts(time, dayText);
    if size(parts, 1) ~= numel(values)
        error('load_kmeans:BadOption', 'time and power must have the same length');
    end
    [samples, nDuplicates] = clean_samples([parts, values]);
    if isempty(samples)
        error('load_kmeans:BadOption', 'time must not be empty');
    end
end

function parts = time_parts(time, dayText)
    if is_numeric_vector(time)
        minutes = double(time(:));
        if any(~isfinite(minutes) | minutes < 0 | minutes >= 1440)
            error('load_kmeans:BadOption', 'numeric minutes must be in [0, 1440)');
        end
        if isempty(dayText)
            dayText = '1970-01-01';
        end
        [year, month, dayNumber] = parse_day(dayText);
        parts = zeros(numel(minutes), 4);
        for index = 1:numel(minutes)
            parts(index, :) = [year, month, dayNumber, minutes(index)];
        end
        return
    end
    if ~isempty(dayText)
        error('load_kmeans:BadOption', 'day applies to numeric minutes, not to timestamps');
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
        error('load_kmeans:BadOption', 'time must be a vector of timestamps or minutes');
    end
    parts = zeros(numel(texts), 4);
    for index = 1:numel(texts)
        [year, month, dayNumber, minuteOfDay, ok] = parse_timestamp(texts{index});
        if ~ok
            error('load_kmeans:BadOption', 'could not parse timestamp ''%s''', as_char(texts{index}));
        end
        parts(index, :) = [year, month, dayNumber, minuteOfDay];
    end
end

function parts = parts_from_datetime(value)
    if ~isempty(value.TimeZone)
        error('load_kmeans:BadOption', 'timestamps must be naive local time');
    end
    value = value(:);
    parts = [double(year(value)), double(month(value)), double(day(value)), ...
        double(hour(value) * 60 + minute(value) + second(value) / 60)];
end

function [raw, dates, minute, step, resampled, nRows, nMissing, nDuplicates] = pack_days(days, stepMinutes, nRows, nMissing, nDuplicates)
    if isempty(days)
        error('load_kmeans:BadOption', 'No power samples remain after cleaning');
    end
    for index = 1:numel(days)
        if numel(days(index).minute) < 2
            error('load_kmeans:BadOption', 'each day needs at least 2 samples (date %s)', days(index).date);
        end
        if any(diff(days(index).minute) <= 0)
            error('load_kmeans:BadOption', 'timestamps on %s must be strictly increasing', days(index).date);
        end
    end
    [minute, raw, step, resampled] = align_days(days, stepMinutes);
    dates = cell(numel(days), 1);
    for index = 1:numel(days)
        dates{index} = days(index).date;
    end
end

function [minute, raw, step, resampled] = align_days(days, stepMinutes)
    grid0 = days(1).minute(:);
    same = true;
    for index = 1:numel(days)
        candidate = days(index).minute(:);
        if numel(candidate) ~= numel(grid0) || max(abs(candidate - grid0)) > 1e-6
            same = false;
            break
        end
    end
    if same && step_matches(grid0, stepMinutes)
        minute = grid0;
        raw = zeros(numel(days), numel(grid0));
        for index = 1:numel(days)
            raw(index, :) = days(index).power(:).';
        end
        step = reported_step(minute, stepMinutes);
        resampled = false;
        return
    end
    if isempty(stepMinutes)
        step = median_step(days);
    else
        step = stepMinutes;
    end
    minute = full_day_grid(step);
    raw = zeros(numel(days), numel(minute));
    for index = 1:numel(days)
        raw(index, :) = interp_day(days(index).date, days(index).minute, days(index).power, minute).';
    end
    resampled = true;
end

function tf = step_matches(grid, stepMinutes)
    if isempty(stepMinutes)
        tf = true;
        return
    end
    if numel(grid) < 2
        tf = false;
        return
    end
    tf = max(abs(diff(grid) - stepMinutes)) <= 1e-6 * max(stepMinutes, 1);
end

function step = reported_step(grid, stepMinutes)
    if ~isempty(stepMinutes)
        step = stepMinutes;
        return
    end
    step = median_value(diff(grid));
end

function step = median_step(days)
    diffs = [];
    for index = 1:numel(days)
        if numel(days(index).minute) >= 2
            diffs = [diffs; diff(days(index).minute(:))]; %#ok<AGROW>
        end
    end
    if isempty(diffs)
        error('load_kmeans:BadOption', 'each day needs at least 2 samples');
    end
    step = median_value(diffs);
end

function grid = full_day_grid(step)
    nSteps = round(1440 / step);
    if nSteps < 2 || abs(nSteps * step - 1440) > 1e-6 * max(step, 1)
        error('load_kmeans:BadOption', 'step_minutes must divide 24 hours into at least 2 samples');
    end
    grid = (step * (0:(nSteps - 1))).';
end

function values = interp_day(date, minute, power, grid)
    minute = minute(:);
    power = power(:);
    if minute(1) > grid(1) + 1e-6 || minute(end) < grid(end) - 1e-6
        error('load_kmeans:BadOption', 'day %s does not cover the daily grid (%s through %s)', ...
            date, clock_text(grid(1)), clock_text(grid(end)));
    end
    values = interp1(minute, power, grid(:), 'linear');
end

function profiles = normalize_profiles(raw, method, dates)
    if strcmp(method, 'none')
        profiles = raw;
        return
    end
    nDays = size(raw, 1);
    if strcmp(method, 'peak')
        scale = max(raw, [], 2);
        bad = find(scale <= 0, 1, 'first');
        if ~isempty(bad)
            error('load_kmeans:BadOption', ...
                'peak normalization needs a positive daily peak (date %s)', dates{bad});
        end
    else
        scale = zeros(nDays, 1);
        for row = 1:nDays
            scale(row) = mean_1d(raw(row, :));
        end
        bad = find(scale <= 0, 1, 'first');
        if ~isempty(bad)
            error('load_kmeans:BadOption', ...
                'mean normalization needs a positive daily mean (date %s)', dates{bad});
        end
    end
    profiles = raw ./ scale;
end

function [labels, centroids, nIter, attemptOut] = best_fit(profiles, k, seed, nInit, maxIter)
    bestSse = inf;
    bestLabels = [];
    bestCentroids = [];
    bestIter = 0;
    bestAttempt = 0;
    for attempt = 0:(nInit - 1)
        [labels, centroids, nIter] = fit_once(profiles, k, mod(seed + attempt, 4294967296), maxIter);
        sse = sum_1d(row_sse(profiles, centroids, labels));
        if sse < bestSse
            bestSse = sse;
            bestLabels = labels;
            bestCentroids = centroids;
            bestIter = nIter;
            bestAttempt = attempt;
        end
    end
    [labels, centroids] = relabel_clusters(bestCentroids, bestLabels);
    nIter = bestIter;
    attemptOut = bestAttempt;
end

function [labels, centroids, nIter] = fit_once(x, k, seed, maxIter)
    rng = struct('state', mod(double(seed), 4294967296));
    centroids = kmeans_pp(x, k, rng);
    labels = assign_labels(x, centroids);
    nIter = 0;
    for step = 1:maxIter %#ok<NASGU>
        centroids = update_centroids(x, labels, centroids);
        nIter = nIter + 1;
        updated = assign_labels(x, centroids);
        if isequal(updated, labels)
            labels = updated;
            return
        end
        labels = updated;
    end
end

function centroids = kmeans_pp(x, k, rng)
    n = size(x, 1);
    [rng, draw] = lcg_u32(rng); %#ok<ASGLU>
    chosen = mod(draw, n) + 1;
    for extra = 2:k %#ok<NASGU>
        d2 = sqdist_to_centers(x, x(chosen, :));
        total = sum_1d(d2);
        if ~(total > 0)
            pick = 0;
            for index = 1:n
                if ~any(chosen == index)
                    pick = index;
                    break
                end
            end
        else
            [rng, draw] = lcg_u32(rng); %#ok<ASGLU>
            target = (draw / 4294967296) * total;
            cumulative = 0;
            pick = n;
            for index = 1:n
                cumulative = cumulative + d2(index);
                if cumulative >= target
                    pick = index;
                    break
                end
            end
            if any(chosen == pick)
                pick = farthest_unused(d2, chosen);
            end
        end
        chosen(end + 1) = pick; %#ok<AGROW>
    end
    centroids = x(chosen, :);
end

function [rng, value] = lcg_u32(rng)
    rng.state = mod(1664525 * rng.state + 1013904223, 4294967296);
    value = rng.state;
end

function pick = farthest_unused(d2, used)
    best = 0;
    bestD = -inf;
    for index = 1:numel(d2)
        if any(used == index)
            continue
        end
        if d2(index) > bestD
            best = index;
            bestD = d2(index);
        end
    end
    if best == 0
        error('load_kmeans:BadOption', 'k exceeds the number of distinct profiles');
    end
    pick = best;
end

function d2 = sqdist_to_centers(x, centers)
    d2 = inf(size(x, 1), 1);
    for center = 1:size(centers, 1)
        for row = 1:size(x, 1)
            value = sqdist(x(row, :), centers(center, :));
            if value < d2(row)
                d2(row) = value;
            end
        end
    end
end

function labels = assign_labels(x, centroids)
    n = size(x, 1);
    k = size(centroids, 1);
    labels = ones(n, 1);
    for row = 1:n
        best = 1;
        bestD = inf;
        for cluster = 1:k
            value = sqdist(x(row, :), centroids(cluster, :));
            if value < bestD
                best = cluster;
                bestD = value;
            end
        end
        labels(row) = best;
    end
end

function newCentroids = update_centroids(x, labels, centroids)
    k = size(centroids, 1);
    newCentroids = zeros(k, size(x, 2));
    empties = [];
    for cluster = 1:k
        member = find(labels == cluster);
        if ~isempty(member)
            newCentroids(cluster, :) = mean_rows(x(member, :));
        else
            empties(end + 1) = cluster; %#ok<AGROW>
        end
    end
    if isempty(empties)
        return
    end
    d2own = zeros(size(x, 1), 1);
    for row = 1:size(x, 1)
        d2own(row) = sqdist(x(row, :), centroids(labels(row), :));
    end
    picked = false(size(x, 1), 1);
    for slot = 1:numel(empties)
        best = 0;
        bestD = -inf;
        for row = 1:size(x, 1)
            if picked(row)
                continue
            end
            if d2own(row) > bestD
                best = row;
                bestD = d2own(row);
            end
        end
        picked(best) = true;
        newCentroids(empties(slot), :) = x(best, :);
    end
end

function [labels, centroids] = relabel_clusters(centroids, labels)
    k = size(centroids, 1);
    peak = zeros(k, 1);
    for cluster = 1:k
        [~, peak(cluster)] = max(centroids(cluster, :));
    end
    [~, order] = sortrows([peak, (1:k).']);
    remap = zeros(k, 1);
    for newIndex = 1:k
        remap(order(newIndex)) = newIndex;
    end
    labels = remap(labels);
    centroids = centroids(order, :);
end

function values = row_sse(x, centroids, labels)
    values = zeros(size(x, 1), 1);
    for row = 1:size(x, 1)
        values(row) = sqdist(x(row, :), centroids(labels(row), :));
    end
end

function score = silhouette_score(x, labels, k)
    n = size(x, 1);
    if k < 2 || n < 2
        score = NaN;
        return
    end
    sizes = zeros(k, 1);
    for index = 1:n
        sizes(labels(index)) = sizes(labels(index)) + 1;
    end
    if any(sizes == 0)
        score = NaN;
        return
    end
    members = cell(k, 1);
    for cluster = 1:k
        members{cluster} = find(labels == cluster);
    end
    scores = zeros(n, 1);
    for row = 1:n
        own = labels(row);
        group = members{own};
        if numel(group) <= 1
            scores(row) = 0;
            continue
        end
        aSum = 0;
        for index = 1:numel(group)
            other = group(index);
            if other == row
                continue
            end
            aSum = aSum + sqrt(sqdist(x(row, :), x(other, :)));
        end
        a = aSum / (numel(group) - 1);
        b = inf;
        for cluster = 1:k
            if cluster == own
                continue
            end
            bSum = 0;
            others = members{cluster};
            for index = 1:numel(others)
                bSum = bSum + sqrt(sqdist(x(row, :), x(others(index), :)));
            end
            b = min(b, bSum / numel(others));
        end
        denom = max(a, b);
        if denom == 0
            scores(row) = 0;
        else
            scores(row) = (b - a) / denom;
        end
    end
    score = mean_1d(scores);
end

function value = sqdist(left, right)
    acc = 0;
    left = left(:);
    right = right(:);
    for index = 1:numel(left)
        diffValue = left(index) - right(index);
        acc = acc + diffValue * diffValue;
    end
    value = acc;
end

function centroid = mean_rows(block)
    acc = zeros(1, size(block, 2));
    for row = 1:size(block, 1)
        acc = acc + block(row, :);
    end
    centroid = acc / size(block, 1);
end

function value = mean_1d(values)
    acc = 0;
    count = numel(values);
    for index = 1:count
        acc = acc + values(index);
    end
    value = acc / count;
end

function value = sum_1d(values)
    acc = 0;
    for index = 1:numel(values)
        acc = acc + values(index);
    end
    value = acc;
end

function [rows, nMissing] = read_power_csv(csvPath, timeCol, powerCol)
    if exist(csvPath, 'file') ~= 2
        error('load_kmeans:FileNotFound', 'CSV not found: %s', csvPath);
    end
    raw = fileread(csvPath);
    if isempty(strtrim(raw))
        error('load_kmeans:EmptyCsv', 'CSV is empty: %s', csvPath);
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
        error('load_kmeans:EmptyCsv', 'CSV is empty: %s', csvPath);
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
        error('load_kmeans:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    headers = table{1};
    for index = 1:numel(headers)
        headers{index} = strtrim(headers{index});
    end
    timeName = resolve_column(headers, timeCol, time_aliases(), 'time');
    powerName = resolve_column(headers, powerCol, power_aliases(), 'power');
    if strcmp(timeName, powerName)
        error('load_kmeans:BadOption', 'time and power columns must be different');
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
            error('load_kmeans:BadOption', 'a row is missing its timestamp');
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
        [year, month, dayNumber, minuteOfDay, ok] = parse_timestamp(power_time(cells, timeIndex));
        if ~ok
            error('load_kmeans:BadOption', 'could not parse timestamp ''%s''', strtrim(cells{timeIndex}));
        end
        value = str2double(powerText);
        if ~isscalar(value) || ~isfinite(value)
            error('load_kmeans:BadOption', 'power must be finite');
        end
        rows(end + 1, :) = [year, month, dayNumber, minuteOfDay, value]; %#ok<AGROW>
    end
    if isempty(rows) && nMissing == 0
        if dataRows == 0
            error('load_kmeans:EmptyCsv', 'CSV has no data rows: %s', csvPath);
        end
        error('load_kmeans:BadOption', 'No power samples remain after cleaning');
    end
end

function text = power_time(cells, timeIndex)
    text = strtrim(cells{timeIndex});
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

function days = group_days(samples)
    if isempty(samples)
        days = struct('date', {}, 'minute', {}, 'power', {});
        return
    end
    breaks = 1;
    for index = 2:size(samples, 1)
        if any(samples(index, 1:3) ~= samples(index - 1, 1:3))
            breaks(end + 1) = index; %#ok<AGROW>
        end
    end
    breaks(end + 1) = size(samples, 1) + 1; %#ok<AGROW>
    days = struct('date', {}, 'minute', {}, 'power', {});
    for group = 1:(numel(breaks) - 1)
        block = samples(breaks(group):(breaks(group + 1) - 1), :);
        item.date = sprintf('%04d-%02d-%02d', block(1, 1), block(1, 2), block(1, 3));
        item.minute = block(:, 4);
        item.power = block(:, 5);
        days(end + 1) = item; %#ok<AGROW>
    end
end

function text = format_result(dates, labels, peakKw, daySse, sizes, peakHour, meanPeak, ...
        k, seed, nInit, normalize, sse, silhouette, nIter, attempt, step, resampled, ...
        nRows, nMissing, nDuplicates)
    header = sprintf(['days=%d  k=%d  seed=%d  n_init=%d  normalize=%s  sse=%s  ', ...
        'silhouette=%s  n_iter=%d  attempt=%d  step_min=%s  resampled=%d'], ...
        numel(dates), k, seed, nInit, normalize, compact_num(sse), compact_num(silhouette), ...
        nIter, attempt, compact_num(step), double(resampled));
    rows = sprintf('rows=%d  missing=%d  duplicates=%d', nRows, nMissing, nDuplicates);
    clusters = cell(k, 1);
    for index = 1:k
        clusters{index} = sprintf('cluster=%d  n=%d  peak_hour=%s  mean_peak_kw=%s', ...
            index, sizes(index), compact_num(peakHour(index)), compact_num(meanPeak(index)));
    end
    days = cell(numel(dates), 1);
    for index = 1:numel(dates)
        days{index} = sprintf('date=%s  label=%d  peak_kw=%s  day_sse=%s', ...
            dates{index}, labels(index), compact_num(peakKw(index)), compact_num(daySse(index)));
    end
    text = strjoin({header, rows, strjoin(clusters, sprintf('\n')), strjoin(days, sprintf('\n'))}, sprintf('\n\n'));
end

function write_assignments(csvPath, dates, labels, peakKw, daySse)
    folder = fileparts(csvPath);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
    fid = fopen(csvPath, 'w');
    if fid < 0
        error('load_kmeans:BadOption', 'could not write CSV: %s', csvPath);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, 'date,label,peak_kw,day_sse\n');
    for index = 1:numel(dates)
        fprintf(fid, '%s,%d,%s,%s\n', dates{index}, labels(index), csv_num(peakKw(index)), csv_num(daySse(index)));
    end
end

function fig = render_figure(hour, profiles, centroids, labels, sizes, normalize, k, sse, silhouette, outputPng, showFig)
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
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [80 40 1040 820], ...
        'Name', 'load-kmeans', 'NumberTitle', 'off');
    profileAxis = subplot(2, 1, 1, 'Parent', fig);
    centroidAxis = subplot(2, 1, 2, 'Parent', fig);
    hold(profileAxis, 'on');
    hold(centroidAxis, 'on');
    legendText = cell(1, k);
    for cluster = 1:k
        color = palette(mod(cluster - 1, size(palette, 1)) + 1, :);
        legendText{cluster} = sprintf('cluster %d (n=%d)', cluster, sizes(cluster));
        member = find(labels == cluster);
        if isempty(member)
            plot(profileAxis, nan, nan, 'Color', color);
        end
        first = true;
        for index = 1:numel(member)
            if first
                plot(profileAxis, hour, profiles(member(index), :), 'Color', color, 'LineWidth', 1.15);
                first = false;
            else
                plot(profileAxis, hour, profiles(member(index), :), 'Color', color, 'LineWidth', 1.15, ...
                    'HandleVisibility', 'off');
            end
        end
        plot(profileAxis, hour, centroids(cluster, :), 'Color', color, 'LineWidth', 2.4, ...
            'HandleVisibility', 'off');
        plot(centroidAxis, hour, centroids(cluster, :), 'Color', color, 'LineWidth', 2.3);
    end
    hold(profileAxis, 'off');
    hold(centroidAxis, 'off');
    yLabel = y_label(normalize);
    style_axis(profileAxis, 'Normalized daily profiles', yLabel, hour);
    style_axis(centroidAxis, 'Typical day centroids', yLabel, hour);
    xlabel(centroidAxis, 'Hour of day');
    apply_legend(profileAxis, legendText);
    apply_legend(centroidAxis, legendText);
    titleText = sprintf('k-means daily load    k=%d    SSE=%s    silhouette=%s', ...
        k, compact_num(sse), compact_num(silhouette));
    if exist('sgtitle', 'file') == 2 || exist('sgtitle', 'builtin') == 5
        sgtitle(titleText);
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

function text = y_label(normalize)
    if strcmp(normalize, 'peak')
        text = 'Power / daily peak';
    elseif strcmp(normalize, 'mean')
        text = 'Power / daily mean';
    else
        text = 'Power (kW)';
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
        error('load_kmeans:BadOption', 'Column ''%s'' not found for %s. Available: %s', ...
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
    error('load_kmeans:BadOption', ...
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

function [year, month, dayNumber] = parse_day(text)
    raw = strtrim(as_char(text));
    if numel(raw) ~= 10 || raw(5) ~= '-' || raw(8) ~= '-' || ~all_digits(raw([1:4, 6:7, 9:10]))
        error('load_kmeans:BadOption', 'day must be YYYY-MM-DD');
    end
    year = str2double(raw(1:4));
    month = str2double(raw(6:7));
    dayNumber = str2double(raw(9:10));
    if ~valid_date(year, month, dayNumber)
        error('load_kmeans:BadOption', 'day must be a real calendar date');
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
        error('load_kmeans:BadOption', '%s must be a finite number', name);
    end
    if ~isscalar(number) || ~isfinite(number)
        error('load_kmeans:BadOption', '%s must be a finite number', name);
    end
end

function number = positive_number(name, value)
    number = finite_number(name, value);
    if ~(number > 0)
        error('load_kmeans:BadOption', '%s must be a positive finite number', name);
    end
end

function number = integral_number(name, value, minimum, message) %#ok<INUSL>
    if islogical(value) || ~isnumeric(value) || ~isscalar(value) || ~isfinite(value) || value ~= floor(value)
        error('load_kmeans:BadOption', '%s', message);
    end
    number = double(value);
    if number < minimum
        error('load_kmeans:BadOption', '%s', message);
    end
end

function name = normalize_name(value)
    name = lower(strtrim(as_char(value)));
    if ~(strcmp(name, 'peak') || strcmp(name, 'mean') || strcmp(name, 'none'))
        error('load_kmeans:BadOption', 'normalize must be peak, mean, or none');
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
    error('load_kmeans:BadOption', '%s must be true or false', name);
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
    keys = {'k', 'seed', 'normalize', 'n_init', 'max_iter', 'step_minutes', ...
        'time_col', 'power_col', 'dates', 'day', 'csv_path', 'output_csv', 'output_png', 'show'};
    tf = any(strcmpi(strtrim(as_char(value)), keys));
end
