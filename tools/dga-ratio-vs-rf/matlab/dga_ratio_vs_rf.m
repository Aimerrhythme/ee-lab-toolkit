function result = dga_ratio_vs_rf(csvPath, varargin)
%DGA_RATIO_VS_RF IEC 60599 three-ratio rule versus a small random forest.
%   result = dga_ratio_vs_rf(csvPath, 'n_trees', 50, 'max_depth', 6, ...
%       'mtry', 2, 'min_samples_split', 2, 'seed', 0, ...
%       'output_csv', '', 'output_png', '', 'show', false)
%
%   CSV columns: sample_id,h2_ppm,ch4_ppm,c2h6_ppm,c2h4_ppm,c2h2_ppm,label,split
%   (label in PD,D1,D2,T1,T2,T3; split in train,test). Matches
%   python/dga_ratio_vs_rf.py: same shared 32-bit LCG, same split search, same
%   fields. Base MATLAB only. Teaching use; simplified ratio table.
%
%   Features for the forest are log10(1 + ppm). Rule ratios use each gas
%   floored at 0.1 ppm: R1 = C2H2/C2H4, R2 = CH4/H2, R3 = C2H4/C2H6.

    classes = {'PD', 'D1', 'D2', 'T1', 'T2', 'T3'};
    gases = {'H2', 'CH4', 'C2H6', 'C2H4', 'C2H2'};
    nCls = numel(classes);

    opt = struct('n_trees', 50, 'max_depth', 6, 'mtry', 2, ...
        'min_samples_split', 2, 'seed', 0, 'output_csv', '', ...
        'output_png', '', 'show', false);
    if mod(numel(varargin), 2) ~= 0
        error('dga_ratio_vs_rf:args', 'Options must be name/value pairs.');
    end
    names = fieldnames(opt);
    for a = 1:2:numel(varargin)
        hit = find(strcmpi(varargin{a}, names), 1);
        if isempty(hit)
            error('dga_ratio_vs_rf:args', 'unknown parameter name: %s', char(string(varargin{a})));
        end
        opt.(names{hit}) = varargin{a + 1};
    end
    ints = {'n_trees', 'max_depth', 'mtry', 'min_samples_split'};
    for a = 1:numel(ints)
        v = opt.(ints{a});
        if ~isnumeric(v) || ~isscalar(v) || v < 1 || v ~= floor(v)
            error('dga_ratio_vs_rf:args', '%s must be a positive integer', ints{a});
        end
    end
    if opt.mtry > 5
        error('dga_ratio_vs_rf:args', 'mtry must not exceed 5');
    end
    if ~isnumeric(opt.seed) || ~isscalar(opt.seed) || opt.seed < 0 || opt.seed ~= floor(opt.seed)
        error('dga_ratio_vs_rf:args', 'seed must be a non-negative integer');
    end
    if ~(islogical(opt.show) || isnumeric(opt.show)) || ~isscalar(opt.show)
        error('dga_ratio_vs_rf:args', 'show must be true or false');
    end

    [ids, gas, y, split] = read_samples(csvPath, classes);
    isTrain = strcmp(split, 'train');
    isTest = ~isTrain;
    if ~any(isTrain) || ~any(isTest)
        error('dga_ratio_vs_rf:data', 'need at least one train and one test sample');
    end
    feats = log10(1 + gas);
    [trees, importance] = fit_forest(feats(isTrain, :), y(isTrain), opt, nCls);
    [pred, prob] = predict_forest(trees, feats, nCls);

    g = max(gas, 0.1);
    rat = [g(:, 5) ./ g(:, 4), g(:, 2) ./ g(:, 1), g(:, 4) ./ g(:, 3)];
    ruleIdx = zeros(size(y));
    for i = 1:numel(y)
        ruleIdx(i) = iec_rule(rat(i, 1), rat(i, 2), rat(i, 3));
    end

    confRule = zeros(nCls, nCls + 1);
    confRf = zeros(nCls, nCls);
    testRows = find(isTest);
    for i = testRows(:)'
        confRule(y(i), ruleIdx(i)) = confRule(y(i), ruleIdx(i)) + 1;
        confRf(y(i), pred(i)) = confRf(y(i), pred(i)) + 1;
    end
    accRule = mean(ruleIdx(isTest) == y(isTest));
    accRf = mean(pred(isTest) == y(isTest));
    ndFrac = mean(ruleIdx(isTest) == nCls + 1);

    ruleNames = [classes, {'ND'}];
    result = struct();
    result.sample_ids = ids;
    result.split = split;
    result.true_label = classes(y);
    result.rule_label = ruleNames(ruleIdx);
    result.rf_label = classes(pred);
    result.rf_prob = max(prob, [], 2);
    result.ratios = rat;
    result.confusion_rule = confRule;
    result.confusion_rf = confRf;
    result.importance = importance;
    result.acc_rule = accRule;
    result.acc_rf = accRf;
    result.rule_nd_fraction = ndFrac;
    result.n_train = sum(isTrain);
    result.n_test = sum(isTest);
    result.n_trees = opt.n_trees;
    result.max_depth = opt.max_depth;
    result.mtry = opt.mtry;
    result.seed = opt.seed;
    result.summary = format_table(result, classes, gases);
    result.output_csv = '';
    result.output_png = '';
    result.fig = [];

    if ~isempty(opt.output_csv)
        outDir = fileparts(opt.output_csv);
        if ~isempty(outDir) && exist(outDir, 'dir') ~= 7
            mkdir(outDir);
        end
        fid = fopen(opt.output_csv, 'w');
        fprintf(fid, 'sample_id,split,true,rule,rf,rf_prob,r1,r2,r3\n');
        for i = 1:numel(ids)
            fprintf(fid, '%s,%s,%s,%s,%s,%.4f,%.4f,%.4f,%.4f\n', ids{i}, split{i}, ...
                result.true_label{i}, result.rule_label{i}, result.rf_label{i}, ...
                result.rf_prob(i), rat(i, 1), rat(i, 2), rat(i, 3));
        end
        fclose(fid);
        result.output_csv = opt.output_csv;
    end
    if ~isempty(opt.output_png) || opt.show
        fig = make_plot(result, classes, gases, opt.show);
        if ~isempty(opt.output_png)
            outDir = fileparts(opt.output_png);
            if ~isempty(outDir) && exist(outDir, 'dir') ~= 7
                mkdir(outDir);
            end
            saveas(fig, opt.output_png);
            result.output_png = opt.output_png;
        end
        if opt.show
            result.fig = fig;
        else
            close(fig);
        end
    end
end

function [ids, gas, y, split] = read_samples(csvPath, classes)
    if exist(csvPath, 'file') ~= 2
        error('dga_ratio_vs_rf:data', 'CSV not found: %s', csvPath);
    end
    fid = fopen(csvPath, 'r');
    header = strtrim(fgetl(fid));
    cols = strtrim(strsplit(header, ','));
    need = {'sample_id', 'h2_ppm', 'ch4_ppm', 'c2h6_ppm', 'c2h4_ppm', 'c2h2_ppm', 'label', 'split'};
    pos = zeros(1, numel(need));
    for a = 1:numel(need)
        hit = find(strcmp(need{a}, cols), 1);
        if isempty(hit)
            fclose(fid);
            error('dga_ratio_vs_rf:data', 'CSV missing columns: %s', need{a});
        end
        pos(a) = hit;
    end
    ids = {}; split = {}; gas = zeros(0, 5); y = zeros(0, 1);
    while true
        line = fgetl(fid);
        if ~ischar(line)
            break;
        end
        line = strtrim(line);
        if isempty(line)
            continue;
        end
        f = strtrim(strsplit(line, ','));
        ids{end + 1, 1} = f{pos(1)}; %#ok<AGROW>
        gas(end + 1, :) = cellfun(@str2double, f(pos(2:6))); %#ok<AGROW>
        lab = find(strcmp(f{pos(7)}, classes), 1);
        if isempty(lab)
            fclose(fid);
            error('dga_ratio_vs_rf:data', 'unknown label %s', f{pos(7)});
        end
        y(end + 1, 1) = lab; %#ok<AGROW>
        if ~any(strcmp(f{pos(8)}, {'train', 'test'}))
            fclose(fid);
            error('dga_ratio_vs_rf:data', 'split must be train or test');
        end
        split{end + 1, 1} = f{pos(8)}; %#ok<AGROW>
    end
    fclose(fid);
    if isempty(ids)
        error('dga_ratio_vs_rf:data', 'CSV has no data rows');
    end
    if any(~isfinite(gas(:))) || any(gas(:) < 0)
        error('dga_ratio_vs_rf:data', 'gas concentrations must be finite and non-negative');
    end
end

function idx = iec_rule(r1, r2, r3)
% Simplified IEC 60599 table; first match wins; 7 means ND.
    if r2 < 0.1 && r3 < 0.2
        idx = 1;
    elseif r1 > 1 && r2 >= 0.1 && r2 <= 0.5 && r3 > 1
        idx = 2;
    elseif r1 >= 0.6 && r1 <= 2.5 && r2 >= 0.1 && r2 <= 1 && r3 > 2
        idx = 3;
    elseif r2 > 1 && r3 < 1
        idx = 4;
    elseif r1 < 0.1 && r2 > 1 && r3 >= 1 && r3 <= 4
        idx = 5;
    elseif r1 < 0.2 && r2 > 1 && r3 > 4
        idx = 6;
    else
        idx = 7;
    end
end

function [state, v] = lcg_randint(state, n)
    state = mod(1664525 * state + 1013904223, 4294967296);
    v = floor(state / 4294967296 * n);
end

function s = gini_sum(counts)
    n = 0;
    sq = 0;
    for i = 1:numel(counts)
        n = n + counts(i);
        sq = sq + counts(i) * counts(i);
    end
    if n == 0
        s = 0;
    else
        s = n - sq / n;
    end
end

function [trees, importance] = fit_forest(x, y, opt, k)
    n = numel(y);
    nf = size(x, 2);
    importance = zeros(1, nf);
    trees = cell(opt.n_trees, 1);
    for t = 1:opt.n_trees
        state = mod(opt.seed + t - 1, 4294967296);
        boot = zeros(n, 1);
        for i = 1:n
            [state, v] = lcg_randint(state, n);
            boot(i) = v + 1;
        end
        feature = []; thr = []; left = []; right = []; prob = zeros(0, k);
        stack = struct('idx', {boot}, 'depth', {0}, 'parent', {0}, 'side', {0});
        while ~isempty(stack)
            item = stack(end);
            stack(end) = [];
            idx = item.idx;
            node = numel(feature) + 1;
            counts = zeros(1, k);
            for c = 1:k
                counts(c) = sum(y(idx) == c);
            end
            feature(node, 1) = -1; thr(node, 1) = 0; %#ok<AGROW>
            left(node, 1) = 0; right(node, 1) = 0; %#ok<AGROW>
            prob(node, :) = counts / sum(counts); %#ok<AGROW>
            if item.parent > 0
                if item.side == 1
                    left(item.parent) = node;
                else
                    right(item.parent) = node;
                end
            end
            m = numel(idx);
            parentG = gini_sum(counts);
            if parentG == 0 || m < opt.min_samples_split || item.depth >= opt.max_depth
                continue;
            end
            order = 1:nf;
            for i = 1:opt.mtry
                [state, v] = lcg_randint(state, nf - i + 1);
                j = i + v;
                tmp = order(i); order(i) = order(j); order(j) = tmp;
            end
            bestScore = Inf; bestF = 0; bestThr = 0;
            for q = 1:opt.mtry
                f = order(q);
                [vals, o] = sort(x(idx, f));
                srt = idx(o);
                lc = zeros(1, k);
                rc = counts;
                for p = 1:m - 1
                    lab = y(srt(p));
                    lc(lab) = lc(lab) + 1;
                    rc(lab) = rc(lab) - 1;
                    if vals(p) == vals(p + 1)
                        continue;
                    end
                    score = gini_sum(lc) + gini_sum(rc);
                    if score < bestScore
                        bestScore = score; bestF = f;
                        bestThr = (vals(p) + vals(p + 1)) / 2;
                    end
                end
            end
            if bestF == 0
                continue;
            end
            importance(bestF) = importance(bestF) + parentG - bestScore;
            feature(node) = bestF;
            thr(node) = bestThr;
            mask = x(idx, bestF) <= bestThr;
            % Push right first so the left subtree is grown first (same RNG order as Python).
            stack(end + 1) = struct('idx', idx(~mask), 'depth', item.depth + 1, 'parent', node, 'side', 2); %#ok<AGROW>
            stack(end + 1) = struct('idx', idx(mask), 'depth', item.depth + 1, 'parent', node, 'side', 1); %#ok<AGROW>
        end
        trees{t} = struct('feature', feature, 'thr', thr, 'left', left, 'right', right, 'prob', prob);
    end
    total = sum(importance);
    if total > 0
        importance = importance / total;
    end
end

function [pred, prob] = predict_forest(trees, x, k)
    n = size(x, 1);
    prob = zeros(n, k);
    for t = 1:numel(trees)
        tr = trees{t};
        for i = 1:n
            node = 1;
            while tr.feature(node) > 0
                if x(i, tr.feature(node)) <= tr.thr(node)
                    node = tr.left(node);
                else
                    node = tr.right(node);
                end
            end
            prob(i, :) = prob(i, :) + tr.prob(node, :);
        end
    end
    prob = prob / numel(trees);
    [~, pred] = max(prob, [], 2);
end

function text = format_table(r, classes, gases)
    lines = {};
    lines{end + 1} = sprintf('train=%d  test=%d  n_trees=%d  max_depth=%d  mtry=%d  seed=%d', ...
        r.n_train, r.n_test, r.n_trees, r.max_depth, r.mtry, r.seed);
    lines{end + 1} = sprintf('accuracy_test  rule=%.4f  rf=%.4f  rule_nd_fraction=%.4f', ...
        r.acc_rule, r.acc_rf, r.rule_nd_fraction);
    lines{end + 1} = '';
    parts = cell(1, numel(gases));
    for i = 1:numel(gases)
        parts{i} = sprintf('%s=%.4f', gases{i}, r.importance(i));
    end
    lines{end + 1} = ['importance ' strjoin(parts, '  ')];
    lines{end + 1} = '';
    lines{end + 1} = ['confusion_rule (rows true, cols ' strjoin([classes, {'ND'}], ',') ')'];
    for i = 1:size(r.confusion_rule, 1)
        lines{end + 1} = ['  ' classes{i} ' ' strjoin(arrayfun(@(v) sprintf('%3d', v), r.confusion_rule(i, :), 'UniformOutput', false), ' ')]; %#ok<AGROW>
    end
    lines{end + 1} = '';
    lines{end + 1} = ['confusion_rf (rows true, cols ' strjoin(classes, ',') ')'];
    for i = 1:size(r.confusion_rf, 1)
        lines{end + 1} = ['  ' classes{i} ' ' strjoin(arrayfun(@(v) sprintf('%3d', v), r.confusion_rf(i, :), 'UniformOutput', false), ' ')]; %#ok<AGROW>
    end
    text = strjoin(lines, newline);
end

function fig = make_plot(r, classes, gases, show)
    if show
        vis = 'on';
    else
        vis = 'off';
    end
    fig = figure('Visible', vis, 'Position', [100 100 1100 340]);
    mats = {r.confusion_rule, r.confusion_rf};
    cols = {[classes, {'ND'}], classes};
    titles = {sprintf('IEC ratio rule (acc=%.2f)', r.acc_rule), ...
        sprintf('Random forest (acc=%.2f)', r.acc_rf)};
    for p = 1:2
        subplot(1, 3, p);
        imagesc(mats{p});
        colormap(gca, flipud(gray));
        set(gca, 'XTick', 1:numel(cols{p}), 'XTickLabel', cols{p}, ...
            'YTick', 1:numel(classes), 'YTickLabel', classes);
        xlabel('Predicted'); ylabel('True'); title(titles{p});
        for i = 1:size(mats{p}, 1)
            for j = 1:size(mats{p}, 2)
                text(j, i, num2str(mats{p}(i, j)), 'HorizontalAlignment', 'center', 'Color', [0.8 0.2 0.2]);
            end
        end
    end
    subplot(1, 3, 3);
    bar(r.importance, 'FaceColor', [0.2 0.6 0.3]);
    set(gca, 'XTick', 1:numel(gases), 'XTickLabel', gases);
    ylabel('Gini importance (sum = 1)'); title('Gas feature importance');
end
