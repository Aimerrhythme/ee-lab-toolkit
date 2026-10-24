function result = load_csv_plot(csv_path, varargin)
%LOAD_CSV_PLOT Clean a load CSV and plot a standard load figure.
%   RESULT = LOAD_CSV_PLOT(CSV_PATH) reads a timestamp column and a load
%   column (kW), fills missing values, flags spike outliers, and draws a
%   clean figure. Name-value keys match the Python keyword arguments.
%
%   RESULT = LOAD_CSV_PLOT(CSV_PATH, 'agg', 'daily_mean', ...
%       'output_png', 'load.png', 'show', false)
%
%   Keys: time_col, load_col, agg, outlier_method, z_thresh, iqr_k,
%   fill_method, output_png, show.
%
%   agg: 'none' | 'mean' | 'daily_mean'
%   outlier_method: 'iqr' | 'zscore' | 'none'
%   fill_method: 'interpolate' | 'ffill' | 'drop'
%
%   RESULT fields: time, load_kw, load_raw_kw, is_outlier, n_rows,
%   n_missing, n_outliers, mean_kw, daily_mean, agg, output_png, fig.
%   daily_mean is a table with date and mean_kw. It has rows only when
%   agg is 'daily_mean'. mean_kw is always the mean of the cleaned series.
%
%   Pipeline (same order as python/load_csv_plot.py):
%   1. Read the table and resolve columns.
%   2. Parse timestamps, sort, drop duplicate timestamps (keep first).
%   3. Count missing load values.
%   4. Drop missing rows when fill_method is drop.
%   5. Flag spike outliers.
%   6. Fill missing samples and, unless dropping, fill across spikes.
%   7. Optionally aggregate a daily mean on the cleaned series.
%   8. Plot and optionally save a PNG.

    parser = inputParser;
    parser.FunctionName = 'load_csv_plot';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addRequired('csv_path', @is_text_scalar);
    parser.addParameter('time_col', '', @is_text_scalar);
    parser.addParameter('load_col', '', @is_text_scalar);
    parser.addParameter('agg', 'none', @is_text_scalar);
    parser.addParameter('outlier_method', 'iqr', @is_text_scalar);
    parser.addParameter('z_thresh', 3.0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('iqr_k', 1.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('fill_method', 'interpolate', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(csv_path, varargin{:});
    opt = parser.Results;

    csvPath = char(strtrim(string(csv_path)));
    if ~isfile(csvPath)
        error('load_csv_plot:FileNotFound', 'CSV not found: %s', csvPath);
    end

    agg = lower(char(strtrim(string(opt.agg))));
    outlierMethod = lower(char(strtrim(string(opt.outlier_method))));
    fillMethod = lower(char(strtrim(string(opt.fill_method))));
    assert_choice('agg', agg, {'none', 'mean', 'daily_mean'});
    assert_choice('outlier_method', outlierMethod, {'iqr', 'zscore', 'none'});
    assert_choice('fill_method', fillMethod, {'interpolate', 'ffill', 'drop'});
    if ~(opt.z_thresh > 0)
        error('load_csv_plot:BadOption', 'z_thresh must be positive');
    end
    if ~(opt.iqr_k >= 0)
        error('load_csv_plot:BadOption', 'iqr_k must be >= 0');
    end

    tableData = read_load_table(csvPath);
    names = string(tableData.Properties.VariableNames);
    if isempty(names)
        error('load_csv_plot:EmptyCsv', 'CSV is empty: %s', csvPath);
    end
    timeName = resolve_column(names, opt.time_col, time_alias_priority(), 'time');
    loadName = resolve_column(names, opt.load_col, load_alias_priority(), 'load');
    if timeName == loadName
        error('load_csv_plot:SameColumn', 'time and load columns resolved to the same field');
    end

    time = parse_time_column(column_values(tableData, timeName));
    loadRaw = parse_load_column(column_values(tableData, loadName));
    [time, loadRaw, nMissing] = prepare_series(time, loadRaw);
    if strcmp(fillMethod, 'drop')
        keep = isfinite(loadRaw);
        time = time(keep);
        loadRaw = loadRaw(keep);
    end
    if isempty(time)
        error('load_csv_plot:NoRows', 'No load rows remain after cleaning.');
    end

    isOutlier = flag_outliers(loadRaw, outlierMethod, opt.z_thresh, opt.iqr_k);
    loadKw = cleaned_load(time, loadRaw, isOutlier, fillMethod);
    if any(isfinite(loadKw))
        meanKw = mean(loadKw, 'omitnan');
    else
        meanKw = NaN;
    end
    if strcmp(agg, 'daily_mean')
        daily = daily_mean_table(time, loadKw);
    else
        daily = empty_daily();
    end

    outputPng = char(strtrim(string(opt.output_png)));
    fig = render_figure(time, loadKw, loadRaw, isOutlier, meanKw, daily, agg, outputPng, logical(opt.show));

    result = struct();
    result.time = time;
    result.load_kw = loadKw;
    result.load_raw_kw = loadRaw;
    result.is_outlier = isOutlier;
    result.n_rows = numel(time);
    result.n_missing = nMissing;
    result.n_outliers = nnz(isOutlier);
    result.mean_kw = meanKw;
    result.daily_mean = daily;
    result.agg = agg;
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

function assert_choice(name, value, allowed)
    if ~any(strcmp(value, allowed))
        error('load_csv_plot:BadOption', '%s must be one of: %s', name, strjoin(allowed, ', '));
    end
end

function tableData = read_load_table(csvPath)
    try
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
    catch
        opts = detectImportOptions(csvPath, 'VariableNamingRule', 'preserve');
    end
    tableData = readtable(csvPath, opts);
end

function names = time_alias_priority()
    names = ["timestamp", "datetime", "date_time", "datestamp", "time", "date", "ts"];
    names = [names, unicode_text([0x65F6 0x95F4 0x6233])]; % U+65F6 U+95F4 U+6233
    names = [names, unicode_text([0x65F6 0x95F4])]; % U+65F6 U+95F4
    names = [names, unicode_text([0x65F6 0x523B])]; % U+65F6 U+523B
    names = [names, unicode_text([0x65E5 0x671F])]; % U+65E5 U+671F
end

function names = load_alias_priority()
    names = ["load_kw", "power_kw", "p_kw", "demand_kw", "active_power", ...
        "load_power", "load", "power", "kw", "p"];
    loadWord = unicode_text([0x8D1F 0x8377]); % U+8D1F U+8377
    names = [names, strcat(loadWord, "(kw)"), strcat(loadWord, "kw")];
    names = [names, unicode_text([0x6709 0x529F 0x529F 0x7387])]; % U+6709 U+529F U+529F U+7387
    names = [names, unicode_text([0x6709 0x529F])]; % U+6709 U+529F
    names = [names, loadWord];
end

function text = unicode_text(codepoints)
    text = string(char(codepoints));
end

function key = normalize_name(name)
    key = lower(strtrim(string(name)));
    key = regexprep(key, '[\s_\-()]', '');
    % Fullwidth parentheses U+FF08 / U+FF09, kept as code points so this file stays ASCII.
    key = replace(key, string(char(hex2dec('FF08'))), "");
    key = replace(key, string(char(hex2dec('FF09'))), "");
end

function name = resolve_column(names, requested, priority, kind)
    names = string(names(:)).';
    norms = strings(size(names));
    for index = 1:numel(names)
        norms(index) = normalize_name(names(index));
    end
    requestedText = strtrim(string(requested));
    if strlength(requestedText) > 0
        found = find(names == requestedText, 1, 'first');
        if isempty(found)
            found = find(norms == normalize_name(requestedText), 1, 'first');
        end
        if isempty(found)
            error('load_csv_plot:ColumnNotFound', ...
                'Column "%s" not found for %s. Available: %s', ...
                requestedText, kind, strjoin(cellstr(names), ', '));
        end
        name = names(found);
        return
    end
    for index = 1:numel(priority)
        alias = normalize_name(priority(index));
        found = find(norms == alias, 1, 'first');
        if ~isempty(found)
            name = names(found);
            return
        end
    end
    error('load_csv_plot:ColumnNotFound', ...
        'Could not find a %s column. Pass %s_col explicitly. Available: %s', ...
        kind, kind, strjoin(cellstr(names), ', '));
end

function raw = column_values(tableData, colName)
    names = string(tableData.Properties.VariableNames);
    found = find(names == string(colName), 1, 'first');
    raw = tableData{:, found};
end

function time = parse_time_column(raw)
    if isdatetime(raw)
        time = raw(:);
        return
    end
    if iscell(raw)
        text = string(raw);
    else
        text = string(raw);
    end
    text = strtrim(text(:));
    try
        time = datetime(text);
    catch
        time = NaT(numel(text), 1);
    end
    time = time(:);
end

function values = parse_load_column(raw)
    if isnumeric(raw)
        values = double(raw(:));
        return
    end
    if iscell(raw)
        text = string(raw);
    else
        text = string(raw);
    end
    values = str2double(strtrim(text(:)));
end

function [time, loadRaw, nMissing] = prepare_series(time, loadRaw)
    time = time(:);
    loadRaw = double(loadRaw(:));
    loadRaw(~isfinite(loadRaw)) = NaN;
    valid = ~isnat(time);
    time = time(valid);
    loadRaw = loadRaw(valid);
    if isempty(time)
        error('load_csv_plot:NoTimestamps', 'No valid timestamps in CSV.');
    end
    [time, order] = sort(time);
    loadRaw = loadRaw(order);
    [~, firstIdx] = unique(time, 'stable');
    time = time(firstIdx);
    loadRaw = loadRaw(firstIdx);
    nMissing = sum(~isfinite(loadRaw));
end

function mask = flag_outliers(values, method, zThresh, iqrK)
    values = values(:);
    mask = false(size(values));
    finite = isfinite(values);
    if strcmp(method, 'none') || nnz(finite) < 4
        return
    end
    sample = values(finite);
    switch method
        case 'iqr'
            quartiles = prctile(sample, [25 75]);
            span = quartiles(2) - quartiles(1);
            if span == 0
                return
            end
            low = quartiles(1) - iqrK * span;
            high = quartiles(2) + iqrK * span;
            flagged = sample < low | sample > high;
        case 'zscore'
            deviation = std(sample, 0);
            if deviation == 0
                return
            end
            center = mean(sample);
            flagged = abs((sample - center) ./ deviation) > zThresh;
        otherwise
            error('load_csv_plot:BadOption', 'outlier_method must be iqr, zscore, or none.');
    end
    mask(finite) = flagged;
end

function filled = fill_linear_time(time, values)
    % Linear fill in time. Ends use the nearest finite sample (np.interp).
    filled = values(:);
    time = time(:);
    good = isfinite(filled);
    nGood = nnz(good);
    if nGood == 0
        return
    end
    if nGood == 1
        filled(~good) = filled(find(good, 1, 'first'));
        return
    end
    secondsFromStart = seconds(time - time(1));
    knownTime = secondsFromStart(good);
    knownValue = filled(good);
    missing = find(~good);
    query = secondsFromStart(missing);
    estimated = interp1(knownTime, knownValue, query, 'linear', NaN);
    estimated(query < knownTime(1)) = knownValue(1);
    estimated(query > knownTime(end)) = knownValue(end);
    filled(missing) = estimated;
end

function cleaned = cleaned_load(time, loadRaw, isOutlier, fillMethod)
    cleaned = loadRaw(:);
    if strcmp(fillMethod, 'drop')
        return
    end
    cleaned(isOutlier) = NaN;
    switch fillMethod
        case 'ffill'
            cleaned = fillmissing(cleaned, 'previous');
            cleaned = fillmissing(cleaned, 'next');
        case 'interpolate'
            cleaned = fill_linear_time(time, cleaned);
        otherwise
            error('load_csv_plot:BadOption', 'fill_method must be interpolate, ffill, or drop.');
    end
end

function daily = empty_daily()
    daily = table('Size', [0 2], 'VariableTypes', {'datetime', 'double'}, ...
        'VariableNames', {'date', 'mean_kw'});
end

function daily = daily_mean_table(time, loadKw)
    time = time(:);
    loadKw = loadKw(:);
    if isempty(time)
        daily = empty_daily();
        return
    end
    day = dateshift(time, 'start', 'day');
    [days, ~, groupId] = unique(day, 'stable');
    means = accumarray(groupId, loadKw, [], @(values) mean(values, 'omitnan'));
    daily = table(days(:), means(:), 'VariableNames', {'date', 'mean_kw'});
end

function fig = render_figure(time, loadKw, loadRaw, isOutlier, meanKw, daily, agg, outputPng, showFig)
    if showFig
        visible = 'on';
    else
        visible = 'off';
    end
    if strcmp(agg, 'daily_mean')
        figHeight = 640;
    else
        figHeight = 440;
    end
    fig = figure('Visible', visible, 'Color', 'w', 'Position', [100 100 980 figHeight], ...
        'Name', 'load-csv-plot', 'NumberTitle', 'off');

    lineColor = [31, 78, 121] / 255;
    spikeColor = [192, 57, 43] / 255;
    meanColor = [230, 126, 34] / 255;
    dailyColor = [61, 122, 106] / 255;

    if strcmp(agg, 'daily_mean')
        layout = tiledlayout(fig, 2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
        ax = nexttile(layout);
    else
        ax = axes('Parent', fig);
    end

    plot(ax, time, loadKw, 'Color', lineColor, 'LineWidth', 1.6, 'DisplayName', 'Cleaned load');
    hold(ax, 'on');
    mark_outliers(ax, time, loadKw, loadRaw, isOutlier, spikeColor);
    if strcmp(agg, 'mean') && isfinite(meanKw)
        yline(ax, meanKw, '--', 'Color', meanColor, 'LineWidth', 1.2, 'DisplayName', 'Mean');
    end
    style_time_axis(ax);
    title(ax, 'Load profile (cleaned)');
    ylabel(ax, 'Load (kW)');
    xlabel(ax, 'Time');
    legend(ax, 'Location', 'best');
    finiteClean = loadKw(isfinite(loadKw));
    if ~isempty(finiteClean)
        low = min(finiteClean);
        high = max(finiteClean);
        span = max(high - low, 1);
        ylim(ax, [low - 0.12 * span, high + 0.28 * span]);
    end
    set(ax, 'FontSize', 11);

    if strcmp(agg, 'daily_mean')
        axDaily = nexttile(layout);
        if height(daily) > 0
            plot(axDaily, daily.date, daily.mean_kw, '-o', ...
                'Color', dailyColor, 'LineWidth', 1.6, ...
                'MarkerSize', 7, 'MarkerFaceColor', dailyColor);
            pad = hours(12);
            xlim(axDaily, [daily.date(1) - pad, daily.date(end) + pad]);
        end
        title(axDaily, 'Daily mean load');
        ylabel(axDaily, 'Mean load (kW)');
        xlabel(axDaily, 'Date');
        grid(axDaily, 'on');
        axDaily.GridColor = [0.82 0.82 0.82];
        axDaily.GridAlpha = 0.35;
        xtickformat(axDaily, 'MM-dd');
        set(axDaily, 'FontSize', 11);
        box(axDaily, 'on');
    end

    drawnow;
    if strlength(strtrim(string(outputPng))) > 0
        destination = char(string(outputPng));
        folder = fileparts(destination);
        if ~isempty(folder) && ~exist(folder, 'dir')
            mkdir(folder);
        end
        exportgraphics(fig, destination, 'Resolution', 150);
    end
    if ~showFig
        close(fig);
        fig = [];
    end
end

function style_time_axis(ax)
    grid(ax, 'on');
    ax.GridColor = [0.82 0.82 0.82];
    ax.GridAlpha = 0.35;
    box(ax, 'on');
    xtickformat(ax, 'MM-dd HH:mm');
end

function mark_outliers(ax, time, loadKw, loadRaw, isOutlier, spikeColor)
    idx = find(isOutlier(:) & isfinite(loadKw(:)) & isfinite(loadRaw(:)));
    if isempty(idx)
        return
    end
    finiteRaw = loadRaw(isfinite(loadRaw));
    center = median(finiteRaw);
    if numel(idx) > 8
        deviation = abs(loadRaw(idx) - center);
        [~, order] = sort(deviation, 'ascend');
        idx = idx(order(end - 7:end));
    end
    plot(ax, time(idx), loadKw(idx), 'x', 'Color', spikeColor, ...
        'LineWidth', 1.4, 'MarkerSize', 8, 'DisplayName', 'Flagged spike');
    finiteClean = loadKw(isfinite(loadKw));
    span = max(max(finiteClean) - min(finiteClean), 1);
    for index = 1:numel(idx)
        row = idx(index);
        xPos = ruler2num(time(row), ax.XAxis);
        text(ax, xPos, loadKw(row) + 0.08 * span, format_kw(loadRaw(row)), ...
            'Color', spikeColor, 'FontSize', 8, ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom');
    end
end

function label = format_kw(value)
    if abs(value - round(value)) < 1e-6
        label = sprintf('raw %.0f kW', value);
    else
        label = sprintf('raw %.1f kW', value);
    end
end
