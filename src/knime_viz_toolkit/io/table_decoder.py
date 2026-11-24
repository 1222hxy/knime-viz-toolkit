"""Native pure-Python decoder for KNIME executed binary tables.

Supports:
- `container_table_compressed` & `container_table` (`DefaultTableStoreFormat`)
- `rearrange_columns_table` & `rearrange_columns_table_compressed`
- `wrapped_table`
- `new_spec_table`
- `concatenate_table`
- `joined_table`
- KNIME cell types: String, Int, Long, Double, Boolean, LocalDate,
  LocalDateTime, LocalTime, ZonedDateTime, MissingCell.
"""

from __future__ import annotations

import datetime
import io
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from ..models import ColumnSpec
from .snappy import decompress_knime_stream
from .table import KnimeTable

NS = {"k": "http://www.knime.org/2008/09/XMLConfig"}


class WorkflowSource:
    """Unified read-only file access over either a `.knwf` zip or an unpacked directory."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._zip: zipfile.ZipFile | None = None
        if self.path.is_file():
            self._zip = zipfile.ZipFile(self.path, "r")
            self._entries = sorted(n.rstrip("/") for n in self._zip.namelist() if not n.endswith("/"))
        elif self.path.is_dir():
            self._entries = sorted(
                p.relative_to(self.path).as_posix()
                for p in self.path.rglob("*")
                if p.is_file()
            )
        else:
            raise FileNotFoundError(f"KNIME workflow path not found: {self.path}")
        self._entry_set = set(self._entries)

    @property
    def entries(self) -> list[str]:
        return self._entries

    def exists(self, rel_path: str) -> bool:
        return rel_path in self._entry_set

    def read_bytes(self, rel_path: str) -> bytes:
        if self._zip is not None:
            return self._zip.read(rel_path)
        return (self.path / rel_path).read_bytes()

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
            self._zip = None


def java_argb_to_hex(argb: int) -> str:
    """Convert KNIME Java signed 32-bit ARGB integer to `#RRGGBB` hex string."""
    unsigned = argb & 0xFFFFFFFF
    r = (unsigned >> 16) & 0xFF
    g = (unsigned >> 8) & 0xFF
    b = unsigned & 0xFF
    return f"#{r:02X}{g:02X}{b:02X}"


def parse_spec_xml(xml_bytes: bytes) -> list[ColumnSpec]:
    """Parse a KNIME `spec.xml` into a list of `ColumnSpec` objects."""
    root = ET.fromstring(xml_bytes)
    n_entry = root.find('k:entry[@key="number_columns"]', NS)
    ncols = int(n_entry.get("value", "0")) if n_entry is not None else 0
    cols: list[ColumnSpec] = []

    for i in range(ncols):
        ccfg = root.find(f'k:config[@key="column_spec_{i}"]', NS)
        if ccfg is None:
            continue
        cname_e = ccfg.find('k:entry[@key="column_name"]', NS)
        cname = cname_e.get("value", f"col_{i}") if cname_e is not None else f"col_{i}"
        ctype_e = ccfg.find('k:config[@key="column_type"]/k:entry[@key="cell_class"]', NS)
        cclass = ctype_e.get("value", "") if ctype_e is not None else ""

        possible_values: list[str] = []
        pv_cfg = ccfg.find('k:config[@key="column_domain"]/k:config[@key="possible_values"]', NS)
        if pv_cfg is not None:
            for item in pv_cfg.findall("k:config", NS):
                val_e = item.find(".//k:entry[@key='StringCell']", NS)
                if val_e is not None and val_e.get("value") is not None:
                    possible_values.append(val_e.get("value", ""))

        color_map: dict[str, str] = {}
        ch_cfg = ccfg.find('k:config[@key="color_handler"]', NS)
        if ch_cfg is not None:
            # Nominal color model
            cm_cfg = ch_cfg.find('k:config[@key="color_model"]', NS)
            if cm_cfg is not None:
                keys_cfg = cm_cfg.find('k:config[@key="keys"]', NS)
                if keys_cfg is not None:
                    for idx_cfg in keys_cfg.findall("k:config", NS):
                        k_idx = idx_cfg.get("key")
                        if k_idx is None:
                            continue
                        str_e = idx_cfg.find(".//k:entry[@key='StringCell']", NS)
                        col_e = cm_cfg.find(f'k:entry[@key="{k_idx}"]', NS)
                        if str_e is not None and col_e is not None:
                            try:
                                color_map[str_e.get("value", "")] = java_argb_to_hex(int(col_e.get("value", "0")))
                            except ValueError:
                                pass

        cols.append(
            ColumnSpec(
                name=cname,
                cell_class=cclass,
                possible_values=possible_values,
                color_map=color_map,
            )
        )
    return cols


def _read_block(buf: bytes, pos: int) -> tuple[bytes, int]:
    """Read a KNIME BlockableInputStream block terminated by unescaped 0x61."""
    out = bytearray()
    n = len(buf)
    while pos < n:
        b = buf[pos]
        pos += 1
        if b == 0x61:  # BYTE_END_OF_BLOCK
            return bytes(out), pos
        if b == 0x62:  # BYTE_ESCAPE
            if pos >= n:
                raise EOFError("Truncated escape sequence in KNIME data.bin")
            out.append(buf[pos])
            pos += 1
        else:
            out.append(b)
    raise EOFError("Unterminated block in KNIME data.bin")


def _decode_java_utf(b: bytes) -> str:
    if len(b) >= 2:
        ln = struct.unpack_from(">H", b, 0)[0]
        if ln == len(b) - 2:
            return b[2:].decode("utf-8", errors="replace")
    if len(b) >= 4:
        ln = struct.unpack_from(">I", b, 0)[0]
        if ln == len(b) - 4:
            return b[4:].decode("utf-8", errors="replace")
    return b.decode("utf-8", errors="replace")


def _decode_cell(cell_class: str, b: bytes) -> Any:
    """Deserialize a single KNIME DataCell payload."""
    short = cell_class.rsplit(".", 1)[-1]
    if short == "StringCell":
        return _decode_java_utf(b)
    if short == "IntCell":
        return struct.unpack(">i", b[:4])[0]
    if short == "LongCell":
        return struct.unpack(">q", b[:8])[0]
    if short == "DoubleCell":
        return struct.unpack(">d", b[:8])[0]
    if short == "BooleanCell":
        return bool(b[0]) if b else False
    if short == "LocalDateCell":
        if len(b) == 8:
            epoch_day = struct.unpack(">q", b)[0]
            return datetime.date(1970, 1, 1) + datetime.timedelta(days=epoch_day)
        if len(b) == 6:
            y, m, d = struct.unpack(">iBB", b)
            return datetime.date(y, m, d)
        return _decode_java_utf(b)
    if short == "LocalDateTimeCell":
        if len(b) >= 16:
            epoch_day, nano_of_day = struct.unpack(">qq", b[:16])
            dt = datetime.datetime(1970, 1, 1) + datetime.timedelta(
                days=epoch_day, microseconds=nano_of_day // 1000
            )
            return dt
        return _decode_java_utf(b)
    if short == "LocalTimeCell":
        if len(b) >= 8:
            nano_of_day = struct.unpack(">q", b[:8])[0]
            secs, rem_ns = divmod(nano_of_day, 1_000_000_000)
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            return datetime.time(int(h % 24), int(m), int(s), int(rem_ns // 1000))
        return _decode_java_utf(b)
    if short == "ZonedDateTimeCell":
        return _decode_java_utf(b)
    # Fallback: readable string if printable, else hex representation
    try:
        return _decode_java_utf(b)
    except Exception:
        return b.hex()


def decode_container_data_zip(
    dz_bytes: bytes,
    ncols: int,
    col_names: list[str] | None = None,
) -> KnimeTable:
    """Decode a KNIME `data.zip` (`DefaultTableStoreFormat`) into a `KnimeTable`."""
    with zipfile.ZipFile(io.BytesIO(dz_bytes), "r") as dz:
        mroot = ET.fromstring(dz.read("meta.xml"))
        ver_e = mroot.find('.//k:entry[@key="container.version"]', NS)
        version = ver_e.get("value", "") if ver_e is not None else ""
        has_row_keys = "norowkey" not in version.lower()
        size_e = mroot.find('.//k:entry[@key="table.size"]', NS)
        nrows = int(size_e.get("value", "0")) if size_e is not None else 0
        comp_e = mroot.find('.//k:entry[@key="container.compression"]', NS)
        compression = comp_e.get("value", "NONE") if comp_e is not None else "NONE"

        classes: list[str] = []
        cls_cfg = mroot.find('.//k:config[@key="table.datacell.classes"]', NS)
        if cls_cfg is not None:
            elems = sorted(
                cls_cfg.findall("k:config", NS),
                key=lambda c: int(c.get("key", "element_0").split("_")[-1]),
            )
            for e in elems:
                ce = e.find('k:entry[@key="class"]', NS)
                if ce is not None:
                    classes.append(ce.get("value", ""))

        names = col_names if (col_names and len(col_names) == ncols) else [f"col_{i}" for i in range(ncols)]
        if nrows == 0 or "data.bin" not in dz.namelist():
            return KnimeTable(names, {n: [] for n in names}, [])

        raw = decompress_knime_stream(dz.read("data.bin"), compression=compression)
        pos = 0
        row_keys: list[str] = []
        columns_data: list[list[Any]] = [[] for _ in range(ncols)]

        for r in range(nrows):
            if has_row_keys:
                rk_b, pos = _read_block(raw, pos)
                row_keys.append(_decode_java_utf(rk_b))
            else:
                row_keys.append(f"Row{r}")
            for c in range(ncols):
                t = raw[pos]
                pos += 1
                if t == 0x80:  # BYTE_TYPE_MISSING
                    columns_data[c].append(None)
                else:
                    idx = (t - 0x82) & 0xFF
                    blk, pos = _read_block(raw, pos)
                    cclass = classes[idx] if idx < len(classes) else "StringCell"
                    columns_data[c].append(_decode_cell(cclass, blk))
            # Row separator byte (0x83 in container_12)
            if pos < len(raw):
                pos += 1

        return KnimeTable(names, {names[i]: columns_data[i] for i in range(ncols)}, row_keys)


class KnimeTableRegistry:
    """Indexes and lazily resolves every table inside a KNIME workflow."""

    def __init__(self, source: WorkflowSource) -> None:
        self.source = source
        # Maps table_ID -> directory prefix containing data.xml
        self._id_to_dir: dict[int, str] = {}
        self._cache: dict[str, KnimeTable] = {}
        self._spec_cache: dict[str, list[ColumnSpec]] = {}
        self._index_tables()

    def _index_tables(self) -> None:
        for entry in self.source.entries:
            if entry.endswith("/data.xml"):
                dir_prefix = entry[: -len("/data.xml")]
                try:
                    root = ET.fromstring(self.source.read_bytes(entry))
                    tid_e = root.find('k:entry[@key="table_ID"]', NS)
                    if tid_e is not None and tid_e.get("value") is not None:
                        tid = int(tid_e.get("value", "-1"))
                        # Prefer concrete container tables if duplicate table_ID exists
                        tt_e = root.find('k:entry[@key="table_type"]', NS)
                        tt = tt_e.get("value", "") if tt_e is not None else ""
                        if tid not in self._id_to_dir or "container_table" in tt:
                            self._id_to_dir[tid] = dir_prefix
                except Exception:
                    continue

    def get_spec(self, table_dir: str) -> list[ColumnSpec]:
        if table_dir in self._spec_cache:
            return self._spec_cache[table_dir]
        spec_path = f"{table_dir}/spec.xml"
        if not self.source.exists(spec_path):
            return []
        specs = parse_spec_xml(self.source.read_bytes(spec_path))
        self._spec_cache[table_dir] = specs
        return specs

    def read_table_dir(self, table_dir: str, _visited: set[str] | None = None) -> KnimeTable:
        if table_dir in self._cache:
            return self._cache[table_dir].copy()

        visited = set(_visited) if _visited else set()
        if table_dir in visited:
            raise RecursionError(f"Cyclic KNIME table reference detected at {table_dir}")
        visited.add(table_dir)

        data_xml_path = f"{table_dir}/data.xml"
        specs = self.get_spec(table_dir)
        col_names = [s.name for s in specs]

        if not self.source.exists(data_xml_path):
            dz_path = f"{table_dir}/data.zip"
            if self.source.exists(dz_path):
                tbl = decode_container_data_zip(self.source.read_bytes(dz_path), len(col_names), col_names)
                self._cache[table_dir] = tbl
                return tbl.copy()
            raise FileNotFoundError(f"No data.xml or data.zip found in {table_dir}")

        root = ET.fromstring(self.source.read_bytes(data_xml_path))
        tt_e = root.find('k:entry[@key="table_type"]', NS)
        table_type = tt_e.get("value", "") if tt_e is not None else ""
        meta = root.find('k:config[@key="meta_internal"]', NS)
        refs_cfg = root.find('k:config[@key="table_references"]', NS)
        sub_refs = []
        if refs_cfg is not None:
            for e in refs_cfg.findall("k:entry", NS):
                if e.get("key") != "array-size" and e.get("value"):
                    sub_refs.append(e.get("value", ""))

        def resolve_ref_id(ref_id: int, fallback_sub_idx: int = 0) -> KnimeTable:
            if fallback_sub_idx < len(sub_refs):
                candidate = f"{table_dir}/{sub_refs[fallback_sub_idx]}"
                if self.source.exists(f"{candidate}/data.xml"):
                    try:
                        croot = ET.fromstring(self.source.read_bytes(f"{candidate}/data.xml"))
                        ctid = croot.find('k:entry[@key="table_ID"]', NS)
                        if ctid is not None and int(ctid.get("value", "-1")) == ref_id:
                            return self.read_table_dir(candidate, visited)
                    except Exception:
                        pass
            if ref_id in self._id_to_dir:
                return self.read_table_dir(self._id_to_dir[ref_id], visited)
            if fallback_sub_idx < len(sub_refs):
                return self.read_table_dir(f"{table_dir}/{sub_refs[fallback_sub_idx]}", visited)
            raise KeyError(f"Cannot resolve KNIME table_reference_ID={ref_id} from {table_dir}")

        tbl: KnimeTable
        if table_type in ("container_table_compressed", "container_table", "buffered_data_table"):
            fname_e = root.find('k:entry[@key="table_file_name"]', NS)
            fname = fname_e.get("value", "data.zip") if fname_e is not None else "data.zip"
            dz_path = f"{table_dir}/{fname}"
            tbl = decode_container_data_zip(self.source.read_bytes(dz_path), len(col_names), col_names)

        elif table_type in ("new_spec_table", "wrapped_table"):
            ref_id = int(meta.find('k:entry[@key="table_reference_ID"]', NS).get("value"))  # type: ignore[union-attr]
            base_tbl = resolve_ref_id(ref_id, 0)
            if col_names and len(col_names) == len(base_tbl.columns):
                base_tbl = base_tbl.rename_columns(col_names)
            tbl = base_tbl

        elif table_type in ("rearrange_columns_table", "rearrange_columns_table_compressed"):
            ref_id = int(meta.find('k:entry[@key="table_reference_ID"]', NS).get("value"))  # type: ignore[union-attr]
            base_tbl = resolve_ref_id(ref_id, 0)

            map_cfg = meta.find('k:config[@key="table_internal_map"]', NS)  # type: ignore[union-attr]
            flags_cfg = meta.find('k:config[@key="table_internal_flags"]', NS)  # type: ignore[union-attr]
            imap = [
                int(e.get("value"))  # type: ignore[arg-type]
                for e in sorted(
                    (e for e in map_cfg.findall("k:entry", NS) if e.get("key") != "array-size"),  # type: ignore[union-attr]
                    key=lambda x: int(x.get("key", "0")),
                )
            ]
            iflags = [
                e.get("value", "true").lower() == "true"
                for e in sorted(
                    (e for e in flags_cfg.findall("k:entry", NS) if e.get("key") != "array-size"),  # type: ignore[union-attr]
                    key=lambda x: int(x.get("key", "0")),
                )
            ]

            n_local = sum(1 for f in iflags if not f)
            local_tbl: KnimeTable | None = None
            if n_local > 0:
                fname_e = root.find('k:entry[@key="table_file_name"]', NS)
                fname = (fname_e.get("value") if fname_e is not None and fname_e.get("value") else "data.zip")
                dz_path = f"{table_dir}/{fname}"
                local_tbl = decode_container_data_zip(self.source.read_bytes(dz_path), n_local)

            series_dict: dict[str, list[Any]] = {}
            out_names = col_names if len(col_names) == len(imap) else [f"col_{i}" for i in range(len(imap))]
            for out_idx, (src_idx, from_ref) in enumerate(zip(imap, iflags)):
                cname = out_names[out_idx]
                if from_ref:
                    series_dict[cname] = base_tbl.col_at(src_idx)
                else:
                    assert local_tbl is not None
                    series_dict[cname] = local_tbl.col_at(src_idx)

            tbl = KnimeTable(out_names, series_dict, base_tbl.row_ids)

        elif table_type == "concatenate_table":
            ids_cfg = meta.find('k:config[@key="table_reference_IDS"]', NS)  # type: ignore[union-attr]
            ref_ids = [
                int(e.get("value"))  # type: ignore[arg-type]
                for e in sorted(
                    (e for e in ids_cfg.findall("k:entry", NS) if e.get("key") != "array-size"),  # type: ignore[union-attr]
                    key=lambda x: int(x.get("key", "0")),
                )
            ]
            parts = [resolve_ref_id(rid, i) for i, rid in enumerate(ref_ids)]
            tbl = KnimeTable.concat_rows(parts)
            if col_names and len(col_names) == len(tbl.columns):
                tbl = tbl.rename_columns(col_names)

        elif table_type == "joined_table":
            left_id = int(meta.find('k:entry[@key="left_table_ID"]', NS).get("value"))  # type: ignore[union-attr]
            right_id = int(meta.find('k:entry[@key="right_table_ID"]', NS).get("value"))  # type: ignore[union-attr]
            left_tbl = resolve_ref_id(left_id, 0)
            right_tbl = resolve_ref_id(right_id, 1)
            tbl = KnimeTable.concat_cols(left_tbl, right_tbl)
            if col_names and len(col_names) == len(tbl.columns):
                tbl = tbl.rename_columns(col_names)

        else:
            dz_path = f"{table_dir}/data.zip"
            if self.source.exists(dz_path):
                tbl = decode_container_data_zip(self.source.read_bytes(dz_path), len(col_names), col_names)
            elif meta is not None and meta.find('k:entry[@key="table_reference_ID"]', NS) is not None:
                ref_id = int(meta.find('k:entry[@key="table_reference_ID"]', NS).get("value"))  # type: ignore[union-attr]
                tbl = resolve_ref_id(ref_id, 0)
            else:
                raise NotImplementedError(f"Unsupported KNIME table_type '{table_type}' in {table_dir}")

        self._cache[table_dir] = tbl
        return tbl.copy()
