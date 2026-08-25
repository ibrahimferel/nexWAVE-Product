"""
Attention Model Routing Agent
Diekstrak dari WaveIQ_v11_PRD.ipynb (Stage 3a)

Cara pakai:
    import torch
    from api.ml.routing import AttnRoutingPolicy, route_with_attn

    attn = AttnRoutingPolicy()
    attn.load_state_dict(torch.load("/models/attn_routing_v11.pt", map_location="cpu"))
    attn.eval()

    dist, route = route_with_attn(attn, locs, nav)
"""

import numpy as np
import torch
import torch.nn as nn

# Hyperparameter default — harus sama dengan saat training
ROUTING_HID    = 64
ROUTING_HEADS  = 4
ROUTING_LAYERS = 3


class AttnEncoderLayer(nn.Module):
    def __init__(self, d_h: int, n_heads: int):
        super().__init__()
        self.mha = nn.MultiheadAttention(d_h, n_heads, batch_first=True)
        self.ff  = nn.Sequential(
            nn.Linear(d_h, 4 * d_h), nn.ReLU(), nn.Linear(4 * d_h, d_h)
        )
        self.n1 = nn.LayerNorm(d_h)
        self.n2 = nn.LayerNorm(d_h)

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        h2, _ = self.mha(h, h, h)
        h = self.n1(h + h2)
        return self.n2(h + self.ff(h))


class AttnRoutingPolicy(nn.Module):
    """
    Attention Model untuk picker routing (Kool et al. 2018 style).
    Encoder: multi-head self-attention atas seluruh lokasi dalam wave
    (termasuk depot sebagai node index 0).
    Decoder: pointer mechanism — tiap langkah attend ke lokasi yang
    belum dikunjungi, pilih yang skornya tertinggi (greedy decode).
    """

    def __init__(
        self,
        d_in:    int = 2,
        d_h:     int = ROUTING_HID,
        n_heads: int = ROUTING_HEADS,
        n_layers:int = ROUTING_LAYERS,
    ):
        super().__init__()
        self.embed  = nn.Linear(d_in, d_h)
        self.layers = nn.ModuleList([
            AttnEncoderLayer(d_h, n_heads) for _ in range(n_layers)
        ])
        self.W_q   = nn.Linear(d_h * 2, d_h)
        self.W_k   = nn.Linear(d_h, d_h)
        self.start = nn.Parameter(torch.randn(d_h) * 0.1)
        self.d_h   = d_h

    def encode(self, coords: torch.Tensor) -> torch.Tensor:
        h = self.embed(coords).unsqueeze(0)
        for layer in self.layers:
            h = layer(h)
        return h.squeeze(0)

    def forward(
        self,
        coords: torch.Tensor,
        greedy: bool = False,
    ) -> tuple:
        n = coords.shape[0]
        H = self.encode(coords)
        graph_mean = H.mean(0)
        K    = self.W_k(H)
        mask = torch.zeros(n, dtype=torch.bool, device=coords.device)
        mask[0] = True   # depot sudah dikunjungi di awal
        tour = [0]
        logp = torch.zeros(1, device=coords.device)
        last = self.start

        for _ in range(n - 1):
            ctx    = torch.cat([graph_mean, last])
            q      = self.W_q(ctx).unsqueeze(0)
            scores = (q @ K.T).squeeze(0) / (self.d_h ** 0.5)
            scores = scores.masked_fill(mask, float("-inf"))
            probs  = torch.softmax(scores, dim=-1)

            if greedy:
                nxt = int(torch.argmax(probs).item())
            else:
                dist_cat = torch.distributions.Categorical(probs)
                nxt_t    = dist_cat.sample()
                nxt      = int(nxt_t.item())
                logp     = logp + dist_cat.log_prob(nxt_t)

            mask = mask.clone()
            mask[nxt] = True
            tour.append(nxt)
            last = H[nxt]

        return tour, logp


# ── Helper functions ───────────────────────────────────────────────────────────

def instance_coords(locs: list, nav) -> torch.Tensor:
    """
    Buat tensor koordinat ternormalisasi untuk satu wave.
    Node 0 = depot, node 1..n = lokasi dalam wave.
    """
    dep = (nav.G.nodes[nav.DEPOT]["x"], nav.G.nodes[nav.DEPOT]["y"])
    pts = [dep] + [(nav.loc_xy[l]["x"], nav.loc_xy[l]["y"]) for l in locs]
    arr = np.array(pts, dtype=np.float32)
    mu, sd = arr.mean(0), arr.std(0) + 1e-6
    return torch.tensor((arr - mu) / sd, dtype=torch.float32)


def tour_length_idx(locs: list, tour_idx: list, nav) -> float:
    """Hitung total jarak rute dari indeks tour."""
    seq   = [None] + list(locs)
    order = [seq[i] for i in tour_idx]
    d     = 0.0
    prev  = None
    for loc in order[1:]:
        d   += nav.depot_dist(loc) if prev is None else nav.corridor_distance(prev, loc)
        prev = loc
    return d + (nav.depot_dist(prev) if prev else 0.0)


def route_with_attn(model: AttnRoutingPolicy, locs: list, nav) -> tuple:
    """
    Jalankan Attention Model untuk satu wave.
    Return: (total_distance, ordered_locs)
    """
    valid = [l for l in locs if l in nav.loc_to_nav]
    if not valid:
        return 0.0, []
    coords = instance_coords(valid, nav)
    with torch.no_grad():
        tour_idx, _ = model(coords, greedy=True)
    route = [valid[i - 1] for i in tour_idx[1:]]
    d     = tour_length_idx(valid, tour_idx, nav)
    return d, route


def route_best(model: AttnRoutingPolicy, locs: list, nav) -> tuple:
    """
    Pilih rute terpendek dari tiga kandidat:
    Attention Model, S-shape heuristic, Nearest-neighbor.
    Safety net: performa tidak pernah lebih buruk dari heuristik.
    """
    da, ra = route_with_attn(model, locs, nav)
    ds, rs = nav.route_sshape(locs)
    dn, rn = nav.route_nn(locs)
    return min([(da, ra), (ds, rs), (dn, rn)], key=lambda x: x[0])
