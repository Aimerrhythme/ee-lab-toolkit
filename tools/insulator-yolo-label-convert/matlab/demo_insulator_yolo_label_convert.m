function demo_insulator_yolo_label_convert()
%DEMO_INSULATOR_YOLO_LABEL_CONVERT Convert the synthetic VOC sample to YOLO format.
%   From this folder, call demo_insulator_yolo_label_convert. Outputs go to
%   examples/output/ (gitignored). Same summary lines as examples/run_demo.py.
    here = fileparts(mfilename('fullpath'));
    addpath(here);
    toolDir = fileparts(here);
    outBase = fullfile(toolDir, 'examples', 'output');
    result = insulator_yolo_label_convert(fullfile(toolDir, 'examples', 'data', 'voc'), ...
        fullfile(outBase, 'yolo_matlab'), ...
        'output_png', fullfile(outBase, 'insulator_check_matlab.png'), 'show', false);
    fprintf('images=%d boxes=%d skipped=%d empty_images=%d\n', result.n_images, ...
        result.n_boxes, result.n_skipped, result.n_empty_images);
    fprintf('split train=%d val=%d test=%d\n', result.split_counts.train, ...
        result.split_counts.val, result.split_counts.test);
    for k = 1:numel(result.classes)
        fprintf('class %s id=%d boxes=%d\n', result.classes{k}, k - 1, result.class_counts(k));
    end
    fprintf('outputs in %s\n', outBase);
end
