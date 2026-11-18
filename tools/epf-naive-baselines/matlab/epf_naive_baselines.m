function result = epf_naive_baselines(csvPath, varargin)
%EPF_NAIVE_BASELINES Previous-day and previous-week naive price forecasts.
%   result = epf_naive_baselines(csvPath, 'eval_start_day', 7, ...
%       'output_csv', '', 'output_png', '', 'show', false)
%   CSV columns: date,hour,price (hour 0..23, whole consecutive days).
%   Day index is 0-based as in Python: eval days are eval_start_day..n_days-1.
%   result.metrics.naive_prev_day / naive_prev_week have .mae .smape_pct .rmse
%   sMAPE in percent, 0/0 counts as 0. Base MATLAB only.
    p = inputParser;
    addParameter(p, 'eval_start_day', 7);
    addParameter(p, 'output_csv', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;

    fid = fopen(csvPath, 'r');
    if fid < 0, error('epf:file', 'cannot open %s', csvPath); end
    c = onCleanup(@() fclose(fid));
    t = textscan(fid, '%s %f %f', 'Delimiter', ',', 'HeaderLines', 1);
    dates = strtrim(t{1}); hours = t{2}; prices = t{3};
    n = numel(prices);
    if n == 0 || mod(n, 24) ~= 0 || numel(hours) ~= n
        error('epf:rows', 'row count must be a positive multiple of 24');
    end
    if any(hours(:) ~= mod((0:n-1)', 24))
        error('epf:hours', 'hours must run 0..23 consecutively in every day');
    end
    if any(~isfinite(prices))
        error('epf:nan', 'prices must be finite (no blank/NaN)');
    end
    P = reshape(prices, 24, []).';     % n_days x 24
    dayDates = dates(1:24:end);
    nDays = size(P, 1);
    s0 = o.eval_start_day;
    if s0 < 7, error('epf:start', 'eval_start_day must be >= 7'); end
    if s0 >= nDays, error('epf:start', 'eval_start_day must be < number of days'); end

    idx = (s0:nDays-1) + 1;            % MATLAB 1-based rows
    actual = P(idx, :);
    models = {'naive_prev_day', 'naive_prev_week'};
    lags = [1 7];
    result.metrics = struct();
    result.forecasts = struct();
    result.hourly_mae = struct();
    for k = 1:2
        f = P(idx - lags(k), :);
        result.forecasts.(models{k}) = f;
        e = actual - f;
        den = (abs(actual) + abs(f)) / 2;
        ratio = zeros(size(e));
        nz = den ~= 0;
        ratio(nz) = abs(e(nz)) ./ den(nz);
        result.metrics.(models{k}) = struct('mae', mean(abs(e(:))), ...
            'smape_pct', mean(ratio(:)) * 100, 'rmse', sqrt(mean(e(:).^2)));
        result.hourly_mae.(models{k}) = mean(abs(e), 1);
    end
    result.dates = dayDates(idx);
    result.actual = actual;
    result.n_eval_days = numel(idx);
    result.models = models;

    if ~isempty(o.output_csv)
        ensure_dir(o.output_csv);
        fo = fopen(o.output_csv, 'w');
        fprintf(fo, 'date,hour,actual,naive_prev_day,naive_prev_week\n');
        for i = 1:numel(idx)
            for h = 1:24
                fprintf(fo, '%s,%d,%.4f,%.4f,%.4f\n', result.dates{i}, h-1, ...
                    actual(i,h), result.forecasts.naive_prev_day(i,h), ...
                    result.forecasts.naive_prev_week(i,h));
            end
        end
        fclose(fo);
    end
    if ~isempty(o.output_png) || o.show
        vis = 'off'; if o.show, vis = 'on'; end
        fig = figure('Visible', vis, 'Position', [100 100 1100 400]);
        a = actual.'; a = a(:);
        k = min(numel(a), 24*7);
        subplot(1, 2, 1); hold on;
        plot(0:k-1, a(1:k), 'k', 'LineWidth', 1.5);
        for m = 1:2
            fm = result.forecasts.(models{m}).'; fm = fm(:);
            plot(0:k-1, fm(1:k), 'LineWidth', 1);
        end
        xlabel('hour (first 7 evaluated days)'); ylabel('price');
        legend(['actual', models], 'Interpreter', 'none');
        subplot(1, 2, 2); hold on;
        for m = 1:2
            plot(0:23, result.hourly_mae.(models{m}), '-o');
        end
        xlabel('hour of day'); ylabel('MAE');
        legend(models, 'Interpreter', 'none');
        if ~isempty(o.output_png)
            ensure_dir(o.output_png);
            saveas(fig, o.output_png);
        end
        if ~o.show, close(fig); end
    end
end

function ensure_dir(f)
    d = fileparts(f);
    if ~isempty(d) && exist(d, 'dir') ~= 7, mkdir(d); end
end
