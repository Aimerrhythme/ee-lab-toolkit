function result = epf_lear_feature_builder(csvPath, varargin)
%EPF_LEAR_FEATURE_BUILDER Build the LEAR input matrix (one row per target day).
%   result = epf_lear_feature_builder(csvPath, 'lags', [1 2 3 7], ...
%       'output_csv', '', 'output_png', '', 'show', false)
%   CSV columns: date,hour,price[,load_forecast]. Row = [price lags | load
%   forecast of target day | Mon..Sun one-hot]; y = price of target day.
    p = inputParser;
    addParameter(p, 'lags', [1 2 3 7]);
    addParameter(p, 'output_csv', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    lags = p.Results.lags(:)';
    if isempty(lags) || min(lags) < 1
        error('lags must be positive integers');
    end
    fid = fopen(csvPath, 'r');
    hdr = strtrim(fgetl(fid));
    cols = strsplit(hdr, ',');
    hasLoad = any(strcmp(cols, 'load_forecast'));
    fmt = '%s %f %f';
    if hasLoad, fmt = [fmt ' %f']; end
    C = textscan(fid, fmt, 'Delimiter', ',');
    fclose(fid);
    dates = strtrim(C{1}); hours = C{2}; price = C{3};
    n = numel(price);
    if n == 0 || mod(n, 24) ~= 0
        error('row count must be a positive multiple of 24');
    end
    if any(hours ~= mod((0:n-1)', 24))
        error('hours must run 0..23 consecutively in every day');
    end
    if any(~isfinite(price))
        error('prices must be finite');
    end
    P = reshape(price, 24, [])';
    ex = [];
    if hasLoad
        if any(~isfinite(C{4})), error('load_forecast must be finite'); end
        ex = reshape(C{4}, 24, [])';
    end
    days = dates(1:24:end);
    nd = size(P, 1);
    first = max(lags);
    if nd <= first
        error('need more days than the largest lag');
    end
    nt = nd - first;
    X = [];
    for d = first+1:nd   % 1-based day index
        parts = [];
        for L = lags
            parts = [parts, P(d-L, :)]; %#ok<AGROW>
        end
        if hasLoad, parts = [parts, ex(d, :)]; end %#ok<AGROW>
        dow = zeros(1, 7);
        wd = weekday(datenum(days{d}, 'yyyy-mm-dd')); % 1=Sun..7=Sat
        dow(mod(wd + 5, 7) + 1) = 1;                  % Mon=1..Sun=7
        X = [X; parts, dow]; %#ok<AGROW>
    end
    y = P(first+1:end, :);
    names = {};
    for L = lags
        for h = 0:23, names{end+1} = sprintf('price_D-%d_h%02d', L, h); end %#ok<AGROW>
    end
    if hasLoad
        for h = 0:23, names{end+1} = sprintf('load_fc_D_h%02d', h); end %#ok<AGROW>
    end
    dn = {'Mon','Tue','Wed','Thu','Fri','Sat','Sun'};
    for k = 1:7, names{end+1} = ['dow_' dn{k}]; end %#ok<AGROW>
    result = struct('X', X, 'y', y, 'names', {names}, 'target_dates', {days(first+1:end)}, ...
        'lags', lags, 'n_rows', size(X, 1), 'n_features', size(X, 2));
    if ~isempty(p.Results.output_csv)
        od = fileparts(p.Results.output_csv);
        if ~isempty(od) && ~exist(od, 'dir'), mkdir(od); end
        f = fopen(p.Results.output_csv, 'w');
        yn = arrayfun(@(h) sprintf('y_h%02d', h), 0:23, 'UniformOutput', false);
        fprintf(f, '%s\n', strjoin([{'date'}, names, yn], ','));
        for i = 1:nt
            fprintf(f, '%s', result.target_dates{i});
            fprintf(f, ',%.4f', X(i, :), y(i, :));
            fprintf(f, '\n');
        end
        fclose(f);
    end
    if ~isempty(p.Results.output_png)
        op = fileparts(p.Results.output_png);
        if ~isempty(op) && ~exist(op, 'dir'), mkdir(op); end
        vis = 'off'; if p.Results.show, vis = 'on'; end
        fig = figure('Visible', vis, 'Position', [100 100 1000 380]);
        subplot(1, 4, 1:3); imagesc(X'); colorbar;
        xlabel('target day index'); ylabel('feature column'); title('LEAR feature matrix (transposed)');
        subplot(1, 4, 4); bar(sum(X(:, end-6:end), 1)); set(gca, 'XTickLabel', {'M','T','W','T','F','S','S'});
        title('rows per weekday');
        saveas(fig, p.Results.output_png);
        if ~p.Results.show, close(fig); end
    end
end
