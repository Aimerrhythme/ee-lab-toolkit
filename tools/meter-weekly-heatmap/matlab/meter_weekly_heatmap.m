function res = meter_weekly_heatmap(csvPath, varargin)
%METER_WEEKLY_HEATMAP Fold daily meter kWh into week x weekday matrices.
%   res = meter_weekly_heatmap(csvPath, 'max_gap', 3, 'output_dir', dir, ...
%         'output_png', file, 'show', false)
%   Same semantics as python/meter_weekly_heatmap.py. CSV columns:
%   customer_id,label,date,kwh. Blank/NaN/negative kWh = missing; duplicate
%   dates keep the first row. Interior gaps <= max_gap days are linearly
%   interpolated (status 'filled'); other gaps stay NaN. Min-max per customer.
%   Weekday index 0 = Monday. Base MATLAB only (no toolboxes).
%   res.start_ordinal, res.n_weeks, res.customers(k).{customer_id,label,kwh,
%   norm,status,n_observed,n_filled,n_missing,missing_rate,weekend_ratio}.

    p = inputParser;
    addParameter(p, 'max_gap', 3);
    addParameter(p, 'output_dir', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;

    % ---- read ----
    fid = fopen(csvPath, 'r');
    if fid < 0, error('meter_weekly_heatmap:open', 'cannot open %s', csvPath); end
    cleaner = onCleanup(@() fclose(fid));
    fgetl(fid);  % header
    ids = {}; labels = {}; ords = []; vals = []; ridx = [];
    while true
        ln = fgetl(fid);
        if ~ischar(ln), break; end
        ln = strtrim(ln);
        if isempty(ln), continue; end
        f = strsplit(ln, ',', 'CollapseDelimiters', false);
        cid = strtrim(f{1});
        k = find(strcmp(ids, cid), 1);
        if isempty(k)
            ids{end+1} = cid; labels{end+1} = strtrim(f{2}); k = numel(ids); %#ok<AGROW>
        end
        v = str2double(strtrim(f{4}));   % '' and 'NaN' -> NaN
        if isnan(v) || v < 0, v = NaN; end
        ridx(end+1) = k; %#ok<AGROW>
        ords(end+1) = datenum(strtrim(f{3}), 'yyyy-mm-dd') - 366; %#ok<AGROW> python toordinal
        vals(end+1) = v; %#ok<AGROW>
    end

    first = min(ords); last = max(ords);
    startOrd = first - mod(first - 1, 7);
    endOrd = last + (6 - mod(last - 1, 7));
    nDays = endOrd - startOrd + 1;
    nWeeks = nDays / 7;
    res.start_ordinal = startOrd;
    res.n_weeks = nWeeks;
    wk = mod(0:nDays-1, 7);

    for k = 1:numel(ids)
        sel = find(ridx == k);
        raw = nan(1, nDays);
        seen = false(1, nDays);
        for s = sel
            pos = ords(s) - startOrd + 1;
            if ~seen(pos), raw(pos) = vals(s); seen(pos) = true; end
        end
        spanLo = min(ords(sel)) - startOrd + 1;
        spanHi = max(ords(sel)) - startOrd + 1;
        missInSpan = sum(isnan(raw(spanLo:spanHi)));
        [filledVals, fmask] = fill_gaps_(raw, o.max_gap);
        ok = ~isnan(filledVals);
        status = repmat({'missing'}, 1, nDays);
        status(ok) = {'observed'};
        status(fmask) = {'filled'};
        nrm = nan(1, nDays);
        if any(ok)
            lo = min(filledVals(ok)); hi = max(filledVals(ok));
            if hi == lo, nrm(ok) = 0; else, nrm(ok) = (filledVals(ok) - lo) / (hi - lo); end
        end
        wd = filledVals(ok & wk < 5); we = filledVals(ok & wk >= 5);
        if ~isempty(wd) && ~isempty(we) && mean(wd) > 0
            ratio = mean(we) / mean(wd);
        else
            ratio = NaN;
        end
        c.customer_id = ids{k};
        c.label = labels{k};
        c.kwh = reshape(filledVals, 7, nWeeks)';
        c.norm = reshape(nrm, 7, nWeeks)';
        c.status = status;
        c.n_observed = sum(strcmp(status, 'observed'));
        c.n_filled = sum(strcmp(status, 'filled'));
        c.n_missing = sum(strcmp(status, 'missing'));
        c.missing_rate = missInSpan / (spanHi - spanLo + 1);
        c.weekend_ratio = ratio;
        cs(k) = c; %#ok<AGROW>
    end
    res.customers = cs;

    if ~isempty(o.output_dir), write_outputs_(res, o.output_dir); end
    if ~isempty(o.output_png) || o.show, plot_(res, o.output_png, o.show); end
end

function [out, filled] = fill_gaps_(v, maxGap)
    out = v; filled = false(size(v)); n = numel(v); i = 1;
    while i <= n
        if isnan(v(i))
            j = i;
            while j <= n && isnan(v(j)), j = j + 1; end
            if i > 1 && j <= n && (j - i) <= maxGap
                a = v(i-1); b = v(j);
                for k = i:j-1
                    out(k) = a + (b - a) * (k - i + 1) / (j - i + 1);
                    filled(k) = true;
                end
            end
            i = j;
        else
            i = i + 1;
        end
    end
end

function write_outputs_(res, outDir)
    if ~exist(outDir, 'dir'), mkdir(outDir); end
    fid = fopen(fullfile(outDir, 'matrix_long.csv'), 'w');
    fprintf(fid, 'customer_id,label,week,weekday,date,kwh,norm,status\n');
    for c = res.customers
        kw = c.kwh'; nm = c.norm';   % row-major day order
        for k = 1:res.n_weeks * 7
            d = datestr(res.start_ordinal + k - 1 + 366, 'yyyy-mm-dd');
            fprintf(fid, '%s,%s,%d,%d,%s,%s,%s,%s\n', c.customer_id, c.label, ...
                floor((k-1)/7), mod(k-1, 7), d, numstr_(kw(k)), numstr_(nm(k)), c.status{k});
        end
    end
    fclose(fid);
    fid = fopen(fullfile(outDir, 'summary.csv'), 'w');
    fprintf(fid, 'customer_id,label,n_observed,n_filled,n_missing,missing_rate,weekend_ratio\n');
    for c = res.customers
        fprintf(fid, '%s,%s,%d,%d,%d,%.4f,%.4f\n', c.customer_id, c.label, c.n_observed, ...
            c.n_filled, c.n_missing, c.missing_rate, c.weekend_ratio);
    end
    fclose(fid);
end

function s = numstr_(x)
    if isnan(x), s = ''; else, s = sprintf('%.4f', x); end
end

function plot_(res, png, show)
    n = numel(res.customers);
    if show, vis = 'on'; else, vis = 'off'; end
    fig = figure('Visible', vis, 'Position', [100 100 260*n+100 420]);
    for k = 1:n
        c = res.customers(k);
        subplot(1, n, k);
        imagesc(c.norm, 'AlphaData', ~isnan(c.norm), [0 1]);
        set(gca, 'Color', [0.83 0.83 0.83], 'XTick', 1:7, 'XTickLabel', {'M','T','W','T','F','S','S'});
        title(sprintf('%s (%s)', c.customer_id, c.label));
        ylabel('week');
    end
    colorbar;
    if ~isempty(png)
        d = fileparts(png);
        if ~isempty(d) && ~exist(d, 'dir'), mkdir(d); end
        saveas(fig, png);
    end
    if ~show, close(fig); end
end
