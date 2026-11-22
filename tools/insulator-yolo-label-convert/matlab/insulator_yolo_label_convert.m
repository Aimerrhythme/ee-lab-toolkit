function result = insulator_yolo_label_convert(vocDir, outDir, varargin)
%INSULATOR_YOLO_LABEL_CONVERT Convert Pascal-VOC XML boxes to YOLO txt, split 7:2:1.
%   result = insulator_yolo_label_convert(vocDir, outDir, 'classes', {}, ...
%       'viz_n', 6, 'output_png', '', 'show', false)
%   vocDir holds annotations/*.xml and images/. Split rule on sorted position
%   i (0-based): mod(i,10) in 0-6 train, 7-8 val, 9 test. Base MATLAB only.
    p = inputParser;
    addParameter(p, 'classes', {});
    addParameter(p, 'viz_n', 6);
    addParameter(p, 'output_png', '');
    addParameter(p, 'show', false);
    parse(p, varargin{:});
    o = p.Results;

    xmls = dir(fullfile(vocDir, 'annotations', '*.xml'));
    if isempty(xmls), error('yolo:noxml', 'no XML files in %s', vocDir); end
    [~, order] = sort({xmls.name});
    xmls = xmls(order);
    n = numel(xmls);
    ann = cell(n, 1);
    stems = cell(n, 1);
    for i = 1:n
        [~, stems{i}] = fileparts(xmls(i).name);
        ann{i} = parse_voc(fullfile(vocDir, 'annotations', xmls(i).name));
    end
    classes = o.classes;
    if isempty(classes)
        names = {};
        for i = 1:n, names = [names, ann{i}.names]; end %#ok<AGROW>
        classes = sort(unique(names));
    end
    splits = {'train', 'val', 'test'};
    for s = 1:3
        mkdir_p(fullfile(outDir, 'images', splits{s}));
        mkdir_p(fullfile(outDir, 'labels', splits{s}));
    end
    splitCounts = struct('train', 0, 'val', 0, 'test', 0);
    classCounts = zeros(1, numel(classes));
    nBoxes = 0; nSkipped = 0; nEmpty = 0;
    items = struct('stem', {}, 'split', {}, 'ext', {});
    for i = 1:n
        sp = split_of(i - 1);
        a = ann{i};
        src = fullfile(vocDir, 'images', a.filename);
        if isempty(a.filename) || ~isfile(src)
            c = dir(fullfile(vocDir, 'images', [stems{i} '.*']));
            if isempty(c), error('yolo:noimg', 'image for %s not found', stems{i}); end
            src = fullfile(c(1).folder, c(1).name);
        end
        [~, ~, ext] = fileparts(src);
        lines = {};
        for k = 1:numel(a.names)
            id = find(strcmp(classes, a.names{k}), 1);
            yb = [];
            if ~isempty(id), yb = box_to_yolo(a.boxes(k, :), a.width, a.height); end
            if isempty(yb)
                nSkipped = nSkipped + 1;
                continue
            end
            lines{end + 1} = sprintf('%d %.6f %.6f %.6f %.6f', id - 1, yb); %#ok<AGROW>
            classCounts(id) = classCounts(id) + 1;
        end
        nBoxes = nBoxes + numel(lines);
        nEmpty = nEmpty + isempty(lines);
        write_lines(fullfile(outDir, 'labels', sp, [stems{i} '.txt']), lines);
        copyfile(src, fullfile(outDir, 'images', sp, [stems{i} ext]));
        splitCounts.(sp) = splitCounts.(sp) + 1;
        items(end + 1) = struct('stem', stems{i}, 'split', sp, 'ext', ext); %#ok<AGROW>
    end
    write_lines(fullfile(outDir, 'classes.txt'), classes);
    write_lines(fullfile(outDir, 'data.yaml'), {'path: .', 'train: images/train', ...
        'val: images/val', 'test: images/test', sprintf('nc: %d', numel(classes)), ...
        ['names: [' strjoin(classes, ', ') ']']});

    result = struct('n_images', n, 'n_boxes', nBoxes, 'n_skipped', nSkipped, ...
        'n_empty_images', nEmpty, 'classes', {classes}, 'class_counts', classCounts, ...
        'split_counts', splitCounts, 'items', items, 'out_dir', outDir);
    if ~isempty(o.output_png)
        draw_check(result, o.viz_n, o.output_png, o.show);
    end
end

function s = split_of(idx)
    k = mod(idx, 10);
    if k < 7, s = 'train'; elseif k < 9, s = 'val'; else, s = 'test'; end
end

function a = parse_voc(path)
    doc = xmlread(path);
    root = doc.getDocumentElement();
    a.filename = char(first_text(root, 'filename'));
    sz = root.getElementsByTagName('size').item(0);
    if isempty(sz), error('yolo:size', '%s: missing <size>', path); end
    a.width = round(str2double(first_text(sz, 'width')));
    a.height = round(str2double(first_text(sz, 'height')));
    if ~(a.width > 0 && a.height > 0), error('yolo:size', '%s: bad image size', path); end
    objs = root.getElementsByTagName('object');
    a.names = {};
    a.boxes = zeros(0, 4);
    for k = 0:objs.getLength() - 1
        ob = objs.item(k);
        bb = ob.getElementsByTagName('bndbox').item(0);
        if isempty(bb), continue; end
        a.names{end + 1} = strtrim(char(first_text(ob, 'name'))); %#ok<AGROW>
        a.boxes(end + 1, :) = [str2double(first_text(bb, 'xmin')), str2double(first_text(bb, 'ymin')), ...
            str2double(first_text(bb, 'xmax')), str2double(first_text(bb, 'ymax'))]; %#ok<AGROW>
    end
end

function t = first_text(node, tag)
    el = node.getElementsByTagName(tag).item(0);
    if isempty(el), t = ''; else, t = strtrim(char(el.getTextContent())); end
end

function yb = box_to_yolo(b, w, h)
    xmin = min(max(b(1), 0), w); xmax = min(max(b(3), 0), w);
    ymin = min(max(b(2), 0), h); ymax = min(max(b(4), 0), h);
    if xmax <= xmin || ymax <= ymin
        yb = [];
    else
        yb = [(xmin + xmax) / 2 / w, (ymin + ymax) / 2 / h, (xmax - xmin) / w, (ymax - ymin) / h];
    end
end

function write_lines(path, lines)
    fid = fopen(path, 'w');
    if fid < 0, error('yolo:write', 'cannot write %s', path); end
    for k = 1:numel(lines), fprintf(fid, '%s\n', lines{k}); end
    fclose(fid);
end

function mkdir_p(d)
    if ~isfolder(d), mkdir(d); end
end

function draw_check(result, vizN, outPng, show)
    items = result.items(1:min(max(1, vizN), numel(result.items)));
    cols = min(3, numel(items));
    rows = ceil(numel(items) / cols);
    vis = 'off'; if show, vis = 'on'; end
    fig = figure('Visible', vis, 'Position', [100 100 360 * cols 290 * rows]);
    colors = {[0.17 0.63 0.17], [0.84 0.15 0.16], [0.12 0.47 0.71], [1 0.5 0.05]};
    for k = 1:numel(items)
        it = items(k);
        subplot(rows, cols, k);
        img = imread(fullfile(result.out_dir, 'images', it.split, [it.stem it.ext]));
        imshow(img); hold on;
        [h, w, ~] = size(img);
        txt = strtrim(fileread(fullfile(result.out_dir, 'labels', it.split, [it.stem '.txt'])));
        if ~isempty(txt)
            v = sscanf(txt, '%f', [5 Inf])';
            for r = 1:size(v, 1)
                c = v(r, 1);
                x = (v(r, 2) - v(r, 4) / 2) * w; y = (v(r, 3) - v(r, 5) / 2) * h;
                col = colors{mod(c, 4) + 1};
                rectangle('Position', [x y v(r, 4) * w v(r, 5) * h], 'EdgeColor', col, 'LineWidth', 1.6);
                text(x, y - 3, result.classes{c + 1}, 'Color', col, 'FontSize', 7);
            end
        end
        title(sprintf('%s [%s]', it.stem, it.split), 'Interpreter', 'none', 'FontSize', 8);
    end
    d = fileparts(outPng);
    if ~isempty(d) && ~isfolder(d), mkdir(d); end
    saveas(fig, outPng);
    if ~show, close(fig); end
end
