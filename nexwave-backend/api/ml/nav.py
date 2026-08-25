"""
Nav — Graph corridor navigation
Diekstrak dari WaveIQ_v11_PRD.ipynb (Stage 1c)

Cara pakai:
    from api.ml.nav import Nav
    nav = Nav("/dataset")
"""

import os
import re
import numpy as np
import pandas as pd
import networkx as nx

# Depot sesuai paper & dataset -- titik nav TETAP, bukan dihitung dari centroid
# lokasi (itu cuma heuristik, hasilnya beda -- CC-10, bukan CC-08 yang bener).
DEPOT_LABEL = "CC-08"


class Nav:
    def __init__(self, data_dir: str, floor_penalty: float = 0.0):
        self.floor_penalty = floor_penalty

        # ── Baca CSV ──────────────────────────────────────────────────────────
        df_loc = self._read(os.path.join(data_dir, "Storage_Location.csv"))
        df_nav_raw = self._read(os.path.join(data_dir, "Support_Points_Navigation.csv"))

        # ── Parse Support_Points_Navigation ───────────────────────────────────
        records = []
        for _, row in df_nav_raw.iterrows():
            pts = str(row.iloc[0]).strip()
            label = str(row.iloc[1]).strip()
            m = re.match(r"\(([-\d.]+)[,;]\s*([-\d.]+)[,;]\s*([-\d.]+)\)", pts)
            if m:
                x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
                corridor = re.match(r"([A-Za-z]+)-", label)
                corridor = corridor.group(1) if corridor else label
                idx_m = re.search(r"-(\d+)$", label)
                idx = int(idx_m.group(1)) if idx_m else 0
                records.append({"label": label, "x": x, "y": y,
                                "corridor": corridor, "idx": idx})
        df_nav = pd.DataFrame(records)

        # ── Build corridor graph ───────────────────────────────────────────────
        G = nx.Graph()
        for _, r in df_nav.iterrows():
            G.add_node(r["label"], x=r["x"], y=r["y"])

        # Edge vertikal: titik berurutan dalam satu koridor (LC/CC/RC)
        for corr in df_nav["corridor"].unique():
            pts = df_nav[df_nav["corridor"] == corr].sort_values("idx")
            for i in range(len(pts) - 1):
                p1, p2 = pts.iloc[i], pts.iloc[i + 1]
                G.add_edge(p1["label"], p2["label"],
                           weight=abs(p1["y"] - p2["y"]))

        # Edge horizontal: titik di Y yang sama (aisle cross-connection)
        for yv in df_nav["y"].unique():
            pts = df_nav[df_nav["y"] == yv]
            labels = pts["label"].tolist()
            xs = pts.set_index("label")["x"].to_dict()
            for i in range(len(labels)):
                for j in range(i + 1, len(labels)):
                    l1, l2 = labels[i], labels[j]
                    G.add_edge(l1, l2, weight=abs(xs[l1] - xs[l2]))

        self.G = G
        self.df_nav = df_nav
        self.df_loc = df_loc

        # All-pairs shortest path (precompute saat startup)
        self.navmat = dict(nx.all_pairs_dijkstra_path_length(G, weight="weight"))

        # Map tiap storage location ke titik nav terdekat
        self.loc_to_nav = {}
        for _, r in df_loc.iterrows():
            self.loc_to_nav[r["originalLocation"]] = self._nearest(r["x"], r["y"])

        # loc_xy untuk koordinat mentah
        self.loc_xy = df_loc.set_index("originalLocation")[["x", "y"]].to_dict("index")

        # loc_z untuk floor penalty
        self.loc_z = (df_loc.set_index("originalLocation")["z"].to_dict()
                      if "z" in df_loc.columns else {})

        # Depot: titik TETAP sesuai paper & dataset (DEPOT_LABEL), bukan
        # dihitung dari rata-rata lokasi -- itu cuma heuristik lama yang
        # kebetulan salah nunjuk titik lain (CC-10, bukan CC-08).
        if DEPOT_LABEL not in G.nodes:
            raise ValueError(
                f"Depot '{DEPOT_LABEL}' tidak ada di nav graph -- cek "
                f"Support_Points_Navigation.csv, mungkin label-nya beda atau "
                f"dataset-nya ganti. Node yang ada: {sorted(G.nodes)[:10]}..."
            )
        self.DEPOT = DEPOT_LABEL

    # ── Internal helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _read(path: str) -> pd.DataFrame:
        for sep in [";", ",", "\t"]:
            try:
                df = pd.read_csv(path, sep=sep, encoding="utf-8-sig")
                if df.shape[1] > 1:
                    df.columns = [c.strip() for c in df.columns]
                    return df
            except Exception:
                pass
        df = pd.read_csv(path, encoding="utf-8-sig")
        df.columns = [c.strip() for c in df.columns]
        return df

    def _nearest(self, x: float, y: float):
        c = self.df_nav.copy()
        c["yd"] = (c["y"] - y).abs()
        t = c.nsmallest(6, "yd").copy()
        t["td"] = t["yd"] + (t["x"] - x).abs()
        b = t.loc[t["td"].idxmin()]
        return (b["label"], abs(b["x"] - x) + abs(b["y"] - y))

    # ── Public API ─────────────────────────────────────────────────────────────
    def corridor_distance(self, l1: str, l2: str,
                          floor_penalty: float = None) -> float:
        if l1 == l2:
            return 0.0
        if l1 not in self.loc_to_nav or l2 not in self.loc_to_nav:
            return float("inf")
        n1, e1 = self.loc_to_nav[l1]
        n2, e2 = self.loc_to_nav[l2]
        d = (e1 + e2) if n1 == n2 else (
            e1 + self.navmat.get(n1, {}).get(n2, float("inf")) + e2
        )
        fp = floor_penalty if floor_penalty is not None else self.floor_penalty
        if fp > 0:
            z1 = self.loc_z.get(l1, 1)
            z2 = self.loc_z.get(l2, 1)
            if z1 != z2:
                d += fp
        return d

    def depot_dist(self, l: str) -> float:
        if l not in self.loc_to_nav:
            return float("inf")
        n, e = self.loc_to_nav[l]
        if n == self.DEPOT:
            return e
        return e + self.navmat.get(self.DEPOT, {}).get(n, float("inf"))

    def route_nn(self, locs: list) -> tuple:
        """Nearest-neighbor heuristic. Return (total_distance, ordered_locs)."""
        valid = [l for l in locs if l in self.loc_to_nav]
        if not valid:
            return 0.0, []
        un = list(dict.fromkeys(valid))
        cur = None
        tot = 0.0
        order = []
        while un:
            if cur is None:
                nxt = min(un, key=self.depot_dist)
                tot += self.depot_dist(nxt)
            else:
                nxt = min(un, key=lambda l: self.corridor_distance(cur, l))
                tot += self.corridor_distance(cur, nxt)
            un.remove(nxt)
            cur = nxt
            order.append(nxt)
        tot += self.depot_dist(cur)
        return tot, order

    def route_sshape(self, locs: list) -> tuple:
        """S-shape heuristic routing."""
        valid = [l for l in locs if l in self.loc_to_nav]
        if not valid:
            return 0.0, []
        by_nav = {}
        for l in valid:
            nav_pt, _ = self.loc_to_nav[l]
            by_nav.setdefault(nav_pt, []).append(l)
        nav_pts = sorted(by_nav.keys(),
                         key=lambda n: self.G.nodes[n].get("y", 0))
        order = []
        for i, nav_pt in enumerate(nav_pts):
            group = sorted(by_nav[nav_pt],
                           key=lambda l: self.loc_xy[l]["x"],
                           reverse=(i % 2 == 1))
            order.extend(group)
        d = 0.0
        prev = None
        for l in order:
            d += self.depot_dist(l) if prev is None else self.corridor_distance(prev, l)
            prev = l
        if prev:
            d += self.depot_dist(prev)
        return d, order
