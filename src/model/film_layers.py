import torch
import torch.nn as nn
import torch.nn.functional as F

class ManualGRUCell(nn.Module):
    def __init__(self, input_size, hidden_size):
        super().__init__()
        self.hidden_size = hidden_size
        self.w_ih = nn.Linear(input_size, 3 * hidden_size)
        self.w_hh = nn.Linear(hidden_size, 3 * hidden_size)
    def forward(self, x, h):
        gates_i = self.w_ih(x)
        gates_h = self.w_hh(h)
        i_r, i_z, i_n = gates_i.chunk(3, 1)
        h_r, h_z, h_n = gates_h.chunk(3, 1)
        reset_gate = torch.sigmoid(i_r + h_r)
        update_gate = torch.sigmoid(i_z + h_z)
        new_gate    = torch.tanh(i_n + reset_gate * h_n)
        h_new = (1 - update_gate) * new_gate + update_gate * h
        return h_new

class WeatherEncoder(nn.Module):
    def __init__(self, input_dim=10, hidden_dim=64, out_dim=64):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, out_dim)
        )
    def forward(self, x):
        return self.mlp(x)

class ForecastWeatherEncoder(nn.Module):
    def __init__(self, input_dim=10, hidden_dim=64, out_dim=64):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.proj = nn.Linear(input_dim, hidden_dim)
        self.cell = ManualGRUCell(hidden_dim, hidden_dim)
        self.out_proj = nn.Linear(hidden_dim, out_dim)
    def forward(self, w7):
        B, C, T = w7.shape
        x = w7.transpose(1, 2)
        x = F.gelu(self.proj(x))
        h = torch.zeros(B, self.hidden_dim, device=w7.device)
        for t in range(T):
            h = self.cell(x[:, t, :], h)
        return self.out_proj(h)

class FiLMBlock(nn.Module):
    def __init__(self, in_ch, cond_dim):
        super().__init__()
        self.mlp = nn.Sequential(nn.Linear(cond_dim, 2 * in_ch))
        nn.init.zeros_(self.mlp[0].weight)
        nn.init.zeros_(self.mlp[0].bias)
    def forward(self, x, c):
        stats = self.mlp(c).unsqueeze(-1).unsqueeze(-1)
        gamma, beta = stats.chunk(2, 1)
        return (1 + gamma) * x + beta

class SpatialAuxEncoder(nn.Module):
    def __init__(self, terrain_ch=4, lc_ch=11, burn_age_ch=3, hidden_ch=64, out_ch=32, decoder_scales=4):
        super().__init__()
        in_chans = terrain_ch + lc_ch + burn_age_ch
        self.stem = nn.Sequential(
            nn.Conv2d(in_chans, hidden_ch, 3, padding=1),
            nn.BatchNorm2d(hidden_ch),
            nn.GELU()
        )
        
        # Robustly handle out_ch as int or list
        if isinstance(out_ch, int):
            out_ch_list = [out_ch] * decoder_scales
        else:
            out_ch_list = out_ch
            
        self.scale_projs = nn.ModuleList([
            nn.Conv2d(hidden_ch, ch, 1) for ch in out_ch_list
        ])
        
    def forward(self, terrain, lc, burn_age, target_sizes):
        # Concatenate all auxiliary maps
        x = torch.cat([terrain, lc, burn_age], dim=1)
        x = self.stem(x)
        
        out = []
        for proj, (h, w) in zip(self.scale_projs, target_sizes):
            xs = F.interpolate(x, size=(h, w), mode="bilinear", align_corners=False)
            out.append(proj(xs))
        return out
