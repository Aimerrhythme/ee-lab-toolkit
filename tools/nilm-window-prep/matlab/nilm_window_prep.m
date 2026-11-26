function res = nilm_window_prep(csvPath, varargin)
%NILM_WINDOW_PREP Align, resample, fill short gaps and cut seq2point windows.
%   res = nilm_window_prep(csvPath, 'step_s', 6, 'max_gap_steps', 3, ...
%       'window', 11, 'stride', 1, 'output_csv', '', 'output_png', '', 'show', false)
%   Input CSV: timestamp_s,aggregate_w,appliance_w. Same semantics as the Python
%   version: bin mean on [t0+k*step, t0+(k+1)*step), linear fill of interior NaN
%   runs <= max_gap_steps, window kept only if all aggregate samples and the
%   midpoint appliance value are finite. res.starts is 0-based like Python.
    p = inputParser;
    addParameter(p, 'step_s', 6);
    addParameter(p, 'max_gap_steps', 3);
    addParameter(p, 'window', 11);
    addParameter(p, 'stride', 1);
    addParameter(p, 'output_csv', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;
    if o.window < 1 || mod(o.window, 2) == 0
        error('nilm:window', 'window must be a positive odd integer');
    end
    if o.step_s <= 0 || o.stride < 1 || o.max_gap_steps < 0
        error('nilm:args', 'step_s > 0, stride >= 1, max_gap_steps >= 0 required');
    end
    fid = fopen(csvPath, 'r');
    if fid < 0, error('nilm:file', 'cannot open %s', csvPath); end
    c = onCleanup(@() fclose(fid));
    d = textscan(fid, '%f %f %f', 'Delimiter', ',', 'HeaderLines', 1);
    t = d{1}; a = d{2}; b = d{3};
    if isempty(t), error('nilm:empty', 'empty input'); end
    if any(diff(t) <= 0), error('nilm:order', 'timestamps must be strictly increasing'); end
    t0 = t(1);
    nBins = floor((t(end) - t0) / o.step_s) + 1;
    agg = bin_mean(t, a, t0, o.step_s, nBins);
    app = bin_mean(t, b, t0, o.step_s, nBins);
    nEmpty = sum(isnan(agg));
    [agg, f1] = fill_short_gaps(agg, o.max_gap_steps);
    [app, f2] = fill_short_gaps(app, o.max_gap_steps);
    W = o.window; half = floor(W / 2);
    startsAll = 0:o.stride:(nBins - W);
    keep = false(size(startsAll));
    for i = 1:numel(startsAll)
        s = startsAll(i) + 1;            % 1-based
        keep(i) = all(isfinite(agg(s:s+W-1))) && isfinite(app(s+half));
    end
    starts = startsAll(keep);
    n = numel(starts);
    X = zeros(n, W); y = zeros(n, 1);
    for i = 1:n
        s = starts(i) + 1;
        X(i, :) = agg(s:s+W-1).';
        y(i) = app(s+half);
    end
    tMid = t0 + (starts(:) + half + 0.5) * o.step_s;
    res = struct('X', X, 'y', y, 'starts', starts(:), 't_mid', tMid, 'agg', agg, ...
        'app', app, 'n_bins', nBins, 'n_empty_bins', nEmpty, 'n_filled', f1 + f2, ...
        'n_candidates', numel(startsAll), 'n_windows', n, ...
        'n_dropped', numel(startsAll) - n, 'window', W, 'step_s', o.step_s);

    if ~isempty(o.output_csv)
        ensure_dir(o.output_csv);
        fo = fopen(o.output_csv, 'w');
        hdr = sprintf(',x%d', 0:W-1);
        fprintf(fo, 'start_bin,t_mid_s,y_w%s\n', hdr);
        for i = 1:n
            fprintf(fo, '%d,%.1f,%.3f', starts(i), tMid(i), y(i));
            fprintf(fo, ',%.3f', X(i, :));
            fprintf(fo, '\n');
        end
        fclose(fo);
    end
    if ~isempty(o.output_png) || o.show
        vis = 'off'; if o.show, vis = 'on'; end
        fig = figure('Visible', vis, 'Position', [100 100 1000 600]);
        subplot(2, 1, 1); hold on;
        plot(0:nBins-1, agg, 'LineWidth', 1);
        plot(0:nBins-1, app, 'LineWidth', 1);
        gi = find(isnan(agg)) - 1;
        for k = 1:numel(gi)
            patch([gi(k)-.5 gi(k)+.5 gi(k)+.5 gi(k)-.5], [0 0 1 1] * max(agg(isfinite(agg))), ...
                'r', 'FaceAlpha', 0.2, 'EdgeColor', 'none');
        end
        xlabel('bin'); ylabel('W'); legend('aggregate', 'appliance');
        title('resampled series (red = unfilled gap)');
        subplot(2, 1, 2); hold on;
        if n > 0
            for i = round(linspace(1, n, min(4, n)))
                plot(0:W-1, X(i, :), 'LineWidth', 1);
                plot(half, y(i), 'ko');
            end
        end
        xlabel('position in window'); ylabel('W');
        title('sample windows (dot = midpoint appliance target)');
        if ~isempty(o.output_png)
            ensure_dir(o.output_png);
            saveas(fig, o.output_png);
        end
        if ~o.show, close(fig); end
    end
end

function out = bin_mean(t, v, t0, step, nBins)
    k = floor((t - t0) / step) + 1;      % 1-based bin
    ok = isfinite(v) & k >= 1 & k <= nBins;
    cnt = accumarray(k(ok), 1, [nBins 1]);
    sm = accumarray(k(ok), v(ok), [nBins 1]);
    out = nan(nBins, 1);
    nz = cnt > 0;
    out(nz) = sm(nz) ./ cnt(nz);
end

function [x, filled] = fill_short_gaps(x, maxGap)
    n = numel(x); i = 1; filled = 0;
    while i <= n
        if isnan(x(i))
            j = i;
            while j <= n && isnan(x(j)), j = j + 1; end
            if i > 1 && j <= n && (j - i) <= maxGap
                x(i:j-1) = interp1([i-1 j], [x(i-1) x(j)], i:j-1);
                filled = filled + (j - i);
            end
            i = j;
        else
            i = i + 1;
        end
    end
end

function ensure_dir(f)
    d = fileparts(f);
    if ~isempty(d) && exist(d, 'dir') ~= 7, mkdir(d); end
end
