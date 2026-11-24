# KNIME Viz Toolkit (`knime-viz-toolkit`)

[English](#english) | [中文说明](#中文说明)

---

## 中文说明

**`knime-viz-toolkit`** 是一个纯 Python 工具包，可直接读取**已执行的 KNIME 工作流（`.knwf` 压缩包或解压后的工作流目录）**中的节点配置与底层数据表，自动将 KNIME 原生图表节点（Bar Chart、Line Plot、Scatter Plot、Box Plot、Heatmap、Pie Chart、Scatter Matrix、Histogram）以及建模评估节点（Numeric Scorer、k-Means、Regression / Random Forest Predictor）渲染为 **300 DPI 出版级高清图表（PNG / SVG / PDF）**，并内置完整的 **AI Agent 接口（MCP Server + OpenAI / Anthropic Function Calling + CLI JSON 模式）**。

### 核心特性

- **零 KNIME / 零 Java / 零 pandas 依赖**：纯 Python 原生解码 KNIME 二进制表格式（`DefaultTableStoreFormat` / `container_12`、Xerial Snappy / GZIP 压缩、`rearrange_columns_table`、`wrapped_table`、`new_spec_table`、`concatenate_table`、`joined_table` 等）。
- **自动读取 KNIME 图表节点并高清重绘**：自动识别 KNIME 工作流中的所有可视化节点、`settings.xml` 轴配置、聚合方式、节点批注和 `Color Manager` 配色，自动优化配色、字体（自动兼容中英文防乱码）、网格线、趋势线/移动平均线、数值标签、千分位与防重叠排版。
- **自动合成建模诊断图**：自动读取 `Numeric Scorer` 生成多模型指标对比图（R² / MAE / RMSE）、读取 `k-Means` 生成聚类分布双联图、读取 `Predictor` 节点生成实际值 vs 预测值 + 残差诊断图。
- **内置 6 套出版级主题**：
  - `editorial`：咨询/出版风（深海军蓝 + 青绿 + 珊瑚红 + 琥珀黄）
  - `academic`：极简学术/课程汇报风（钢蓝 + 暖红 + 森林绿，清爽无杂物）
  - `nature`：科研期刊风（Okabe-Ito 色盲友好调色板）
  - `presentation_dark`：深色大屏 PPT 主题（深午夜蓝灰底色 + 高对比亮色系）
  - `dark_transparent`：**透明底深色 PPT 专用主题**（纯透明 RGBA 背景 + 亮白文字 + 半透明网格 + 磨砂图例，直接拖入任意深色/渐变 PPT 无违和感）
  - `knime_enhanced`：保留上游 KNIME `Color Manager` 配色，同时升级为 300 DPI 现代排版
- **多形态 AI Agent 接口**：
  1. **原生 MCP Server**（`knime-viz-mcp` / `knime-viz mcp`）：直接接入 Claude Desktop、Cursor、Antigravity 等支持 Model Context Protocol 的 AI 客户端。
  2. **OpenAI / Gemini / DeepSeek / Anthropic Tool Schema & Dispatcher**：`KnimeVizAgentToolkit` 提供标准 JSON Schema 工具声明、`call_tool()` / `call_tool_json()` 统一调度，以及可选的 `include_base64=True` 供多模态 Agent 视觉自检。
  3. **AI 友好 CLI（`--json`）**：每条命令均支持 `--json` 结构化输出，方便命令行 Agent 直接调用。

### 快速安装

```bash
cd knime-viz-toolkit
pip install -e .

# 如需启用 MCP Server（如当前环境未安装 mcp）
pip install -e ".[mcp]"
```

### 快速上手

#### 1. 命令行（CLI）

```bash
# 查看工作流中的所有节点、图表节点、Scorer 与 k-Means 摘要
knime-viz inspect path/to/workflow_EXECUTED.knwf

# 一键将整个工作流的所有图表节点 + 模型分析图导出为 300 DPI 高清图
knime-viz render path/to/workflow_EXECUTED.knwf -o ./out_charts --theme editorial

# 仅渲染单个 KNIME 节点（如 #13 Scatter Plot）并自定义标题
knime-viz render-node path/to/workflow_EXECUTED.knwf 13 -o ./temp_vs_cnt.png --theme academic --title "Temperature vs. Daily Rentals"

# 从任意数据节点（即使 KNIME 里没连画图节点！）自由生图
knime-viz custom path/to/workflow_EXECUTED.knwf 4 --kind correlation --value cnt -o ./corr.png

# AI Agent 命令行 JSON 模式
knime-viz inspect path/to/workflow_EXECUTED.knwf --json
```

#### 2. Python API

```python
from knime_viz_toolkit import KnimeWorkflow, render_workflow, render_node

# 一行代码批量出图
results = render_workflow(
    "Bike_Sharing_Master_Workflow_EXECUTED.knwf",
    output_dir="./out_charts",
    theme="editorial",
    dpi=300,
)
for r in results:
    print(r.chart_kind, "->", r.output_path)

# 直接读取任意 KNIME 节点数据表
with KnimeWorkflow("Bike_Sharing_Master_Workflow_EXECUTED.knwf") as wf:
    table = wf.read_node_table(4)  # Math Formula (#4)
    print(table.shape, table.columns)
    print(table.head(5))
```

#### 3. AI Agent 接口集成

##### 方式 A：MCP Server（Claude Desktop / Cursor / Antigravity）

参考 [`examples/mcp_client_config.json`](examples/mcp_client_config.json)：

```json
{
  "mcpServers": {
    "knime-viz-toolkit": {
      "command": "knime-viz-mcp"
    }
  }
}
```

##### 方式 B：OpenAI / Anthropic / Gemini Function Calling

```python
from knime_viz_toolkit import KnimeVizAgentToolkit

toolkit = KnimeVizAgentToolkit()

# 传给 OpenAI / Gemini / DeepSeek API 的 tools 参数
openai_tools = toolkit.get_openai_tools()

# 传给 Anthropic Claude API 的 tools 参数
anthropic_tools = toolkit.get_anthropic_tools()

# 当模型返回 tool_call 时直接调度执行
res = toolkit.call_tool(
    "render_node_chart",
    {
        "workflow_path": "Bike_Sharing_Master_Workflow_EXECUTED.knwf",
        "node_id": 13,
        "output_path": "out/scatter.png",
        "theme": "editorial",
        "include_base64": False,
    },
)
```

---

## English

**`knime-viz-toolkit`** is a pure-Python package that reads executed KNIME workflows (`.knwf` archives or unpacked workflow directories), natively decodes KNIME's internal binary data tables without requiring a KNIME or Java installation, and automatically renders publication-grade 300-DPI charts (PNG / SVG / PDF) with built-in AI Agent interfaces (MCP Server, OpenAI/Anthropic tool calling, and JSON CLI).

### Supported KNIME Nodes

| Category | KNIME Node Types | Output |
|---|---|---|
| Visualization | `Bar Chart`, `Line Plot`, `Scatter Plot`, `Box Plot`, `Heatmap`, `Pie Chart`, `Scatter Matrix`, `Histogram` | Automatic 300-DPI charts honoring axis labels, aggregations, limits, and `Color Manager` maps |
| Analytics (Auto-Synthesized) | `Numeric Scorer`, `k-Means`, `Regression Predictor`, `Random Forest Predictor` | Multi-model R²/MAE/RMSE comparison, k-Means cluster regimes, Actual-vs-Predicted & residual diagnostics |
| Arbitrary Data Nodes | `CSV Reader`, `GroupBy`, `Math Formula`, `Row Filter`, `Partitioning`, `Sorter`, `Unpivot`, etc. | Direct table decoding, chart recommendations (`suggest_charts`), and custom chart synthesis (`render_custom_chart`) |

### Exposed AI Agent Tools

1. `inspect_workflow` — Full workflow topology, node states, chart nodes, scorers, and k-Means summaries
2. `list_chart_nodes` — Extracted normalized `ChartSpec` list for every visualizable node
3. `read_node_data` — Decoded table schema, column summary statistics, and preview rows from any executed node
4. `suggest_charts` — Automatic chart recommendations for any executed data node
5. `render_node_chart` — Render a specific KNIME chart or analytics node with optional theme/title/label overrides
6. `render_workflow_charts` — Batch-render an entire workflow + write `manifest.json`
7. `render_custom_chart` — Synthesize any supported chart type from any executed KNIME data node
8. `list_themes` — Inspect available themes and palettes

### Running Tests

```bash
python -m unittest discover -s tests -v
```

### License

MIT
