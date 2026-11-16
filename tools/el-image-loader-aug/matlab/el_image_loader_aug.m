function res = el_image_loader_aug(csvPath, varargin)
%EL_IMAGE_LOADER_AUG Load EL cell images, stratified split, flip/rotate augmentation, montage.
%   res = el_image_loader_aug(csvPath, 'fractions',[0.6 0.2 0.2], 'seed',0, ...
%                             'output_dir',d, 'output_png',f)
%
%   Mirrors python/el_image_loader_aug.py (base MATLAB, no toolboxes).
%   CSV columns: path,proba,type   (path relative to the CSV folder; square,
%   same-size images). class = round(proba*3).
%
%   Split: per class, sort by path, rank j = 0..n-1, u = mod((j+seed)*PHI,1);
%   u < f_train -> train, u < f_train+f_val -> val, otherwise test.
%   Augmentation (train only): hflip, vflip, rot90 (CCW), rot180, rot270.
%
%   res fields: paths, types, proba, cls, split (cellstr), images (H x W x N),
%   classes, counts (K x 3: train/val/test), train_mean, train_std,
%   manifest (M x 2 cell: path, op), montage (K*H x 6*W).

p = inputParser;
addParameter(p, 'fractions', [0.6 0.2 0.2]);
addParameter(p, 'seed', 0);
addParameter(p, 'output_dir', '');
addParameter(p, 'output_png', '');
parse(p, varargin{:});
fr = p.Results.fractions;  seed = p.Results.seed;
if any(fr < 0) || abs(sum(fr) - 1) > 1e-9
    error('el_image_loader_aug:fractions', 'fractions must be non-negative and sum to 1');
end

PHI = 0.6180339887498949;
ops = {'orig','hflip','vflip','rot90','rot180','rot270'};
splits = {'train','val','test'};

% ---- read labels
fid = fopen(csvPath, 'r');
if fid < 0, error('cannot open %s', csvPath); end
fgetl(fid);                                   % header
paths = {}; types = {}; proba = [];
while true
    ln = fgetl(fid);
    if ~ischar(ln), break; end
    ln = strtrim(ln);
    if isempty(ln), continue; end
    f = strsplit(ln, ',');
    paths{end+1,1} = strtrim(f{1}); %#ok<AGROW>
    proba(end+1,1) = str2double(f{2}); %#ok<AGROW>
    types{end+1,1} = strtrim(f{3}); %#ok<AGROW>
end
fclose(fid);
n = numel(paths);
if n == 0, error('empty label CSV'); end
cls = round(proba * 3);
root = fileparts(csvPath);

% ---- read images
first = read_gray(fullfile(root, paths{1}));
[h, w] = size(first);
if h ~= w, error('all images must be square and the same size'); end
images = zeros(h, w, n);
images(:,:,1) = first;
for i = 2:n
    a = read_gray(fullfile(root, paths{i}));
    if ~isequal(size(a), [h w]), error('all images must be square and the same size'); end
    images(:,:,i) = a;
end

% ---- stratified split
split = cell(n, 1);
classes = unique(cls);
for k = 1:numel(classes)
    idx = find(cls == classes(k));
    [~, o] = sort(paths(idx));
    idx = idx(o);
    for j = 0:numel(idx)-1
        u = mod((j + seed) * PHI, 1);
        if u < fr(1)
            split{idx(j+1)} = 'train';
        elseif u < fr(1) + fr(2)
            split{idx(j+1)} = 'val';
        else
            split{idx(j+1)} = 'test';
        end
    end
end
counts = zeros(numel(classes), 3);
for k = 1:numel(classes)
    for s = 1:3
        counts(k, s) = sum(cls == classes(k) & strcmp(split, splits{s}));
    end
end
tr = strcmp(split, 'train');
tv = images(:,:,tr);
trainMean = mean(tv(:));
trainStd = std(tv(:), 1);

% ---- augmentation manifest (train only)
trIdx = find(tr);
manifest = cell(numel(trIdx) * 5, 2);
m = 0;
for i = trIdx'
    for o = 2:6
        m = m + 1;
        manifest(m,:) = {paths{i}, ops{o}};
    end
end

% ---- montage: one train sample per class, columns = orig + 5 ops
montage = zeros(numel(classes) * h, 6 * w);
for k = 1:numel(classes)
    idx = find(cls == classes(k) & tr);
    if isempty(idx)
        base = zeros(h, w);
    else
        [~, o] = sort(paths(idx));
        base = images(:,:,idx(o(1)));
    end
    for o = 1:6
        montage((k-1)*h+1:k*h, (o-1)*w+1:o*w) = apply_op(base, ops{o});
    end
end

res = struct('paths',{paths}, 'types',{types}, 'proba',proba, 'cls',cls, ...
    'split',{split}, 'images',images, 'classes',classes, 'counts',counts, ...
    'train_mean',trainMean, 'train_std',trainStd, 'manifest',{manifest}, 'montage',montage);

if ~isempty(p.Results.output_dir)
    write_outputs(res, p.Results.output_dir);
end
if ~isempty(p.Results.output_png)
    d = fileparts(p.Results.output_png);
    if ~isempty(d) && ~exist(d, 'dir'), mkdir(d); end
    imwrite(montage, p.Results.output_png);
end
end

function a = read_gray(path)
x = imread(path);
if isa(x, 'uint16'), sc = 65535; else, sc = 255; end
a = double(x) / sc;
if ndims(a) == 3
    a = mean(a(:,:,1:3), 3);
end
end

function out = apply_op(img, op)
switch op
    case 'orig',   out = img;
    case 'hflip',  out = fliplr(img);
    case 'vflip',  out = flipud(img);
    case 'rot90',  out = rot90(img, 1);
    case 'rot180', out = rot90(img, 2);
    case 'rot270', out = rot90(img, 3);
    otherwise, error('unknown op %s', op);
end
end

function write_outputs(res, d)
if ~exist(d, 'dir'), mkdir(d); end
fid = fopen(fullfile(d, 'split.csv'), 'w');
fprintf(fid, 'path,proba,type,class,split\n');
for i = 1:numel(res.paths)
    fprintf(fid, '%s,%.4f,%s,%d,%s\n', res.paths{i}, res.proba(i), res.types{i}, res.cls(i), res.split{i});
end
fclose(fid);
fid = fopen(fullfile(d, 'class_counts.csv'), 'w');
fprintf(fid, 'class,train,val,test\n');
for k = 1:numel(res.classes)
    fprintf(fid, '%d,%d,%d,%d\n', res.classes(k), res.counts(k,:));
end
fclose(fid);
fid = fopen(fullfile(d, 'aug_manifest.csv'), 'w');
fprintf(fid, 'path,op\n');
for i = 1:size(res.manifest, 1)
    fprintf(fid, '%s,%s\n', res.manifest{i,1}, res.manifest{i,2});
end
fclose(fid);
end
