# 参数表 CSV 导出约定与示例脚本

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MATLAB R2021b+](https://img.shields.io/badge/MATLAB-R2021b+-orange.svg)](https://www.mathworks.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../../LICENSE)

**Read, check, and write a Simulink parameter table as CSV (Python + MATLAB).**

把模型里要用的参数收成一张表：名字、数值、单位、说明，再加上参数放在哪、是什么类型、允许的范围。表可以来自手写 CSV，也可以来自结构体；检查通过后写成固定列序的 CSV，再读回来，类型和文字都不变。示例是一台课堂用的直流电机转速环，参数全是合成的，没有装置记录，也没有学生信息。

Simulink 本身不参与。Python 只用标准库。MATLAB 只用基础语言，不加载 Simulink。检查通过之后，若机器上有 Simulink，再用 `value_text` 调 `set_param`，或把 `workspace` / `base` 里的值写进工作区。这一步写在文末，示例脚本不会调用它。

## CSV schema

写出的文件是 UTF-8、逗号分隔、无 BOM，列序固定：

```text
name,value,unit,description,scope,path,dtype,minimum,maximum,group
```

| Column | Required | Meaning |
|--------|----------|---------|
| `name` | yes | MATLAB 标识符，1–63 字符：字母或下划线开头，其后为字母、数字、下划线 |
| `value` | yes | 按 `dtype` 书写的文字。见下面的文法 |
| `unit` | no | 空，或由 `.` `/` `^` `-` `·` 分开的单位记号。首段可以是 `1`、`%` 或字母开头的词，后面的段还可以是整数，所以 `1/s`、`N.m/A`、`kg.m^2` 都可以。不能有空格 |
| `description` | no | 说明，最长 240 个字符，不能含换行。逗号可以，写出时会加引号 |
| `scope` | no | `model`、`block`、`mask`、`workspace`、`base`。空着等于 `base` |
| `path` | 视 scope | `model` 和 `workspace` 要模型名；`block` 和 `mask` 要至少带一个 `/` 的块路径，段内可以有空格，如 `dc_speed/Speed Ref`；`base` 必须空 |
| `dtype` | no | `double`、`int`、`logical`、`string`。空着时按 `value` 的写法推断 |
| `minimum`, `maximum` | no | 含端点的数值范围，只允许用于 `double` 和 `int`。空着表示不限制 |
| `group` | no | 分组标签，如 `plant`、`controller`。空或标识符加连字符，最长 32 |

同一张表里的键是 `scope|path|name`。`workspace` 里的 `Kp` 和 `base` 里的 `Kp` 可以同时存在。后出现的重复键算错误。

读入时表头忽略大小写、空格和下划线。中英文别名都可以：

| Column | Also accepted |
|--------|----------------|
| `name` | `param`, `parameter`, `参数`, `参数名` |
| `value` | `val`, `值`, `数值` |
| `unit` | `units`, `单位` |
| `description` | `desc`, `comment`, `说明`, `描述` |
| `scope` | `target`, `作用域` |
| `path` | `block`, `block_path`, `路径` |
| `dtype` | `type`, `data_type`, `类型` |
| `minimum` | `min`, `lower`, `下限` |
| `maximum` | `max`, `upper`, `上限` |
| `group` | `category`, `分组`, `类别` |

`#` 开头的行和空行会跳过。表头里分号比逗号多时，整张表按分号分隔。字段两端的空白会去掉。UTF-8 BOM 可以有。

### Value grammar

| `dtype` | Accepted text | Canonical text |
|---------|----------------|----------------|
| `double` | `1`、`1.5`、`.5`、`1e-6`、`+2.5e-3`。必须有限 | 16 位有效数字的短写法；16 位不够往返时用 17 位。`0.0001` 仍是 `0.0001`，`1e-6` 写成 `1e-06` |
| `int` | 可选正负号加数字，不写小数点。绝对值不超过 `2^53` | 去掉前导零和正号，如 `007` 写成 `7` |
| `logical` | `true` `false` `yes` `no` `on` `off` `1` `0`，不区分大小写 | `true` 或 `false` |
| `string` | 其余文字，最长 240，不能含换行。可以是空串，但必须显式写 `dtype=string` | 原文（两端空白已去掉） |

`dtype` 空着时：`true`/`false`/`yes`/`no`/`on`/`off` 推断为 `logical`；纯整数字面量推断为 `int`；其余数推断为 `double`；对不上就推断为 `string`。因此 `10` 是整数，`10.0` 或 `dtype=double` 才是实数。`1` 和 `0` 在没写类型时是整数，不是逻辑值。

## Dependencies

| Runtime | Requirements |
|---------|----------------|
| Python 3.10+ | 标准库即可（`csv`）。不需要 numpy、pandas |
| MATLAB R2021b+ | 基础 MATLAB。不需要 Simulink，也不需要其它工具箱 |

## Quick start

在仓库根目录执行。

### Python

```bash
python tools/simulink-param-export/examples/run_demo.py
```

脚本读取 `examples/data/dc_speed_params.csv`。这个示例故意用了中文表头和分号，用来模仿一份不规范的导出。规范 CSV 写到 `examples/output/simulink_param_export_demo.csv`（该目录已 gitignore）。

在自己的脚本里调用：

```python
import sys
sys.path.insert(0, "tools/simulink-param-export/python")
from simulink_param_export import simulink_param_export

result = simulink_param_export(
    "tools/simulink-param-export/examples/data/dc_speed_params.csv",
    output_csv="tools/simulink-param-export/examples/output/params.csv",
)
print(result.n_rows, result.workspace["dc_speed"]["Kp"])
print(result.table_text)
```

### MATLAB

一行：

```matlab
addpath('tools/simulink-param-export/matlab'); demo_simulink_param_export
```

或先进入函数目录：

```matlab
cd('tools/simulink-param-export/matlab')
demo_simulink_param_export
```

图没有；结果是一张文本表和一份规范 CSV，路径为 `examples/output/simulink_param_export_demo.csv`。

换一组内存中的参数：

```matlab
row = struct('name', 'Kp', 'value', 1.8, 'dtype', 'double', ...
    'scope', 'workspace', 'path', 'dc_speed', 'minimum', 0, 'maximum', 100);
result = simulink_param_export(row, 'output_csv', 'kp.csv', 'strict', true);
```

## Parameters

Python 关键字与 MATLAB 名值对使用同一套名字。输入三选一：位置参数、`rows`、`csv_path`。

| Name | Default | Description |
|------|---------|-------------|
| `source` | — | CSV 路径、一条记录，或记录列表。MATLAB 里这是第一个位置参数 |
| `rows` | — | 与位置参数二选一的记录数组 |
| `csv_path` | — | 与位置参数二选一的 CSV 路径 |
| `output_csv` | 不写文件 | 规范 CSV 的输出路径。父目录不存在时会创建 |
| `strict` | `true` | 为真时，第一条行错误用 `ValueError`（MATLAB 为 `simulink_param_export:BadTable`）抛出。为假时，错误行不进入 `rows`，其余照常写出 |

表头对不上（缺 `name` 或 `value`、未知列、重复列、引号没关上）时，不论 `strict` 都直接报错。

## API

两侧返回同一组字段。

| Field | Meaning |
|-------|---------|
| `rows` | 通过检查的记录，顺序与输入一致 |
| `errors` | 未通过的记录。`strict=true` 且成功时为空。MATLAB 空错误是 1×0 struct |
| `workspace` | `scope=workspace` 的值，先按模型名再按参数名。Python 是字典，MATLAB 是 struct |
| `base` | `scope=base` 的值，参数名到值 |
| `output_csv` | 写出的路径。未写时 Python 为 `None`，MATLAB 为 `''` |
| `n_rows` | `rows` 的条数 |
| `n_errors` | `errors` 的条数 |
| `table_text` | 文本表，列是 name、dtype、value、unit、scope、path、group |
| `assignment_text` | 按名字排序的 workspace 与 base 赋值，用规范文字 |

`rows(i)` 的字段：

| Field | Meaning |
|-------|---------|
| `name`, `scope`, `path`, `dtype`, `unit`, `description`, `group` | 规范后的文字 |
| `value` | 类型化的值。`double` 为浮点，`logical` 为布尔，`string` 为文字。`int` 在 Python 里是 int，在 MATLAB 里是 double（`2^53` 以内精确） |
| `value_text` | 写回 CSV、以及交给 `set_param` 的文字 |
| `minimum`, `maximum` | 边界。Python 无边界为 `None`，MATLAB 无边界为 `NaN` |
| `row_number` | CSV 的物理行号（从 1 计，含注释），或内存记录的序号 |

Python 另外提供薄包装：`read_param_table`、`write_param_table`、`validate_param_table`、`format_param_table`、`format_assignments`、`param_rows_equal`。MATLAB 同目录有 `read_param_table.m`、`write_param_table.m`、`validate_param_table.m`。文本表直接用 `result.table_text`。

块参数和模型参数不会放进 `workspace` 或 `base`。它们留在 `rows` 里，等有 Simulink 时再用 `value_text` 写入。

## Example output

`examples/data/dc_speed_params.csv` 是 17 行合成参数：转速 PI、固定步长、直流电机的 R/L/Kt/Ke/J/B，以及两个基工作区标签。`Decimation` 没写 `dtype`，字面量 `10` 因此是 `int`。`UseFilter` 是 `logical`。`Note` 的说明里有逗号，写出时带引号。

`run_demo.py` 打印：

```text
simulink-param-export: rows=17 errors=0
name         dtype    value      unit         scope      path                   group
Kp           double   1.8        1            workspace  dc_speed               controller
Ki           double   12         1/s          workspace  dc_speed               controller
Ts           double   0.0001     s            model      dc_speed               solver
StopTime     double   2          s            model      dc_speed               solver
Decimation   int      10         1            model      dc_speed               solver
Gain         double   1          1            block      dc_speed/Speed Ref     reference
R            double   0.8        ohm          workspace  dc_speed               plant
L            double   0.005      H            workspace  dc_speed               plant
Kt           double   0.4        N.m/A        workspace  dc_speed               plant
Ke           double   0.4        V/rad/s      workspace  dc_speed               plant
J            double   0.002      kg.m^2       workspace  dc_speed               plant
B            double   0.0002     N.m/rad/s    workspace  dc_speed               plant
UseFilter    logical  true                    mask       dc_speed/Speed PI      controller
FilterHz     double   50         Hz           workspace  dc_speed               controller
ModelName    string   dc_speed                base                              meta
RatedRpm     double   1500       rpm          base                              plant
Note         string   class-demo              base                              meta
workspace dc_speed: B=0.0002, FilterHz=50, J=0.002, Ke=0.4, Ki=12, Kp=1.8, Kt=0.4, L=0.005, R=0.8
base: ModelName=dc_speed, Note=class-demo, RatedRpm=1500
round-trip ok: 17 rows
```

规范文件的三行样子：

```csv
name,value,unit,description,scope,path,dtype,minimum,maximum,group
Kp,1.8,1,Proportional gain of the speed PI,workspace,dc_speed,double,0,100,controller
UseFilter,true,,Enable speed measurement filter,mask,dc_speed/Speed PI,logical,,,controller
Note,class-demo,,"Label, not a measurement",base,,string,,,meta
```

`Ts` 的下限在源文件里写成 `1e-6`，规范文件里是 `1e-06`。两边读入后都是同一个数。

## Pushing into a model

下面这段需要 Simulink，示例不运行它。`result` 是已经检查过的返回值。

```matlab
load_system('dc_speed');
hws = get_param('dc_speed', 'ModelWorkspace');
names = fieldnames(result.workspace.dc_speed);
for k = 1:numel(names)
    hws.assignin(names{k}, result.workspace.dc_speed.(names{k}));
end
for k = 1:numel(result.rows)
    row = result.rows(k);
    if any(strcmp(row.scope, {'block', 'mask', 'model'}))
        set_param(row.path, row.name, row.value_text);
    elseif strcmp(row.scope, 'base')
        assignin('base', row.name, row.value);
    end
end
```

`set_param` 要的是字符，所以用 `value_text`，不要把浮点直接送进去。Python 没有对应的模型对象；`result.workspace` 和 `result.base` 就是普通字典。

## Limitations

- 只接受标量 `double` / `int` / `logical` 和一条 `string`。不写向量、矩阵、结构体或总线
- 不计算表达式。对话框里要保留的公式（例如 `Kp+1`）请设 `dtype=string`，原样放在 `value_text` 里
- 单位只检查记号形状，不换算。`ohm` 和 `V/rad/s` 都能过；带空格的写法不行
- 块路径的每一段必须像名字一样开头，中间可以有空格或连字符。`dc_speed/Speed Ref` 可以，`1/Gain` 不行
- 整数停在 `2^53`。再大的整数不能在 double 里精确表示，表会拒绝
- MATLAB 把 `int` 存在 double 里，把空的 minimum/maximum 存成 `NaN`。Python 用 int 和 `None`。比较时看 `dtype` 和 `value_text`
- 实数的规范拼写沿用各自的 `%.16g`（必要时 17 位）。课堂里的这些数两边一致；很难看的二进制小数，最后一位的写法可能不同，但再读入后数值相同
- 示例是公式和手写常数，不能代替某台装置或某个学生的模型

## FAQ

**只有两列 `name,value` 可以吗？**  
可以。缺省 `scope` 是 `base`，缺省类型按字面量推断。要进模型工作区，请写上 `scope=workspace` 和模型名。

**为什么 `Decimation=10` 变成了 int？**  
这一行没有 `dtype`，而 `10` 是整数字面量。转速给定、电阻这类实数要写 `10.0`，或显式写 `dtype=double`。示例里的 `StopTime` 就是显式的 double，所以 `2` 仍是 double。

**逻辑值为什么不把 `1` 认成 true？**  
推断时 `1` 和 `0` 是整数，避免和增益、计数混在一起。要逻辑值就写 `true`/`false`，或把 `dtype` 设为 `logical`（这时 `1`/`0`/`yes`/`no` 都可以）。

**重复的参数名一定报错吗？**  
同一个 `scope` 和 `path` 下重复才报错。两个模型的工作区可以各有一个 `Kp`。

**需要 Simulink 吗？**  
读写和检查不需要。只有把结果推进已打开的模型时才需要，而且那一段不在示例里运行。

## License

MIT，见仓库 [LICENSE](../../LICENSE)。

## Teaching disclaimer

教学辅助用途：帮助约定参数表的读写和检查，结果不作为工程整定、投运或考核依据。请勿把学生姓名、学号、成绩或未授权的现场模型参数放进示例或提交到仓库。
