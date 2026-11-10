function result = pmu_iforest(source, varargin)
%PMU_IFOREST Isolation Forest (from scratch, base MATLAB) for PMU phasor glitch detection.
%   result = pmu_iforest('synthetic_pmu.csv', 'contamination', 0.03)
%   result = pmu_iforest({t, v_mag_pu, v_angle_deg, freq_hz})
%   Name-value: n_trees (100), max_samples (256), contamination (0.02), f_nom (50),
%   seed (0), output_csv, output_png, show (false).
%   Fields: time_s, features, feature_names, scores, threshold, flags,
%   anomaly_times, precision, recall, summary. Random draws differ from NumPy, so
%   scores are close but not identical to the Python tool.

    p = inputParser;
    addParameter(p, 'n_trees', 100);
    addParameter(p, 'max_samples', 256);
    addParameter(p, 'contamination', 0.02);
    addParameter(p, 'f_nom', 50);
    addParameter(p, 'seed', 0);
    addParameter(p, 'output_csv', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;

    truth = [];
    if ischar(source) || isstring(source)
        tbl = readtable(char(source));
        t = tbl.time_s; mag = tbl.v_mag_pu; ang = tbl.v_angle_deg; fr = tbl.freq_hz;
        if ismember('true_anomaly', tbl.Properties.VariableNames)
            truth = tbl.true_anomaly;
        end
    else
        t = source{1}(:); mag = source{2}(:); ang = source{3}(:); fr = source{4}(:);
    end
    if ~(o.contamination > 0 && o.contamination < 0.5)
        error('pmu_iforest:contamination', 'contamination must be in (0, 0.5)');
    end
    n = numel(t);
    if n < 16
        error('pmu_iforest:size', 'need at least 16 frames');
    end

    angu = rad2deg(unwrap(deg2rad(ang)));
    X = [mag, [0; diff(mag)], [0; diff(angu)], fr - o.f_nom];
    names = {'v_mag_pu', 'd_mag_pu', 'd_angle_deg', 'df_hz'};
    med = median(X, 1);
    mad = median(abs(X - med), 1);
    mad(mad == 0) = 1;
    Z = (X - med) ./ mad;

    psi = min(o.max_samples, n);
    limit = ceil(log2(psi));
    rng(o.seed);
    trees = cell(o.n_trees, 1);
    for k = 1:o.n_trees
        idx = randperm(n, psi);
        trees{k} = grow(Z(idx, :), 0, limit);
    end
    meanPath = zeros(n, 1);
    for i = 1:n
        s = 0;
        for k = 1:o.n_trees
            s = s + tree_path(trees{k}, Z(i, :));
        end
        meanPath(i) = s / o.n_trees;
    end
    scores = 2 .^ (-meanPath / c_factor(psi));
    threshold = quantile_linear(sort(scores), 1 - o.contamination);
    flags = scores >= threshold;

    result = struct('time_s', t, 'features', X, 'feature_names', {names}, ...
        'scores', scores, 'threshold', threshold, 'flags', flags, ...
        'anomaly_times', t(flags), 'contamination', o.contamination, ...
        'n_trees', o.n_trees, 'max_samples', psi, 'seed', o.seed, ...
        'precision', NaN, 'recall', NaN, 'summary', '', ...
        'output_csv', '', 'output_png', '');
    result.summary = sprintf('pmu-iforest: frames=%d flagged=%d threshold=%.4f contamination=%g', ...
        n, sum(flags), threshold, o.contamination);
    if ~isempty(truth)
        tp = sum(flags & truth > 0);
        result.precision = tp / max(sum(flags), 1);
        result.recall = tp / max(sum(truth > 0), 1);
        result.summary = sprintf('%s precision=%.3f recall=%.3f', result.summary, ...
            result.precision, result.recall);
    end

    if ~isempty(o.output_csv)
        d = fileparts(o.output_csv);
        if ~isempty(d) && exist(d, 'dir') ~= 7, mkdir(d); end
        out = table(t, X(:,1), X(:,2), X(:,3), X(:,4), scores, double(flags), ...
            'VariableNames', [{'time_s'}, names, {'score', 'flag'}]);
        writetable(out, o.output_csv);
        result.output_csv = o.output_csv;
    end
    if ~isempty(o.output_png) || o.show
        if o.show, vis = 'on'; else, vis = 'off'; end
        fig = figure('Visible', vis, 'Position', [100 100 900 700]);
        subplot(3,1,1); plot(t, X(:,1), 'LineWidth', 0.8); hold on;
        plot(t(flags), X(flags,1), 'r.', 'MarkerSize', 14); ylabel('|V| (pu)');
        subplot(3,1,2); plot(t, fr, 'LineWidth', 0.8); hold on;
        plot(t(flags), fr(flags), 'r.', 'MarkerSize', 14); ylabel('f (Hz)');
        subplot(3,1,3); plot(t, scores, 'LineWidth', 0.8); hold on;
        yline(threshold, 'r--'); ylabel('anomaly score'); xlabel('time (s)');
        if ~isempty(o.output_png)
            d = fileparts(o.output_png);
            if ~isempty(d) && exist(d, 'dir') ~= 7, mkdir(d); end
            saveas(fig, o.output_png);
            result.output_png = o.output_png;
        end
        if ~o.show, close(fig); end
    end
end

function v = c_factor(n)
    if n <= 1
        v = 0;
    elseif n == 2
        v = 1;
    else
        v = 2 * (log(n - 1) + 0.5772156649015329) - 2 * (n - 1) / n;
    end
end

function q = quantile_linear(sorted, prob)
    % Same linear interpolation as numpy.quantile.
    pos = 1 + (numel(sorted) - 1) * prob;
    lo = floor(pos); hi = ceil(pos);
    q = sorted(lo) + (pos - lo) * (sorted(hi) - sorted(lo));
end

function node = grow(X, depth, limit)
    n = size(X, 1);
    lo = min(X, [], 1); hi = max(X, [], 1);
    cols = find(hi > lo);
    if depth >= limit || n <= 1 || isempty(cols)
        node = struct('leaf', true, 'size', n, 'q', 0, 'p', 0, 'left', [], 'right', []);
        return
    end
    q = cols(randi(numel(cols)));
    pv = lo(q) + rand() * (hi(q) - lo(q));
    mask = X(:, q) < pv;
    node = struct('leaf', false, 'size', n, 'q', q, 'p', pv, ...
        'left', grow(X(mask, :), depth + 1, limit), ...
        'right', grow(X(~mask, :), depth + 1, limit));
end

function len = tree_path(node, x)
    depth = 0;
    while ~node.leaf
        if x(node.q) < node.p
            node = node.left;
        else
            node = node.right;
        end
        depth = depth + 1;
    end
    len = depth + c_factor(node.size);
end
