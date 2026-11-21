function result = theft_imbalance_metrics(csvPath, varargin)
%THEFT_IMBALANCE_METRICS Confusion matrix, ROC/PR, F1 and best-F1 threshold.
%   result = theft_imbalance_metrics(csvPath, 'threshold', 0.5, ...
%       'output_csv', '', 'output_png', '', 'show', false)
%   CSV: y_true (0/1) then >=1 score columns; predict theft when score >= threshold.
%   result.rows is a struct array (fields as in the output CSV header),
%   result.models the score-column names. Base MATLAB only.
    p = inputParser;
    addParameter(p, 'threshold', 0.5);
    addParameter(p, 'output_csv', '');
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;
    if o.threshold < 0 || o.threshold > 1
        error('theft:thr', 'threshold must be in [0, 1]');
    end

    fid = fopen(csvPath, 'r');
    if fid < 0, error('theft:file', 'cannot open %s', csvPath); end
    c = onCleanup(@() fclose(fid));
    names = strtrim(strsplit(strtrim(fgetl(fid)), ','));
    if numel(names) < 2 || ~strcmp(names{1}, 'y_true')
        error('theft:header', 'first column must be y_true plus >=1 score column');
    end
    t = textscan(fid, repmat('%f', 1, numel(names)), 'Delimiter', ',');
    len = cellfun(@numel, t);
    if any(len ~= len(1)) || len(1) == 0
        error('theft:rows', 'ragged or empty data');
    end
    D = cell2mat(t);
    if any(~isfinite(D(:))), error('theft:nan', 'all cells must be finite numbers'); end
    y = D(:, 1);
    if any(y ~= 0 & y ~= 1), error('theft:label', 'y_true must be 0 or 1'); end
    if sum(y) == 0 || sum(y) == numel(y), error('theft:class', 'y_true needs both classes'); end
    S = D(:, 2:end);
    models = names(2:end);
    n = numel(y); npos = sum(y);

    rows = row_of('always_normal', 'fixed', 1.0, y, zeros(n, 1), 0.5, npos / n);
    curves = struct();
    for j = 1:numel(models)
        s = S(:, j);
        cv = curve_points(y, s);
        auc = trapz([0; cv.fpr], [0; cv.tpr]);
        ap = sum(diff([0; cv.tpr]) .* cv.precision);
        [~, k] = max(cv.f1);   % first max = highest threshold
        rows(end+1) = row_of(models{j}, 'fixed', o.threshold, y, s, auc, ap); %#ok<AGROW>
        rows(end+1) = row_of(models{j}, 'best_f1', cv.thresholds(k), y, s, auc, ap); %#ok<AGROW>
        curves.(models{j}) = cv;
    end
    result.n = n; result.n_pos = npos; result.prevalence = npos / n;
    result.threshold = o.threshold; result.models = models; result.rows = rows;
    result.always_normal_accuracy = 1 - npos / n;
    result.curves = curves; result.y = y; result.scores = S;

    if ~isempty(o.output_csv)
        d = fileparts(o.output_csv);
        if ~isempty(d) && ~exist(d, 'dir'), mkdir(d); end
        f = fopen(o.output_csv, 'w');
        fprintf(f, '%s\n', header_line());
        for r = 1:numel(rows), fprintf(f, '%s\n', format_row(rows(r))); end
        fclose(f);
    end
    if ~isempty(o.output_png) || o.show
        plot_all(result, o.output_png, o.show);
    end
end

function cv = curve_points(y, s)
    [ss, order] = sort(s, 'descend');
    ys = y(order);
    last = [find(diff(ss) ~= 0); numel(ss)];
    ctp = cumsum(ys);
    tp = ctp(last);
    npred = last;
    pos = sum(y); neg = numel(y) - pos;
    cv.thresholds = ss(last);
    cv.tp = tp; cv.fp = npred - tp;
    cv.tpr = tp / pos; cv.fpr = (npred - tp) / neg;
    cv.precision = tp ./ npred;
    cv.f1 = 2 * tp ./ (npred + pos);
end

function r = row_of(model, point, thr, y, s, auc, ap)
    pred = s >= thr;
    tp = sum(pred & y == 1); fp = sum(pred & y == 0);
    fn = sum(~pred & y == 1); tn = sum(~pred & y == 0);
    if tp + fp > 0, prec = tp / (tp + fp); else, prec = 0; end
    if tp + fn > 0, rec = tp / (tp + fn); else, rec = 0; end
    if tp > 0, f1 = 2 * tp / (2 * tp + fp + fn); else, f1 = 0; end
    if tn + fp > 0, tnr = tn / (tn + fp); else, tnr = 0; end
    r = struct('model', model, 'operating_point', point, 'threshold', thr, ...
        'tp', tp, 'fp', fp, 'fn', fn, 'tn', tn, ...
        'accuracy', (tp + tn) / (tp + fp + fn + tn), 'precision', prec, ...
        'recall', rec, 'f1', f1, 'balanced_acc', (rec + tnr) / 2, ...
        'roc_auc', auc, 'ap', ap);
end

function s = header_line()
    s = 'model,operating_point,threshold,tp,fp,fn,tn,accuracy,precision,recall,f1,balanced_acc,roc_auc,ap';
end

function s = format_row(r)
    s = sprintf('%s,%s,%.4f,%d,%d,%d,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f', ...
        r.model, r.operating_point, r.threshold, r.tp, r.fp, r.fn, r.tn, ...
        r.accuracy, r.precision, r.recall, r.f1, r.balanced_acc, r.roc_auc, r.ap);
end

function plot_all(result, outPng, show)
    vis = 'off'; if show, vis = 'on'; end
    fig = figure('Visible', vis, 'Position', [100 100 900 720]);
    names = result.models;
    subplot(2, 2, 1); hold on; grid on;
    subplot(2, 2, 2); hold on; grid on;
    subplot(2, 2, 3); hold on; grid on;
    for j = 1:numel(names)
        cv = result.curves.(names{j});
        r = result.rows(2 * j);   % fixed row of model j
        subplot(2, 2, 1);
        plot([0; cv.fpr], [0; cv.tpr], 'DisplayName', sprintf('%s (AUC %.3f)', names{j}, r.roc_auc));
        subplot(2, 2, 2);
        plot(cv.tpr, cv.precision, 'DisplayName', sprintf('%s (AP %.3f)', names{j}, r.ap));
        subplot(2, 2, 3);
        plot(cv.thresholds, cv.f1, 'DisplayName', names{j});
    end
    subplot(2, 2, 1); plot([0 1], [0 1], 'k:', 'HandleVisibility', 'off');
    title('ROC'); xlabel('FPR'); ylabel('TPR'); legend('Location', 'southeast');
    subplot(2, 2, 2); yline(result.prevalence, 'k:', 'prevalence');
    title('PR curve'); xlabel('Recall'); ylabel('Precision'); legend('Location', 'northeast');
    subplot(2, 2, 3); xline(result.threshold, 'k:');
    title('F1 vs threshold'); xlabel('threshold'); ylabel('F1'); legend('Location', 'northeast');
    r = result.rows(2);
    cm = [r.tn r.fp; r.fn r.tp];
    subplot(2, 2, 4); imagesc(cm); colormap(gca, flipud(gray)); axis equal tight;
    for a = 1:2
        for b = 1:2, text(b, a, num2str(cm(a, b)), 'HorizontalAlignment', 'center', 'Color', 'r'); end
    end
    set(gca, 'XTick', 1:2, 'XTickLabel', {'pred 0', 'pred 1'}, 'YTick', 1:2, 'YTickLabel', {'true 0', 'true 1'});
    title(sprintf('confusion: %s @ %.2f', names{1}, result.threshold));
    if ~isempty(outPng)
        d = fileparts(outPng);
        if ~isempty(d) && ~exist(d, 'dir'), mkdir(d); end
        saveas(fig, outPng);
    end
    if ~show, close(fig); end
end
