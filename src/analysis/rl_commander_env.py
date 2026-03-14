"""
VanAagni RL AI Commander Environment
====================================
A Gymnasium-compatible environment wrapper for the Muhurta-2D simulator.
Enables Reinforcement Learning agents to learn optimal fire suppression 
strategies (firelines and backfiring).

Status: Cognitive Frontier (Level 6)
"""

import numpy as np
import logging
from typing import Optional, Tuple, Dict, Any

# Mocking gymnasium if not installed to allow for architectural deployment
try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    class gym:
        class Env: pass
    spaces = None

from src.analysis.simulator import Muhurta2DSimulator

log = logging.getLogger(__name__)

class FireCommanderEnv(gym.Env):
    """
    State: Fire Mask (2D), Terrain Slope/Aspect (2D), Fuel Anomaly (2D)
    Action: [x, y, type] where type is FIRELINE or BACKFIRE
    Reward: Minimizing unconstrained spread area + Carbon protected
    """
    
    def __init__(self, grid_size: int = 128):
        super().__init__()
        self.grid_size = grid_size
        self.simulator = Muhurta2DSimulator()
        
        # Action space: Discrete(grid_size * grid_size * 2) 
        # (Very large, usually requires a CNN-based policy like PPO)
        if spaces:
            self.action_space = spaces.MultiDiscrete([grid_size, grid_size, 3]) # x, y, (none, line, ignite)
            self.observation_space = spaces.Box(low=-5, high=360, shape=(5, grid_size, grid_size), dtype=np.float32)

        self.reset()

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None) -> Tuple[np.ndarray, dict]:
        # Initialize a random fire ignition point
        self.phi = np.ones((self.grid_size, self.grid_size)) * 10.0 # High phi = no fire
        ix, iy = np.random.randint(20, self.grid_size-20, size=2)
        self.phi[iy-2:iy+2, ix-2:ix+2] = -1.0 # Small ignition
        
        self.terrain = {
            'slope': np.random.uniform(0, 30, (self.grid_size, self.grid_size)),
            'aspect': np.random.uniform(0, 360, (self.grid_size, self.grid_size)),
            'non_burnable': np.zeros((self.grid_size, self.grid_size), dtype=np.uint8)
        }
        
        self.weather = {
            'wind_u': np.random.uniform(-10, 10),
            'wind_v': np.random.uniform(-10, 10),
            'fuel_anomaly': np.full((self.grid_size, self.grid_size), -1.0)
        }
        
        self.steps_taken = 0
        return self._get_obs(), {}

    def _get_obs(self):
        # Stack layers: FireMask, Slope, AspectSin, AspectCos, Fuel
        fire_mask = (self.phi <= 0).astype(np.float32)
        obs = np.stack([
            fire_mask,
            self.terrain['slope'],
            np.sin(np.radians(self.terrain['aspect'])),
            np.cos(np.radians(self.terrain['aspect'])),
            self.weather['fuel_anomaly']
        ], axis=0)
        return obs

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, dict]:
        x, y, action_type = action
        
        # 1. Apply Action
        if action_type == 1: # FIRELINE
            self.terrain['non_burnable'][y, x] = 1
        elif action_type == 2: # BACKFIRE
            self.phi[y, x] = -1.0
            
        # 2. Run Simulation for 10 minutes
        prev_burned_area = (self.phi <= 0).sum()
        
        self.phi = self.simulator.simulate_spread(
            self.phi, self.terrain, self.weather, sim_time_minutes=10, dt_minutes=2.0
        )
        
        current_burned_area = (self.phi <= 0).sum()
        growth = current_burned_area - prev_burned_area
        
        # 3. Calculate Reward
        # Penalty for fire growth + Penalty for using resources
        reward = -growth * 1.0 - (1.0 if action_type > 0 else 0.0)
        
        self.steps_taken += 1
        terminated = self.steps_taken > 50 # 50 steps = ~8 hours
        
        return self._get_obs(), reward, terminated, False, {}

if __name__ == "__main__":
    env = FireCommanderEnv()
    obs, info = env.reset()
    print(f"Environment Reset. Initial Fire Pixels: {(obs[0] > 0).sum()}")
    
    # Take a dummy action (Place fireline at center)
    action = np.array([64, 64, 1])
    obs, reward, term, trunc, info = env.step(action)
    print(f"Action Taken. Reward: {reward:.2f}. Current Fire Pixels: {(obs[0] > 0).sum()}")
