function result = wind_curve_binning_filter(source, varargin)
%WIND_CURVE_BINNING_FILTER Bin a wind-power curve and mark abnormal points.
%   RESULT = WIND_CURVE_BINNING_FILTER(CSVPATH)
%   RESULT = WIND_CURVE_BINNING_FILTER(WIND_MPS, POWER_KW, 'bin_width', 0.5)
%
%   Same rules as python/wind_curve_binning_filter.py, in base MATLAB
%   (no toolbox). Bins are half-open [v_min + i*bin_width, next edge).
%   Quartiles are Hyndman-Fan type 7. The fence is closed:
%   [Q1 - iqr_k*IQR, Q3 + iqr_k*IQR]. See the Python module docstring for
%   the rule order (negative, shutdown, curtailment, cut-in/cut-out, IQR).
%
%   Name-value keys match Python: bin_width, v_min, v_cut_in, v_rated,
%   v_cut_out, p_rated_kw, p_shutdown_kw, p_shutdown_theory_frac,
%   curtail_ratio, curtail_theory_frac, iqr_k, min_bin_count, wind_col,
%   power_col, output_csv, output_bins_csv, output_png, show.
%   An empty p_shutdown_kw uses 0.02 * p_rated_kw. MATLAB name-value pairs
%   are case-insensitive. show accepts true/false or 0/1.

    if nargin < 1
        source = [];
    end
    [csvPath, windIn, powerIn, rest] = split_source(source, varargin);
    parser = inputParser;
    parser.FunctionName = 'wind_curve_binning_filter';
    parser.CaseSensitive = false;
    parser.PartialMatching = false;
    parser.addParameter('bin_width', 0.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_min', 0, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_cut_in', 3, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_rated', 12, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('v_cut_out', 25, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('p_rated_kw', 2000, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('p_shutdown_kw', [], @(x) isempty(x) || (isnumeric(x) && isscalar(x)));
    parser.addParameter('p_shutdown_theory_frac', 0.10, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('curtail_ratio', 0.60, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('curtail_theory_frac', 0.30, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('iqr_k', 1.5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('min_bin_count', 5, @(x) isnumeric(x) && isscalar(x));
    parser.addParameter('wind_col', '', @is_text_scalar);
    parser.addParameter('power_col', '', @is_text_scalar);
    parser.addParameter('output_csv', '', @is_text_scalar);
    parser.addParameter('output_bins_csv', '', @is_text_scalar);
    parser.addParameter('output_png', '', @is_text_scalar);
    parser.addParameter('show', false, @(x) islogical(x) || (isnumeric(x) && isscalar(x)));
    parser.parse(rest{:});
    opt = parser.Results;

    binWidth = positive_number('bin_width', opt.bin_width);
    vMin = nonnegative_number('v_min', opt.v_min);
    vCutIn = nonnegative_number('v_cut_in', opt.v_cut_in);
    vRated = positive_number('v_rated', opt.v_rated);
    vCutOut = positive_number('v_cut_out', opt.v_cut_out);
    if ~(vCutIn < vRated && vRated < vCutOut)
        error('wind_curve_binning_filter:BadOption', ...
            'require v_cut_in < v_rated < v_cut_out');
    end
    pRated = positive_number('p_rated_kw', opt.p_rated_kw);
    if isempty(opt.p_shutdown_kw)
        pShutdown = 0.02 * pRated;
    else
        pShutdown = nonnegative_number('p_shutdown_kw', opt.p_shutdown_kw);
    end
    shutdownFrac = fraction_closed('p_shutdown_theory_frac', opt.p_shutdown_theory_frac);
    curtailRatio = fraction_open('curtail_ratio', opt.curtail_ratio);
    curtailFrac = fraction_closed('curtail_theory_frac', opt.curtail_theory_frac);
    iqrK = nonnegative_number('iqr_k', opt.iqr_k);
    minCount = positive_int('min_bin_count', opt.min_bin_count);
    showFig = as_bool('show', opt.show);
    windCol = char(opt.wind_col);
    powerCol = char(opt.power_col);
    outputCsv = char(opt.output_csv);
    outputBins = char(opt.output_bins_csv);
    outputPng = char(opt.output_png);

    if isempty(csvPath)
        if ~isempty(windCol) || ~isempty(powerCol)
            error('wind_curve_binning_filter:BadOption', ...
                'wind_col and power_col apply to CSV input');
        end
        wind = double(windIn(:));
        power = double(powerIn(:));
        nMissing = 0;
    else
        [wind, power, nMissing] = read_samples(csvPath, windCol, powerCol);
    end
    if numel(wind) ~= numel(power)
        error('wind_curve_binning_filter:BadOption', ...
            'wind and power must have the same length');
    end
    if isempty(wind)
        error('wind_curve_binning_filter:BadOption', ...
            'need at least one finite sample');
    end
    if any(~isfinite(wind)) || any(~isfinite(power)) || ~isreal(wind) || ~isreal(power)
        error('wind_curve_binning_filter:BadOption', ...
            'wind_mps and power_kw must be finite');
    end
    if any(wind < vMin)
        error('wind_curve_binning_filter:BadOption', 'wind_mps must be >= v_min');
    end

    theory = theoretical_power(wind, pRated, vCutIn, vRated, vCutOut);
    binIndex = floor((wind - vMin) ./ binWidth);
    n = numel(wind);
    flag = repmat({flag_normal()}, n, 1);
    reason = repmat({''}, n, 1);
    [flag, reason] = apply_rules(wind, power, theory, flag, reason, ...
        vCutIn, vCutOut, pRated, pShutdown, shutdownFrac, curtailRatio, curtailFrac);

    nBins = max(binIndex) + 1;
    [flag, reason, bins] = apply_quartiles(binIndex, power, flag, reason, nBins, ...
        vMin, binWidth, iqrK, minCount, pRated, vCutIn, vRated, vCutOut);
    keep = strcmp(flag, flag_normal());
    nKeep = sum(keep);
    nNegative = sum(strcmp(flag, 'negative'));
    nShutdown = sum(strcmp(flag, 'shutdown'));
    nCurtail = sum(strcmp(flag, 'curtailment'));
    nOutlier = sum(strcmp(flag, 'outlier'));
    summary = sprintf(['wind-curve-binning-filter: rows=%d keep=%d ' ...
        'negative=%d shutdown=%d curtailment=%d outlier=%d ' ...
        'bin_width=%.4g p_rated_kw=%.6g'], ...
        n, nKeep, nNegative, nShutdown, nCurtail, nOutlier, binWidth, pRated);

    if ~isempty(outputCsv)
        write_points(outputCsv, wind, power, theory, binIndex, flag, reason, keep, vMin, binWidth);
    end
    if ~isempty(outputBins)
        write_bins(outputBins, bins);
    end
    fig = [];
    if ~isempty(outputPng) || showFig
        fig = render_figure(wind, power, keep, flag, bins, vMin, vCutIn, vRated, ...
            vCutOut, pRated, outputPng, showFig);
    end

    result = struct();
    result.wind_mps = wind;
    result.power_kw = power;
    result.theory_kw = theory;
    result.bin_index = binIndex;
    result.flag = flag;
    result.reason = reason;
    result.keep = keep;
    result.bins = bins;
    result.n_rows = n;
    result.n_keep = nKeep;
    result.n_negative = nNegative;
    result.n_shutdown = nShutdown;
    result.n_curtailment = nCurtail;
    result.n_outlier = nOutlier;
    result.n_missing = nMissing;
    result.bin_width = binWidth;
    result.v_min = vMin;
    result.v_cut_in = vCutIn;
    result.v_rated = vRated;
    result.v_cut_out = vCutOut;
    result.p_rated_kw = pRated;
    result.p_shutdown_kw = pShutdown;
    result.summary = summary;
    result.output_csv = outputCsv;
    result.output_bins_csv = outputBins;
    result.output_png = outputPng;
    result.fig = fig;
end

function [csvPath, windIn, powerIn, rest] = split_source(source, args)
    csvPath = '';
    windIn = [];
    powerIn = [];
    rest = args;
    if (isempty(source) || (ischar(source) && isempty(strtrim(source)))) && isempty(args)
        error('wind_curve_binning_filter:BadOption', ...
            'pass a CSV path or wind and power');
    end
    if isnumeric(source)
        if isempty(args) || ~isnumeric(args{1})
            error('wind_curve_binning_filter:BadOption', ...
                'pass a CSV path or wind and power');
        end
        windIn = source;
        powerIn = args{1};
        if numel(args) < 2
            rest = {};
        else
            rest = args(2:end);
        end
        return
    end
    if isstring(source)
        if ~isscalar(source)
            error('wind_curve_binning_filter:BadOption', ...
                'pass a CSV path or wind and power');
        end
        source = char(source);
    end
    if ischar(source) && (isrow(source) || isempty(source))
        csvPath = strtrim(source);
        if isempty(csvPath)
            error('wind_curve_binning_filter:BadOption', ...
                'pass a CSV path or wind and power');
        end
        return
    end
    error('wind_curve_binning_filter:BadOption', ...
        'pass a CSV path or wind and power');
end

function [flag, reason] = apply_rules(wind, power, theory, flag, reason, ...
        vCutIn, vCutOut, pRated, pShutdown, shutdownFrac, curtailRatio, curtailFrac)
    shutdownLevel = shutdownFrac * pRated;
    curtailLevel = curtailFrac * pRated;
    for i = 1:numel(wind)
        speed = wind(i);
        watts = power(i);
        expected = theory(i);
        if watts < 0 && speed >= vCutIn
            flag{i} = 'negative';
            reason{i} = 'negative';
        elseif watts <= pShutdown && expected >= shutdownLevel && ...
                speed >= vCutIn && speed < vCutOut
            flag{i} = 'shutdown';
            reason{i} = 'shutdown';
        elseif speed >= vCutIn && speed < vCutOut && expected >= curtailLevel && ...
                watts > pShutdown && watts < curtailRatio * expected
            flag{i} = 'curtailment';
            reason{i} = 'curtailment';
        elseif speed < vCutIn && watts > pShutdown
            flag{i} = 'outlier';
            reason{i} = 'below_cut_in';
        elseif speed >= vCutOut && watts > pShutdown
            flag{i} = 'outlier';
            reason{i} = 'above_cut_out';
        end
    end
end

function [flag, reason, bins] = apply_quartiles(binIndex, power, flag, reason, ...
        nBins, vMin, binWidth, iqrK, minCount, pRated, vCutIn, vRated, vCutOut)
    bins = repmat(empty_bin(), nBins, 1);
    for binId = 0:(nBins - 1)
        members = find(binIndex == binId);
        quartileIds = members(strcmp(flag(members), flag_normal()));
        sample = power(quartileIds);
        left = vMin + binId * binWidth;
        center = left + 0.5 * binWidth;
        if isempty(sample)
            medianKw = NaN;
            q1 = NaN;
            q3 = NaN;
            iqr = NaN;
            lower = NaN;
            upper = NaN;
            applied = false;
        else
            medianKw = empirical_quantile(sample, 0.5);
            q1 = empirical_quantile(sample, 0.25);
            q3 = empirical_quantile(sample, 0.75);
            iqr = q3 - q1;
            lower = q1 - iqrK * iqr;
            upper = q3 + iqrK * iqr;
            applied = numel(sample) >= minCount;
            if applied
                for k = 1:numel(quartileIds)
                    i = quartileIds(k);
                    if power(i) < lower || power(i) > upper
                        flag{i} = 'outlier';
                        reason{i} = 'iqr';
                    end
                end
            end
        end
        clean = [];
        for k = 1:numel(members)
            if strcmp(flag{members(k)}, flag_normal())
                clean(end + 1) = power(members(k)); %#ok<AGROW>
            end
        end
        row = empty_bin();
        row.bin_index = binId;
        row.v_left = left;
        row.v_right = left + binWidth;
        row.v_center = center;
        row.n_raw = numel(members);
        row.n_quartile = numel(quartileIds);
        row.n_clean = numel(clean);
        row.median_kw = medianKw;
        row.q1_kw = q1;
        row.q3_kw = q3;
        row.iqr_kw = iqr;
        row.lower_kw = lower;
        row.upper_kw = upper;
        row.fence_applied = applied;
        row.median_clean_kw = empirical_quantile(clean, 0.5);
        row.theory_kw = theoretical_power(center, pRated, vCutIn, vRated, vCutOut);
        bins(binId + 1) = row;
    end
end

function q = empirical_quantile(values, prob)
    x = sort(values(:));
    n = numel(x);
    if n == 0
        q = NaN;
        return
    end
    if n == 1
        q = x(1);
        return
    end
    h = (n - 1) * prob;
    lo = floor(h);
    hi = ceil(h);
    if hi == lo
        q = x(lo + 1);
    else
        frac = h - lo;
        q = x(lo + 1) * (1 - frac) + x(hi + 1) * frac;
    end
end

function power = theoretical_power(wind, pRated, vCutIn, vRated, vCutOut)
    wind = wind(:);
    power = zeros(size(wind));
    rising = wind >= vCutIn & wind < vRated;
    flat = wind >= vRated & wind < vCutOut;
    span = vRated ^ 3 - vCutIn ^ 3;
    power(rising) = pRated .* (wind(rising) .^ 3 - vCutIn ^ 3) ./ span;
    power(flat) = pRated;
end

function [wind, power, nMissing] = read_samples(path, windCol, powerCol)
    if exist(path, 'file') ~= 2
        error('wind_curve_binning_filter:MissingFile', ...
            'No such file: %s', path);
    end
    fid = fopen(path, 'r', 'n', 'UTF-8');
    if fid < 0
        error('wind_curve_binning_filter:MissingFile', ...
            'No such file: %s', path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    headerLine = fgetl(fid);
    if ~ischar(headerLine)
        error('wind_curve_binning_filter:BadOption', 'empty csv');
    end
    if ~isempty(headerLine) && double(headerLine(1)) == 65279
        headerLine = headerLine(2:end);
    end
    delimiter = ',';
    if numel(strfind(headerLine, ';')) > numel(strfind(headerLine, ',')) %#ok<STRIFCND>
        delimiter = ';';
    end
    headers = split_line(headerLine, delimiter);
    windIdx = pick_column(headers, windCol, wind_aliases(), 'wind');
    powerIdx = pick_column(headers, powerCol, power_aliases(), 'power');
    wind = zeros(0, 1);
    power = zeros(0, 1);
    nMissing = 0;
    lineNumber = 1;
    while true
        line = fgetl(fid);
        if ~ischar(line)
            break
        end
        lineNumber = lineNumber + 1;
        if isempty(strtrim(line))
            continue
        end
        cells = split_line(line, delimiter);
        windText = '';
        powerText = '';
        if windIdx <= numel(cells)
            windText = strtrim(cells{windIdx});
        end
        if powerIdx <= numel(cells)
            powerText = strtrim(cells{powerIdx});
        end
        if isempty(windText) && isempty(powerText)
            continue
        end
        if isempty(windText) || isempty(powerText)
            nMissing = nMissing + 1;
            continue
        end
        speed = str2double(windText);
        watts = str2double(powerText);
        if ~isfinite(speed) || ~isfinite(watts)
            error('wind_curve_binning_filter:BadOption', ...
                'row %d is not a finite wind_mps, power_kw pair', lineNumber);
        end
        wind(end + 1, 1) = speed; %#ok<AGROW>
        power(end + 1, 1) = watts; %#ok<AGROW>
    end
    if isempty(wind)
        error('wind_curve_binning_filter:BadOption', ...
            'need at least one finite sample');
    end
end

function cells = split_line(line, delimiter)
    cells = strsplit(line, delimiter, 'CollapseDelimiters', false);
    if ~iscell(cells)
        cells = {cells};
    end
end

function idx = pick_column(headers, requested, aliases, kind)
    if ~isempty(requested)
        for i = 1:numel(headers)
            if strcmp(strtrim(headers{i}), requested)
                idx = i;
                return
            end
        end
        error('wind_curve_binning_filter:BadOption', ...
            '%s column ''%s'' not found', kind, requested);
    end
    for i = 1:numel(headers)
        name = lower(strtrim(headers{i}));
        for a = 1:numel(aliases)
            if strcmp(name, lower(aliases{a}))
                idx = i;
                return
            end
        end
    end
    error('wind_curve_binning_filter:BadOption', '%s column not found', kind);
end

function names = wind_aliases()
    names = {'wind_mps', 'wind_speed_mps', 'wind_speed', 'wind', 'v_mps', 'v', '风速'};
end

function names = power_aliases()
    names = {'power_kw', 'p_kw', 'active_power_kw', 'active_power', ...
        'power', 'p', '功率kw', '功率', '有功功率', '有功'};
end

function write_points(path, wind, power, theory, binIndex, flag, reason, keep, vMin, binWidth)
    ensure_parent(path);
    fid = fopen(path, 'w', 'n', 'UTF-8');
    if fid < 0
        error('wind_curve_binning_filter:Write', 'could not write %s', path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, 'wind_mps,power_kw,theory_kw,bin_index,v_left,flag,reason,keep\n');
    for i = 1:numel(wind)
        left = vMin + binIndex(i) * binWidth;
        fprintf(fid, '%s,%s,%s,%d,%s,%s,%s,%d\n', ...
            num_str(wind(i)), num_str(power(i)), num_str(theory(i)), ...
            binIndex(i), num_str(left), flag{i}, reason{i}, keep(i));
    end
end

function write_bins(path, bins)
    ensure_parent(path);
    fid = fopen(path, 'w', 'n', 'UTF-8');
    if fid < 0
        error('wind_curve_binning_filter:Write', 'could not write %s', path);
    end
    cleaner = onCleanup(@() fclose(fid)); %#ok<NASGU>
    fprintf(fid, ['bin_index,v_left,v_right,v_center,n_raw,n_quartile,n_clean,' ...
        'median_kw,q1_kw,q3_kw,iqr_kw,lower_kw,upper_kw,fence_applied,' ...
        'median_clean_kw,theory_kw\n']);
    for i = 1:numel(bins)
        row = bins(i);
        fprintf(fid, '%d,%s,%s,%s,%d,%d,%d,%s,%s,%s,%s,%s,%s,%d,%s,%s\n', ...
            row.bin_index, num_str(row.v_left), num_str(row.v_right), num_str(row.v_center), ...
            row.n_raw, row.n_quartile, row.n_clean, num_str(row.median_kw), ...
            num_str(row.q1_kw), num_str(row.q3_kw), num_str(row.iqr_kw), ...
            num_str(row.lower_kw), num_str(row.upper_kw), row.fence_applied, ...
            num_str(row.median_clean_kw), num_str(row.theory_kw));
    end
end

function text = num_str(value)
    if isempty(value) || ~isscalar(value) || isnan(value)
        text = 'nan';
    else
        text = sprintf('%.16g', value);
    end
end

function ensure_parent(path)
    folder = fileparts(path);
    if ~isempty(folder) && exist(folder, 'dir') ~= 7
        mkdir(folder);
    end
end

function fig = render_figure(wind, power, keep, flag, bins, vMin, vCutIn, vRated, ...
        vCutOut, pRated, outputPng, showFig)
    fig = figure('Visible', 'off', 'Color', 'w', 'Position', [80 80 1020 440]);
    ax1 = subplot(1, 2, 1);
    ax2 = subplot(1, 2, 2);
    hold(ax1, 'on');
    hold(ax2, 'on');
    names = {'normal', 'shutdown', 'curtailment', 'negative', 'outlier'};
    for k = 1:numel(names)
        mask = strcmp(flag, names{k});
        if ~any(mask)
            continue
        end
        scatter(ax1, wind(mask), power(mask), 12, flag_color(names{k}), ...
            'filled', 'MarkerFaceAlpha', 0.75, 'DisplayName', names{k});
    end
    plot_theory(ax1, wind, vMin, vCutOut, pRated, vCutIn, vRated);
    scatter(ax2, wind(keep), power(keep), 12, flag_color('normal'), ...
        'filled', 'MarkerFaceAlpha', 0.75, 'DisplayName', 'kept');
    plot_bins(ax2, bins);
    plot_theory(ax2, wind, vMin, vCutOut, pRated, vCutIn, vRated);
    title(ax1, 'Before cleaning', 'Interpreter', 'none');
    title(ax2, 'After cleaning', 'Interpreter', 'none');
    xlabel(ax1, 'Wind speed (m/s)');
    xlabel(ax2, 'Wind speed (m/s)');
    ylabel(ax1, 'Power (kW)');
    grid(ax1, 'on');
    grid(ax2, 'on');
    legend(ax1, 'Location', 'northwest', 'FontSize', 8, 'Box', 'off');
    legend(ax2, 'Location', 'northwest', 'FontSize', 8, 'Box', 'off');
    linkaxes([ax1, ax2], 'xy');
    if ~isempty(outputPng)
        ensure_parent(outputPng);
        print(fig, outputPng, '-dpng', '-r120');
    end
    if showFig
        set(fig, 'Visible', 'on');
    else
        close(fig);
        fig = [];
    end
end

function plot_theory(ax, wind, vMin, vCutOut, pRated, vCutIn, vRated)
    right = max(vCutOut, max(wind));
    gridV = linspace(vMin, right, 400).';
    curve = theoretical_power(gridV, pRated, vCutIn, vRated, vCutOut);
    plot(ax, gridV, curve, 'k-', 'LineWidth', 1.2, 'DisplayName', 'theoretical');
end

function plot_bins(ax, bins)
    labeledBand = false;
    labeledMedian = false;
    band = [242, 193, 78] / 255;
    for i = 1:numel(bins)
        row = bins(i);
        if row.n_quartile == 0 || isnan(row.q1_kw)
            continue
        end
        if labeledBand
            visibility = 'off';
        else
            visibility = 'on';
        end
        fill(ax, [row.v_left, row.v_right, row.v_right, row.v_left], ...
            [row.q1_kw, row.q1_kw, row.q3_kw, row.q3_kw], band, ...
            'FaceAlpha', 0.35, 'EdgeColor', 'none', ...
            'HandleVisibility', visibility, 'DisplayName', 'Q1-Q3');
        labeledBand = true;
        if row.fence_applied && ~isnan(row.lower_kw)
            plot(ax, [row.v_left, row.v_right], [row.lower_kw, row.lower_kw], ...
                '--', 'Color', band, 'LineWidth', 0.6, 'HandleVisibility', 'off');
            plot(ax, [row.v_left, row.v_right], [row.upper_kw, row.upper_kw], ...
                '--', 'Color', band, 'LineWidth', 0.6, 'HandleVisibility', 'off');
        end
        if ~isnan(row.median_clean_kw)
            if labeledMedian
                visibility = 'off';
            else
                visibility = 'on';
            end
            plot(ax, [row.v_left, row.v_right], ...
                [row.median_clean_kw, row.median_clean_kw], '-', ...
                'Color', [228, 87, 86] / 255, 'LineWidth', 1.6, ...
                'HandleVisibility', visibility, 'DisplayName', 'bin median');
            labeledMedian = true;
        end
    end
end

function rgb = flag_color(name)
    switch name
        case 'normal'
            rgb = [76, 120, 168] / 255;
        case 'negative'
            rgb = [178, 121, 162] / 255;
        case 'shutdown'
            rgb = [127, 127, 127] / 255;
        case 'curtailment'
            rgb = [245, 133, 24] / 255;
        case 'outlier'
            rgb = [228, 87, 86] / 255;
        otherwise
            rgb = [0, 0, 0];
    end
end

function row = empty_bin()
    row = struct( ...
        'bin_index', 0, 'v_left', NaN, 'v_right', NaN, 'v_center', NaN, ...
        'n_raw', 0, 'n_quartile', 0, 'n_clean', 0, ...
        'median_kw', NaN, 'q1_kw', NaN, 'q3_kw', NaN, 'iqr_kw', NaN, ...
        'lower_kw', NaN, 'upper_kw', NaN, 'fence_applied', false, ...
        'median_clean_kw', NaN, 'theory_kw', NaN);
end

function name = flag_normal()
    name = 'normal';
end

function tf = is_text_scalar(value)
    tf = (ischar(value) && (isrow(value) || isempty(value))) || ...
        (isstring(value) && isscalar(value));
end

function value = finite_number(name, raw)
    if ~(isnumeric(raw) && isscalar(raw) && isreal(raw) && isfinite(raw))
        error('wind_curve_binning_filter:BadOption', ...
            '%s must be a finite number', name);
    end
    value = double(raw);
end

function value = positive_number(name, raw)
    value = finite_number(name, raw);
    if value <= 0
        error('wind_curve_binning_filter:BadOption', '%s must be positive', name);
    end
end

function value = nonnegative_number(name, raw)
    value = finite_number(name, raw);
    if value < 0
        error('wind_curve_binning_filter:BadOption', '%s must be >= 0', name);
    end
end

function value = fraction_closed(name, raw)
    value = finite_number(name, raw);
    if value < 0 || value > 1
        error('wind_curve_binning_filter:BadOption', '%s must be in [0, 1]', name);
    end
end

function value = fraction_open(name, raw)
    value = finite_number(name, raw);
    if value <= 0 || value >= 1
        error('wind_curve_binning_filter:BadOption', '%s must be in (0, 1)', name);
    end
end

function value = positive_int(name, raw)
    value = finite_number(name, raw);
    if value < 1 || abs(value - round(value)) > 0
        error('wind_curve_binning_filter:BadOption', ...
            '%s must be an integer >= 1', name);
    end
    value = round(value);
end

function tf = as_bool(name, raw)
    if islogical(raw) && isscalar(raw)
        tf = raw;
        return
    end
    if isnumeric(raw) && isscalar(raw) && isreal(raw) && (raw == 0 || raw == 1)
        tf = logical(raw);
        return
    end
    error('wind_curve_binning_filter:BadOption', '%s must be true or false', name);
end
