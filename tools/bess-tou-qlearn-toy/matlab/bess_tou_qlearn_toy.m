function r = bess_tou_qlearn_toy(prices_or_csv, varargin)
%BESS_TOU_QLEARN_TOY Tabular Q-learning for a battery on a TOU tariff (toy).
%   r = bess_tou_qlearn_toy(csvPath, 'n_soc', 6, 'soc0', 0, 'e_step_kwh', 10, ...
%       'eta', 0.95, 'alpha', 0.5, 'n_iter', 200, 'output_csv', '')
%   The first argument may be a hour,price CSV path or a numeric price vector.
%   State = (hour, SOC level), action = discharge/idle/charge one level.
%   Training is a deterministic full sweep (no random exploration), so the
%   numbers match the Python version. Costs are in yuan; negative = profit.
%   Fields: prices, q (H x n_soc x 3), learned_soc (H+1), learned_action (H),
%   greedy_soc, greedy_action, learned_cost, greedy_cost, n_soc, soc0, output_csv.

    p = inputParser;
    addParameter(p, 'n_soc', 6);
    addParameter(p, 'soc0', 0);
    addParameter(p, 'e_step_kwh', 10.0);
    addParameter(p, 'eta', 0.95);
    addParameter(p, 'alpha', 0.5);
    addParameter(p, 'n_iter', 200);
    addParameter(p, 'output_csv', '');
    parse(p, varargin{:});
    n_soc = p.Results.n_soc; soc0 = p.Results.soc0;
    e = p.Results.e_step_kwh; eta = p.Results.eta;
    alpha = p.Results.alpha; n_iter = p.Results.n_iter;
    outCsv = p.Results.output_csv;

    if isnumeric(prices_or_csv)
        prices = prices_or_csv(:);
    else
        T = readtable(prices_or_csv);
        T = sortrows(T, 'hour');
        prices = T.price(:);
    end
    H = numel(prices);
    acts = [-1 0 1];
    termValue = mean(prices) * eta * e;
    vT = termValue * ((0:n_soc-1)' - soc0);   % indexed by SOC level + 1

    valid = false(n_soc, 3);
    for s = 0:n_soc-1
        for k = 1:3
            valid(s+1, k) = (s + acts(k) >= 0) && (s + acts(k) <= n_soc-1);
        end
    end

    q = zeros(H, n_soc, 3);
    for it = 1:n_iter
        qn = q;
        for t = 1:H
            if t == H
                vnext = vT;
            else
                vnext = zeros(n_soc, 1);
                for s = 1:n_soc
                    qq = squeeze(q(t+1, s, :))';
                    qq(~valid(s, :)) = -Inf;
                    vnext(s) = max(qq);
                end
            end
            for s = 0:n_soc-1
                for k = 1:3
                    if ~valid(s+1, k), continue; end
                    a = acts(k);
                    rew = -step_cost(prices(t), a, e, eta);
                    qn(t, s+1, k) = q(t, s+1, k) + ...
                        alpha * (rew + vnext(s + a + 1) - q(t, s+1, k));
                end
            end
        end
        q = qn;
    end

    lo = min(prices) + (max(prices) - min(prices)) / 3;
    hi = max(prices) - (max(prices) - min(prices)) / 3;

    [ls, la, lc] = rollout('learned');
    [gs, ga, gc] = rollout('greedy');

    r = struct('prices', prices, 'q', q, 'learned_soc', ls, 'learned_action', la, ...
        'greedy_soc', gs, 'greedy_action', ga, 'learned_cost', lc, ...
        'greedy_cost', gc, 'n_soc', n_soc, 'soc0', soc0, 'output_csv', '');

    if ~isempty(outCsv)
        d = fileparts(outCsv);
        if ~isempty(d) && ~exist(d, 'dir'), mkdir(d); end
        fid = fopen(outCsv, 'w');
        fprintf(fid, 'hour,price,learned_action,learned_soc_end,greedy_action,greedy_soc_end\n');
        for t = 1:H
            fprintf(fid, '%d,%.2f,%d,%d,%d,%d\n', t-1, prices(t), la(t), ls(t+1), ga(t), gs(t+1));
        end
        fclose(fid);
        r.output_csv = outCsv;
    end

    function [soc, act, cost] = rollout(kind)
        soc = zeros(H+1, 1); act = zeros(H, 1);
        soc(1) = soc0; cost = 0;
        for tt = 1:H
            s0 = soc(tt);
            if strcmp(kind, 'learned')
                qq = squeeze(q(tt, s0+1, :))';
                qq(~valid(s0+1, :)) = -Inf;
                [~, kk] = max(qq);
                a0 = acts(kk);
            else
                a0 = 0;
                if prices(tt) <= lo && s0 < n_soc-1
                    a0 = 1;
                elseif prices(tt) >= hi && s0 > 0
                    a0 = -1;
                end
            end
            act(tt) = a0;
            soc(tt+1) = s0 + a0;
            cost = cost + step_cost(prices(tt), a0, e, eta);
        end
        cost = cost - termValue * (soc(H+1) - soc0);
    end
end

function c = step_cost(price, a, e, eta)
    if a > 0
        g = e / eta;
    elseif a < 0
        g = -e * eta;
    else
        g = 0;
    end
    c = price * g;
end
