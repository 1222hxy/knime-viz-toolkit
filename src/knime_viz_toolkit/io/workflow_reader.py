"""KNIME workflow (.knwf / unpacked folder) parser and node data loader."""

from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ..models import (
    ChartKind,
    ColumnSpec,
    KMeansResult,
    NodeConnection,
    NodeInfo,
    NumericScorerResult,
    WorkflowSummary,
)
from .table import KnimeTable
from .table_decoder import NS, KnimeTableRegistry, WorkflowSource, java_argb_to_hex

CHART_FACTORY_MAP: dict[str, ChartKind] = {
    "org.knime.base.views.node.barchart.BarChartNodeFactory": "bar",
    "org.knime.base.views.node.lineplot.LinePlotNodeFactory": "line",
    "org.knime.base.views.node.scatterplot.ScatterPlotNodeFactory": "scatter",
    "org.knime.base.views.node.boxplot.BoxPlotNodeFactory": "box",
    "org.knime.base.views.node.heatmap.HeatmapNodeFactory": "heatmap",
    "org.knime.base.views.node.piechart.PieChartNodeFactory": "pie",
    "org.knime.base.views.node.histogram.HistogramNodeFactory": "histogram",
    "org.knime.base.node.viz.plotter.scattermatrix.ScatterMatrixNodeFactory": "scatter_matrix",
    # Legacy JS Views support
    "org.knime.js.base.node.viz.plotter.line.LinePlotNodeFactory": "line",
    "org.knime.js.base.node.viz.plotter.scatterSelectionAppender.ScatterPlotNodeFactory": "scatter",
    "org.knime.js.base.node.viz.plotter.box.BoxPlotNodeFactory": "box",
    "org.knime.js.base.node.viz.plotter.bar.GroupedBarChartNodeFactory": "bar",
    "org.knime.js.base.node.viz.plotter.pie.PieChartNodeFactory": "pie",
    "org.knime.js.base.node.viz.heatmap.HeatmapNodeFactory": "heatmap",
}

ANALYTICS_FACTORY_KEYWORDS = (
    "NumericScorer",
    "ClusterAssigner",
    "KMeans",
    "RandomForestRegressionPredictor",
    "RegressionPredictor",
)


def _xml_config_to_dict(elem: ET.Element) -> dict[str, Any]:
    """Recursively convert a KNIME XMLConfig `<config>` element into plain Python dicts/lists."""
    result: dict[str, Any] = {}
    entries = elem.findall("k:entry", NS)
    configs = elem.findall("k:config", NS)

    # Detect KNIME array-style config: has array-size entry and numeric keys 0..n-1
    keys = [e.get("key", "") for e in entries]
    if "array-size" in keys and not configs:
        size = int(next(e.get("value", "0") for e in entries if e.get("key") == "array-size"))
        arr: list[Any] = []
        indexed = {e.get("key"): _parse_entry_value(e) for e in entries if e.get("key") != "array-size"}
        for i in range(size):
            if str(i) in indexed:
                arr.append(indexed[str(i)])
        return {"_array": arr}

    for e in entries:
        k = e.get("key")
        if k is not None:
            result[k] = _parse_entry_value(e)
    for c in configs:
        k = c.get("key")
        if k is not None:
            sub = _xml_config_to_dict(c)
            if set(sub.keys()) == {"_array"}:
                result[k] = sub["_array"]
            else:
                result[k] = sub
    return result


def _parse_entry_value(e: ET.Element) -> Any:
    if e.get("isnull", "false").lower() == "true":
        return None
    val = e.get("value", "")
    etype = e.get("type", "xstring")
    if etype == "xboolean":
        return val.lower() == "true"
    if etype in ("xint", "xlong"):
        try:
            return int(val)
        except ValueError:
            return val
    if etype in ("xdouble", "xfloat"):
        try:
            return float(val)
        except ValueError:
            return val
    return val


def _clean_knime_text(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("%%00010", "\n").replace("%%00013", "").strip()


class KnimeWorkflow:
    """High-level interface to an executed or unexecuted KNIME workflow."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.source = WorkflowSource(self.path)
        self.registry = KnimeTableRegistry(self.source)
        self.prefix: str = self._detect_workflow_prefix()
        self.workflow_name: str = self.prefix or self.path.stem
        self.nodes: dict[int, NodeInfo] = {}
        self.connections: list[NodeConnection] = []
        self._node_dirs: dict[int, str] = {}
        self._color_maps_by_node: dict[int, tuple[str, dict[str, str]]] = {}
        self._scorers: list[NumericScorerResult] = []
        self._kmeans: list[KMeansResult] = []
        self._parse_workflow()

    @classmethod
    def load(cls, path: str | Path) -> "KnimeWorkflow":
        return cls(path)

    def __enter__(self) -> "KnimeWorkflow":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self.source.close()

    def _detect_workflow_prefix(self) -> str:
        wf_files = [e for e in self.source.entries if e == "workflow.knime" or e.endswith("/workflow.knime")]
        if not wf_files:
            raise ValueError(f"No workflow.knime found inside {self.path}")
        # Top-level workflow.knime has the fewest slashes
        top = min(wf_files, key=lambda s: s.count("/"))
        return top[: -len("/workflow.knime")] if "/" in top else ""

    def _rel(self, subpath: str) -> str:
        return f"{self.prefix}/{subpath}" if self.prefix else subpath

    def _parse_workflow(self) -> None:
        wf_xml_path = self._rel("workflow.knime")
        root = ET.fromstring(self.source.read_bytes(wf_xml_path))

        # Parse connections
        for conn_cfg in root.findall('.//k:config[@key="connections"]/k:config', NS):
            s = conn_cfg.find('k:entry[@key="sourceID"]', NS)
            sp = conn_cfg.find('k:entry[@key="sourcePort"]', NS)
            d = conn_cfg.find('k:entry[@key="destID"]', NS)
            dp = conn_cfg.find('k:entry[@key="destPort"]', NS)
            if s is not None and d is not None:
                self.connections.append(
                    NodeConnection(
                        source_id=int(s.get("value", "0")),
                        source_port=int(sp.get("value", "1")) if sp is not None else 1,
                        dest_id=int(d.get("value", "0")),
                        dest_port=int(dp.get("value", "1")) if dp is not None else 1,
                    )
                )

        upstream_map: dict[int, list[int]] = {}
        downstream_map: dict[int, list[int]] = {}
        for c in self.connections:
            upstream_map.setdefault(c.dest_id, []).append(c.source_id)
            downstream_map.setdefault(c.source_id, []).append(c.dest_id)

        # Parse top-level nodes
        for ncfg in root.findall('.//k:config[@key="nodes"]/k:config', NS):
            nid_e = ncfg.find('k:entry[@key="id"]', NS)
            sfile_e = ncfg.find('k:entry[@key="node_settings_file"]', NS)
            if nid_e is None or sfile_e is None:
                continue
            nid = int(nid_e.get("value", "0"))
            sfile = sfile_e.get("value", "").replace("\\", "/")
            full_settings = self._rel(sfile)
            if not self.source.exists(full_settings):
                continue

            node_dir = full_settings.rsplit("/", 1)[0]
            folder_name = node_dir.rsplit("/", 1)[-1]
            self._node_dirs[nid] = node_dir

            sroot = ET.fromstring(self.source.read_bytes(full_settings))
            fac_e = sroot.find('k:entry[@key="factory"]', NS)
            factory = fac_e.get("value", "") if fac_e is not None else ""
            name_e = sroot.find('k:entry[@key="name"]', NS)
            name = name_e.get("value", folder_name) if name_e is not None else folder_name
            state_e = sroot.find('k:entry[@key="state"]', NS)
            state = state_e.get("value", "UNKNOWN") if state_e is not None else "UNKNOWN"
            ann_e = sroot.find('.//k:config[@key="nodeAnnotation"]/k:entry[@key="text"]', NS)
            annotation = _clean_knime_text(ann_e.get("value") if ann_e is not None else "")

            msg_e = sroot.find('.//k:config[@key="node_message"]/k:entry[@key="message"]', NS)
            mtype_e = sroot.find('.//k:config[@key="node_message"]/k:entry[@key="type"]', NS)
            warning = None
            if msg_e is not None and msg_e.get("value"):
                mtype = mtype_e.get("value", "INFO") if mtype_e is not None else "INFO"
                warning = f"[{mtype}] {msg_e.get('value')}"

            view_elem = sroot.find('k:config[@key="view"]', NS)
            model_elem = sroot.find('k:config[@key="model"]', NS)
            view_cfg = _xml_config_to_dict(view_elem) if view_elem is not None else {}
            model_cfg = _xml_config_to_dict(model_elem) if model_elem is not None else {}

            chart_kind = CHART_FACTORY_MAP.get(factory)
            is_chart = chart_kind is not None
            is_analytics = any(k in factory for k in ANALYTICS_FACTORY_KEYWORDS)

            has_out = self.source.exists(f"{node_dir}/port_1/data.xml") or self.source.exists(
                f"{node_dir}/port_1/data.zip"
            )
            has_internal = self.source.exists(f"{node_dir}/internalTables/object_0/data.xml")

            info = NodeInfo(
                node_id=nid,
                folder_name=folder_name,
                name=name,
                factory=factory,
                state=state,
                annotation=annotation,
                warning=warning,
                is_chart_node=is_chart,
                is_analytics_node=is_analytics,
                chart_kind=chart_kind,
                has_output_table=has_out,
                has_internal_table=has_internal,
                upstream_ids=upstream_map.get(nid, []),
                downstream_ids=downstream_map.get(nid, []),
                view_config=view_cfg,
                model_config_raw=model_cfg,
            )
            self.nodes[nid] = info

            # Parse Color Manager
            if "ColorManager" in factory:
                self._extract_color_manager(nid, model_cfg)

        # Second pass: parse analytics nodes (Numeric Scorer, k-Means) now that all nodes exist
        for nid, node in sorted(self.nodes.items()):
            if "NumericScorer" in node.factory:
                sc = self._parse_numeric_scorer(nid)
                if sc is not None:
                    self._scorers.append(sc)
            elif "KMeans" in node.factory or "k_Means" in node.folder_name:
                km = self._parse_kmeans(nid)
                if km is not None:
                    self._kmeans.append(km)

    def _extract_color_manager(self, nid: int, model_cfg: dict[str, Any]) -> None:
        col = model_cfg.get("selected_column")
        values = model_cfg.get("values")
        if not col or not isinstance(values, dict):
            return
        cmap: dict[str, str] = {}
        for k, v in values.items():
            if k == "array-size" or not isinstance(v, dict):
                continue
            str_val = None
            for sub_v in v.values():
                if isinstance(sub_v, dict) and "StringCell" in sub_v:
                    str_val = str(sub_v["StringCell"])
                    break
            argb = model_cfg.get(k)
            if str_val is not None and isinstance(argb, int):
                cmap[str_val] = java_argb_to_hex(argb)
        if cmap:
            self._color_maps_by_node[nid] = (str(col), cmap)

    def _infer_upstream_model_label(self, scorer_id: int) -> str:
        """Walk 1-2 hops upstream of a Numeric Scorer to create a readable model name."""
        node = self.nodes.get(scorer_id)
        if node and node.annotation:
            first_line = node.annotation.splitlines()[0].strip()
            if first_line:
                return first_line
        visited: list[str] = []
        queue = list(node.upstream_ids) if node else []
        seen = {scorer_id}
        depth = 0
        while queue and depth < 3:
            nxt: list[int] = []
            for uid in queue:
                if uid in seen:
                    continue
                seen.add(uid)
                unode = self.nodes.get(uid)
                if unode:
                    if unode.annotation:
                        visited.append(unode.annotation.splitlines()[0].strip())
                    else:
                        visited.append(unode.name)
                    nxt.extend(unode.upstream_ids)
            queue = nxt
            depth += 1
        return " ← ".join(visited[:2]) if visited else f"Scorer #{scorer_id}"

    def _parse_numeric_scorer(self, nid: int) -> NumericScorerResult | None:
        ndir = self._node_dirs[nid]
        ipath = f"{ndir}/internal/internals.xml.gz"
        if not self.source.exists(ipath):
            return None
        try:
            root = ET.fromstring(gzip.decompress(self.source.read_bytes(ipath)))
        except Exception:
            return None
        raw: dict[str, Any] = {}
        for e in root.findall("k:entry", NS):
            k = e.get("key")
            v = e.get("value")
            if k is None:
                continue
            try:
                raw[k] = round(float(v), 6)  # type: ignore[arg-type]
            except Exception:
                raw[k] = v
        node = self.nodes[nid]
        label = self._infer_upstream_model_label(nid)
        return NumericScorerResult(
            node_id=nid,
            label=label,
            annotation=node.annotation,
            upstream_model=label,
            r2=raw.get("R2"),
            mae=raw.get("meanAbsError"),
            rmse=raw.get("rmsd"),
            mse=raw.get("meanSquaredError"),
            mape=raw.get("MAPE"),
            raw_metrics=raw,
        )

    def _parse_kmeans(self, nid: int) -> KMeansResult | None:
        ndir = self._node_dirs[nid]
        ipath = f"{ndir}/internal/kMeansInternalSettings"
        if not self.source.exists(ipath):
            return None
        raw = self.source.read_bytes(ipath)
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
        try:
            kroot = ET.fromstring(raw)
        except Exception:
            return None

        cov = [
            int(e.get("value", "0"))
            for e in kroot.findall('k:config[@key="clusterCoverage"]/k:entry', NS)
            if e.get("key") != "array-size"
        ]
        fnames = [
            e.get("value", "")
            for e in kroot.findall('k:config[@key="FeatureNames"]/k:entry', NS)
            if e.get("key") != "array-size" and e.get("value")
        ]
        centroids: dict[str, dict[str, float]] = {}
        for i in range(len(cov)):
            vals = [
                round(float(e.get("value", "0")), 6)
                for e in kroot.findall(f'k:config[@key="kMeansCluster{i}"]/k:entry', NS)
                if e.get("key") != "array-size"
            ]
            centroids[f"cluster_{i}"] = dict(zip(fnames, vals[: len(fnames)]))
        node = self.nodes[nid]
        return KMeansResult(
            node_id=nid,
            label=node.annotation.splitlines()[0] if node.annotation else f"k-Means (#{nid})",
            features=fnames,
            coverage=cov,
            centroids=centroids,
        )

    def get_upstream_connection(self, node_id: int, dest_port: int = 1) -> NodeConnection | None:
        for c in self.connections:
            if c.dest_id == node_id and c.dest_port == dest_port:
                return c
        # Fallback to first incoming connection on any port
        for c in self.connections:
            if c.dest_id == node_id:
                return c
        return None

    def get_upstream_color_map(self, node_id: int, target_column: str | None = None) -> dict[str, str]:
        """Search upstream nodes (up to 4 hops) for a Color Manager or spec.xml color map."""
        visited: set[int] = set()
        queue: list[int] = [node_id]
        hops = 0
        while queue and hops <= 4:
            nxt: list[int] = []
            for cur in queue:
                if cur in visited:
                    continue
                visited.add(cur)
                if cur in self._color_maps_by_node:
                    col, cmap = self._color_maps_by_node[cur]
                    if target_column is None or col == target_column:
                        return dict(cmap)
                # Also check port_1 spec.xml color handler
                ndir = self._node_dirs.get(cur)
                if ndir and self.source.exists(f"{ndir}/port_1/spec.xml"):
                    for col_spec in self.registry.get_spec(f"{ndir}/port_1"):
                        if col_spec.color_map and (target_column is None or col_spec.name == target_column):
                            return dict(col_spec.color_map)
                ninfo = self.nodes.get(cur)
                if ninfo:
                    nxt.extend(ninfo.upstream_ids)
            queue = nxt
            hops += 1
        return {}

    def read_node_spec(self, node_id: int, port: int = 1) -> list[ColumnSpec]:
        ndir = self._node_dirs.get(node_id)
        if not ndir:
            return []
        port_dir = f"{ndir}/port_{port}"
        if self.source.exists(f"{port_dir}/spec.xml"):
            return self.registry.get_spec(port_dir)
        return []

    def read_node_table(self, node_id: int, port: int = 1) -> KnimeTable:
        """Read the executed output `KnimeTable` of `node_id` (or its input table if it's a sink/chart node)."""
        if node_id not in self.nodes:
            raise KeyError(f"Node #{node_id} not found in workflow '{self.workflow_name}'")
        ndir = self._node_dirs[node_id]
        port_dir = f"{ndir}/port_{port}"
        if self.source.exists(f"{port_dir}/data.xml") or self.source.exists(f"{port_dir}/data.zip"):
            return self.registry.read_table_dir(port_dir)

        # Chart nodes often store no output port; read upstream node's connected output port first
        conn = self.get_upstream_connection(node_id, dest_port=1)
        if conn is not None:
            up_dir = self._node_dirs.get(conn.source_id)
            if up_dir:
                up_port_dir = f"{up_dir}/port_{conn.source_port}"
                if self.source.exists(f"{up_port_dir}/data.xml") or self.source.exists(f"{up_port_dir}/data.zip"):
                    return self.registry.read_table_dir(up_port_dir)

        # Fallback to internalTables/object_0 if present (e.g., Scatter Plot / Line Plot view cache)
        int_dir = f"{ndir}/internalTables/object_0"
        if self.source.exists(f"{int_dir}/data.xml"):
            return self.registry.read_table_dir(int_dir)

        node = self.nodes[node_id]
        raise ValueError(
            f"Node #{node_id} ({node.name}) has no readable executed table data (state={node.state}). "
            "Execute and save the workflow with data in KNIME first."
        )

    def get_input_table(self, node_id: int, input_port: int = 1) -> tuple[KnimeTable, int]:
        """Read the `KnimeTable` entering `node_id` on `input_port`, returning `(table, source_node_id)`."""
        conn = self.get_upstream_connection(node_id, dest_port=input_port)
        if conn is not None:
            tbl = self.read_node_table(conn.source_id, port=conn.source_port)
            return tbl, conn.source_id
        # Fallback to node's own table
        return self.read_node_table(node_id, port=1), node_id

    @property
    def scorers(self) -> list[NumericScorerResult]:
        return list(self._scorers)

    @property
    def kmeans_results(self) -> list[KMeansResult]:
        return list(self._kmeans)

    def list_chart_nodes(self) -> list[NodeInfo]:
        return [n for _, n in sorted(self.nodes.items()) if n.is_chart_node]

    def list_analytics_nodes(self) -> list[NodeInfo]:
        return [n for _, n in sorted(self.nodes.items()) if n.is_analytics_node]

    def list_data_nodes(self) -> list[NodeInfo]:
        return [n for _, n in sorted(self.nodes.items()) if n.has_output_table]

    def summarize(self) -> WorkflowSummary:
        nodes_sorted = [n for _, n in sorted(self.nodes.items())]
        executed = sum(1 for n in nodes_sorted if n.state == "EXECUTED")
        warnings = [f"#{n.node_id} ({n.name}): {n.warning}" for n in nodes_sorted if n.warning]
        return WorkflowSummary(
            workflow_path=str(self.path.resolve()),
            workflow_name=self.workflow_name,
            total_nodes=len(nodes_sorted),
            executed_nodes=executed,
            unexecuted_nodes=len(nodes_sorted) - executed,
            connections_count=len(self.connections),
            chart_nodes=self.list_chart_nodes(),
            analytics_nodes=self.list_analytics_nodes(),
            data_nodes=self.list_data_nodes(),
            scorers=self.scorers,
            kmeans=self.kmeans_results,
            warnings=warnings,
        )
