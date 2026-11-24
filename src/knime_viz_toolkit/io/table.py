"""Lightweight, zero-pandas columnar table for decoded KNIME datasets.

Designed to work cleanly on Python 3.10-3.14 using only the standard library
and NumPy, while offering optional `.to_pandas()` interop when pandas is
installed.
"""

from __future__ import annotations

import datetime
import math
from collections import defaultdict
from typing import Any, Iterable

import numpy as np


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return False


def _to_float(v: Any) -> float | None:
    if _is_missing(v):
        return None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float, np.number)):
        f = float(v)
        return None if math.isnan(f) else f
    try:
        f = float(str(v).strip())
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def smart_sort_key(val: Any) -> tuple[int, float | str]:
    """Sort numeric strings ('1', '2', ..., '12') numerically, then lexicographically."""
    if _is_missing(val):
        return (2, "")
    if isinstance(val, (int, float, np.number)) and not isinstance(val, bool):
        return (0, float(val))
    if isinstance(val, (datetime.date, datetime.datetime)):
        return (0, float(val.toordinal()) if isinstance(val, datetime.date) and not isinstance(val, datetime.datetime) else val.timestamp())
    s = str(val).strip()
    try:
        return (0, float(s))
    except ValueError:
        return (1, s.lower())


class KnimeTable:
    """Columnar in-memory table decoded from a KNIME workflow port."""

    def __init__(
        self,
        columns: list[str],
        data: dict[str, list[Any]],
        row_ids: list[str] | None = None,
    ) -> None:
        self.columns: list[str] = list(columns)
        self._data: dict[str, list[Any]] = {c: list(data[c]) for c in self.columns}
        nrows = len(self._data[self.columns[0]]) if self.columns else (len(row_ids) if row_ids else 0)
        self.row_ids: list[str] = list(row_ids) if row_ids is not None else [f"Row{i}" for i in range(nrows)]
        self._nrows = nrows

    @property
    def shape(self) -> tuple[int, int]:
        return (self._nrows, len(self.columns))

    def __len__(self) -> int:
        return self._nrows

    def __contains__(self, col: str) -> bool:
        return col in self._data

    def __getitem__(self, col: str) -> list[Any]:
        return self._data[col]

    def col_at(self, idx: int) -> list[Any]:
        return self._data[self.columns[idx]]

    def copy(self) -> "KnimeTable":
        return KnimeTable(
            columns=list(self.columns),
            data={c: list(self._data[c]) for c in self.columns},
            row_ids=list(self.row_ids),
        )

    def rename_columns(self, new_names: list[str]) -> "KnimeTable":
        if len(new_names) != len(self.columns):
            raise ValueError(f"Expected {len(self.columns)} column names, got {len(new_names)}")
        new_data = {new: list(self._data[old]) for old, new in zip(self.columns, new_names)}
        return KnimeTable(columns=list(new_names), data=new_data, row_ids=list(self.row_ids))

    @classmethod
    def concat_rows(cls, tables: list["KnimeTable"]) -> "KnimeTable":
        if not tables:
            return cls([], {}, [])
        cols = list(tables[0].columns)
        merged: dict[str, list[Any]] = {c: [] for c in cols}
        rids: list[str] = []
        for t in tables:
            for c in cols:
                merged[c].extend(t._data.get(c, [None] * len(t)))
            rids.extend(t.row_ids)
        return cls(cols, merged, rids)

    @classmethod
    def concat_cols(cls, left: "KnimeTable", right: "KnimeTable") -> "KnimeTable":
        cols = list(left.columns)
        data = {c: list(left._data[c]) for c in left.columns}
        for c in right.columns:
            cname = c
            suffix = 1
            while cname in data:
                cname = f"{c}_{suffix}"
                suffix += 1
            cols.append(cname)
            data[cname] = list(right._data[c])
        return cls(cols, data, list(left.row_ids))

    def is_numeric_column(self, col: str) -> bool:
        vals = [v for v in self._data[col] if not _is_missing(v)]
        if not vals:
            return False
        num_ok = sum(1 for v in vals[:200] if isinstance(v, (int, float, np.number)) and not isinstance(v, bool))
        return (num_ok / min(len(vals), 200)) >= 0.85

    def is_date_column(self, col: str) -> bool:
        vals = [v for v in self._data[col] if not _is_missing(v)]
        if not vals:
            return False
        sample = vals[:50]
        if all(isinstance(v, (datetime.date, datetime.datetime)) for v in sample):
            return True
        if all(isinstance(v, str) for v in sample):
            ok = 0
            for s in sample:
                try:
                    datetime.date.fromisoformat(s[:10])
                    ok += 1
                except ValueError:
                    pass
            return ok / len(sample) >= 0.9
        return False

    def as_dates(self, col: str) -> list[datetime.datetime | None]:
        out: list[datetime.datetime | None] = []
        for v in self._data[col]:
            if _is_missing(v):
                out.append(None)
            elif isinstance(v, datetime.datetime):
                out.append(v)
            elif isinstance(v, datetime.date):
                out.append(datetime.datetime(v.year, v.month, v.day))
            else:
                try:
                    s = str(v).strip()
                    if len(s) >= 10:
                        d = datetime.date.fromisoformat(s[:10])
                        out.append(datetime.datetime(d.year, d.month, d.day))
                    else:
                        out.append(None)
                except ValueError:
                    out.append(None)
        return out

    def as_floats(self, col: str) -> np.ndarray:
        arr = np.full(self._nrows, np.nan, dtype=float)
        for i, v in enumerate(self._data[col]):
            f = _to_float(v)
            if f is not None:
                arr[i] = f
        return arr

    def as_strings(self, col: str) -> list[str]:
        return ["" if _is_missing(v) else str(v) for v in self._data[col]]

    def numeric_columns(self) -> list[str]:
        return [c for c in self.columns if self.is_numeric_column(c)]

    def categorical_columns(self, max_unique: int = 30) -> list[str]:
        out: list[str] = []
        for c in self.columns:
            if self.is_date_column(c):
                continue
            uniq = {str(v) for v in self._data[c] if not _is_missing(v)}
            if 1 < len(uniq) <= max_unique and (not self.is_numeric_column(c) or len(uniq) <= 12):
                out.append(c)
        return out

    def groupby_agg(
        self,
        group_col: str,
        value_cols: Iterable[str],
        method: str = "AVG",
    ) -> tuple[list[str], dict[str, list[float]]]:
        """Group by `group_col` and aggregate `value_cols` using KNIME method names."""
        m = (method or "AVG").upper()
        groups: dict[str, list[int]] = defaultdict(list)
        raw_rep: dict[str, Any] = {}
        for idx, gval in enumerate(self._data[group_col]):
            if _is_missing(gval):
                continue
            key = str(gval)
            groups[key].append(idx)
            if key not in raw_rep:
                raw_rep[key] = gval

        sorted_keys = sorted(groups.keys(), key=lambda k: smart_sort_key(raw_rep[k]))
        vcols = list(value_cols)
        result: dict[str, list[float]] = {vc: [] for vc in vcols}

        for k in sorted_keys:
            idxs = groups[k]
            for vc in vcols:
                if m in ("COUNT", "OCCURRENCE_COUNT"):
                    result[vc].append(float(len(idxs)))
                    continue
                vals = []
                for i in idxs:
                    f = _to_float(self._data[vc][i])
                    if f is not None:
                        vals.append(f)
                if not vals:
                    result[vc].append(0.0)
                elif m in ("AVG", "MEAN", "AVERAGE"):
                    result[vc].append(float(np.mean(vals)))
                elif m == "SUM":
                    result[vc].append(float(np.sum(vals)))
                elif m == "MEDIAN":
                    result[vc].append(float(np.median(vals)))
                elif m == "MIN":
                    result[vc].append(float(np.min(vals)))
                elif m == "MAX":
                    result[vc].append(float(np.max(vals)))
                else:
                    result[vc].append(float(np.mean(vals)))

        return sorted_keys, result

    def pivot_agg(
        self,
        row_col: str,
        col_col: str,
        val_col: str,
        method: str = "AVG",
    ) -> tuple[list[str], list[str], np.ndarray]:
        """Create a 2D pivot matrix `(row_labels, col_labels, matrix)`."""
        m = (method or "AVG").upper()
        cells: dict[tuple[str, str], list[float]] = defaultdict(list)
        row_rep: dict[str, Any] = {}
        col_rep: dict[str, Any] = {}

        r_vals = self._data[row_col]
        c_vals = self._data[col_col]
        v_vals = self._data[val_col]

        for rv, cv, vv in zip(r_vals, c_vals, v_vals):
            if _is_missing(rv) or _is_missing(cv):
                continue
            rk, ck = str(rv), str(cv)
            row_rep.setdefault(rk, rv)
            col_rep.setdefault(ck, cv)
            f = _to_float(vv)
            if f is not None:
                cells[(rk, ck)].append(f)

        rows = sorted(row_rep.keys(), key=lambda k: smart_sort_key(row_rep[k]))
        cols = sorted(col_rep.keys(), key=lambda k: smart_sort_key(col_rep[k]))
        mat = np.full((len(rows), len(cols)), np.nan, dtype=float)

        for ri, rk in enumerate(rows):
            for ci, ck in enumerate(cols):
                vals = cells.get((rk, ck), [])
                if not vals:
                    continue
                if m in ("COUNT", "OCCURRENCE_COUNT"):
                    mat[ri, ci] = float(len(vals))
                elif m == "SUM":
                    mat[ri, ci] = float(np.sum(vals))
                elif m == "MEDIAN":
                    mat[ri, ci] = float(np.median(vals))
                elif m == "MIN":
                    mat[ri, ci] = float(np.min(vals))
                elif m == "MAX":
                    mat[ri, ci] = float(np.max(vals))
                else:
                    mat[ri, ci] = float(np.mean(vals))
        return rows, cols, mat

    def head(self, n: int = 10) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        limit = min(n, self._nrows)
        for i in range(limit):
            row: dict[str, Any] = {"RowID": self.row_ids[i]}
            for c in self.columns:
                v = self._data[c][i]
                if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
                    row[c] = v.isoformat()
                else:
                    row[c] = v
            out.append(row)
        return out

    def column_stats(self) -> list[dict[str, Any]]:
        stats: list[dict[str, Any]] = []
        for c in self.columns:
            vals = self._data[c]
            non_null = [v for v in vals if not _is_missing(v)]
            info: dict[str, Any] = {
                "name": c,
                "non_null": len(non_null),
                "missing": len(vals) - len(non_null),
                "unique": len({str(v) for v in non_null}),
            }
            if self.is_date_column(c):
                info["inferred_type"] = "date"
                dates = [d for d in self.as_dates(c) if d is not None]
                if dates:
                    info["min"] = min(dates).date().isoformat()
                    info["max"] = max(dates).date().isoformat()
            elif self.is_numeric_column(c):
                info["inferred_type"] = "numeric"
                arr = self.as_floats(c)
                arr = arr[~np.isnan(arr)]
                if len(arr):
                    info["min"] = round(float(np.min(arr)), 4)
                    info["max"] = round(float(np.max(arr)), 4)
                    info["mean"] = round(float(np.mean(arr)), 4)
                    info["std"] = round(float(np.std(arr)), 4)
            else:
                info["inferred_type"] = "categorical"
                sample_vals = sorted({str(v) for v in non_null}, key=smart_sort_key)[:8]
                info["sample_values"] = sample_vals
            stats.append(info)
        return stats

    def to_pandas(self) -> Any:
        """Convert to a `pandas.DataFrame` (requires optional `pandas`)."""
        import pandas as pd  # type: ignore[import-not-found]

        df = pd.DataFrame(self._data, index=self.row_ids)
        df.index.name = "RowID"
        return df
