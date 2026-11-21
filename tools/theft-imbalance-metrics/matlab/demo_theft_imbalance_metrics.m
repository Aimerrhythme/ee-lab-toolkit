function demo_theft_imbalance_metrics()
%DEMO_THEFT_IMBALANCE_METRICS Evaluate two scored detectors on imbalanced data.
%   From this folder, call demo_theft_imbalance_metrics. Outputs go to
%   examples/output/ (gitignored). Same summary lines as examples/run_demo.py.
    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    csvPath = fullfile(toolDir, 'examples', 'data', 'synthetic_theft_scores.csv');
    outDir = fullfile(toolDir, 'examples', 'output');
    result = theft_imbalance_metrics(csvPath, 'threshold', 0.5, ...
        'output_csv', fullfile(outDir, 'theft_imbalance_metrics_demo_matlab.csv'), ...
        'output_png', fullfile(outDir, 'theft_imbalance_metrics_demo_matlab.png'), ...
        'show', false);
    fprintf('n=%d positives=%d prevalence=%.4f threshold=%.2f\n', ...
        result.n, result.n_pos, result.prevalence, result.threshold);
    fprintf('always_normal_accuracy=%.4f\n', result.always_normal_accuracy);
    fprintf('model,operating_point,threshold,tp,fp,fn,tn,accuracy,precision,recall,f1,balanced_acc,roc_auc,ap\n');
    for k = 1:numel(result.rows)
        r = result.rows(k);
        fprintf('%s,%s,%.4f,%d,%d,%d,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n', ...
            r.model, r.operating_point, r.threshold, r.tp, r.fp, r.fn, r.tn, ...
            r.accuracy, r.precision, r.recall, r.f1, r.balanced_acc, r.roc_auc, r.ap);
    end
    fprintf('outputs in %s\n', outDir);
end
