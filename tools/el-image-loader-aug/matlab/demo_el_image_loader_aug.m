% DEMO_EL_IMAGE_LOADER_AUG  Run the EL image loader / split / augmentation demo.
% Run from tools/el-image-loader-aug/matlab.
here = fileparts(mfilename('fullpath'));
tool = fileparts(here);
outDir = fullfile(tool, 'examples', 'output');
png = fullfile(outDir, 'el_montage_demo_matlab.png');
res = el_image_loader_aug(fullfile(tool, 'examples', 'data', 'labels.csv'), ...
    'output_dir', fullfile(outDir, 'el_image_loader_aug_matlab'), 'output_png', png);

fprintf('%d images, size %dx%d\n', numel(res.paths), size(res.images,1), size(res.images,2));
fprintf('class  train  val  test\n');
for k = 1:numel(res.classes)
    fprintf('%5d  %5d  %3d  %4d\n', res.classes(k), res.counts(k,:));
end
fprintf('train mean=%.4f std=%.4f; augmented copies=%d\n', ...
    res.train_mean, res.train_std, size(res.manifest, 1));
fprintf('saved %s\n', png);
