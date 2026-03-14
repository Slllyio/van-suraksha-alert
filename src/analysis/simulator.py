"""
Muhurta-2D CNN Simulator Orchestrator
=====================================
This module ties together the Level-Set PDE and the ROS U-Net.
It acts as the PIML (Physics-Informed Machine Learning) engine, orchestrating the
loop: T_0 -> CNN (ROS Generator) -> Level-Set PDE -> T_1

It ingests static terrain and dynamic weather to evolve a fire front.
"""

import numpy as np
import torch
import logging

from src.model.ros_unet import ROSGeneratorUNet
from src.analysis.fire_dynamics import FireEventTracker

log = logging.getLogger(__name__)

class Muhurta2DSimulator:
    def __init__(self, model_path=None, device="cpu"):
        self.device = torch.device(device)
        self.ros_model = ROSGeneratorUNet(n_channels=7).to(self.device)
        self.ros_model.eval()
        
        if model_path:
            try:
                self.ros_model.load_state_dict(torch.load(model_path, map_location=self.device))
                log.info(f"Loaded ROS U-Net from {model_path}")
            except Exception as e:
                log.error(f"Failed to load ROS U-Net weights: {e}")
        else:
            log.warning("No model weights provided for ROS U-Net. Using untrained initialization (dummy spread).")

    def create_input_tensor(
        self, 
        phi_mask: np.ndarray, 
        slope: np.ndarray, 
        aspect: np.ndarray, 
        fuel_anomaly: np.ndarray, 
        wind_u: float, 
        wind_v: float
    ) -> torch.Tensor:
        """
        Stacks the environmental variables into the 7-channel tensor required by the U-Net.
        
        phi_mask: 2D binary mask (1 = fire, 0 = unburned)
        slope: 2D array of slope in degrees
        aspect: 2D array of aspect in degrees (0-360)
        fuel_anomaly: 2D array of NDVI z-scores (negative = dry)
        """
        # Encode aspect into continuous cyclical variables
        aspect_rad = np.radians(aspect)
        aspect_sin = np.sin(aspect_rad)
        aspect_cos = np.cos(aspect_rad)
        
        # Wind is broadcasted to the full 2D grid
        h, w = phi_mask.shape
        wind_u_grid = np.full((h, w), wind_u, dtype=np.float32)
        wind_v_grid = np.full((h, w), wind_v, dtype=np.float32)
        
        # Stack channels
        stack = np.stack([
            phi_mask.astype(np.float32),
            slope.astype(np.float32),
            aspect_sin.astype(np.float32),
            aspect_cos.astype(np.float32),
            fuel_anomaly.astype(np.float32),
            wind_u_grid,
            wind_v_grid
        ], axis=0) # Shape: (7, H, W)
        
        # Add batch dimension
        tensor = torch.from_numpy(stack).unsqueeze(0).to(self.device)
        return tensor

    def simulate_spread(
        self, 
        initial_phi: np.ndarray, 
        terrain_dict: dict, 
        weather_dict: dict, 
        sim_time_minutes: int, 
        dt_minutes: float = 1.0,
        dx: float = 30.0,
        dy: float = 30.0
    ) -> np.ndarray:
        """
        Runs the Physics-Informed CNN-PDE loop.
        
        initial_phi: The starting Signed Distance Function (SDF). phi < 0 is burning.
        terrain_dict: Must contain 'slope' and 'aspect' 2D numpy arrays.
        weather_dict: Must contain 'wind_u', 'wind_v', and 'fuel_anomaly'.
        """
        phi_current = initial_phi.copy()
        
        slope = terrain_dict.get('slope', np.zeros_like(phi_current))
        aspect = terrain_dict.get('aspect', np.zeros_like(phi_current))
        
        wind_u = weather_dict.get('wind_u', 0.0)
        wind_v = weather_dict.get('wind_v', 0.0)
        fuel_anomaly = weather_dict.get('fuel_anomaly', np.zeros_like(phi_current))

        steps = int(sim_time_minutes / dt_minutes)
        log.info(f"Starting Muhurta-2D Simulation: {sim_time_minutes} mins, {steps} steps.")

        for step in range(steps):
            # 1. Convert current Phi (Distance) to a strict Fire Mask (0 or 1)
            # We use a smoothed Heaviside or simply binary
            fire_mask = (phi_current <= 0).astype(np.float32)
            
            # 2. CNN Inference: Predict Spatial ROS Field
            with torch.no_grad():
                input_tensor = self.create_input_tensor(
                    fire_mask, slope, aspect, fuel_anomaly, wind_u, wind_v
                )
                ros_tensor = self.ros_model(input_tensor)
                # Squeeze batch and channel dims, get numpy array
                ros_field = ros_tensor.squeeze().cpu().numpy()
            
            # --- Apply Human Interventions (Firelines) ---
            if 'non_burnable' in terrain_dict:
                # Force ROS to zero where firelines exist
                ros_field[terrain_dict['non_burnable'] == 1] = 0.0
            
            # Convert CNN output (m/min) to m/s for the PDE
            ros_field_ms = ros_field / 60.0
            
            # 3. PDE Evolve: Apply the WRF-Fire Level-Set math
            phi_next = FireEventTracker.level_set_advance(
                phi=phi_current,
                R_f=ros_field_ms,
                dt=dt_minutes * 60.0, # seconds
                dx=dx,
                dy=dy
            )
            
            phi_current = phi_next
            
            if (step + 1) % 10 == 0 or (step + 1) == steps:
                log.info(f"  Step {step + 1}/{steps} completed.")
                
        return phi_current

    def simulate_probabilistic_spread(
        self,
        initial_phi: np.ndarray,
        terrain_dict: dict,
        weather_dict: dict,
        sim_time_minutes: int,
        dt_minutes: float = 1.0,
        n_iterations: int = 100,
        wind_jitter_pct: float = 0.2,
        fuel_jitter_pct: float = 0.1
    ) -> np.ndarray:
        """
        Runs N Monte Carlo simulations with stochastic noise on wind and fuel
        to generate a Fire Arrival Probability Map.
        
        Returns:
            probability_map: 2D array [0.0 - 1.0] representing the probability
                             that each pixel will burn within the sim_time.
        """
        log.info(f"Starting Probabilistic Monte Carlo Simulation ({n_iterations} iterations)")
        burn_counts = np.zeros_like(initial_phi)
        
        base_wind_u = weather_dict.get('wind_u', 0.0)
        base_wind_v = weather_dict.get('wind_v', 0.0)
        base_fuel = weather_dict.get('fuel_anomaly', np.zeros_like(initial_phi))
        
        for i in range(n_iterations):
            # Apply stochastic jitter
            jittered_weather = weather_dict.copy()
            jittered_weather['wind_u'] = base_wind_u * np.random.normal(1.0, wind_jitter_pct)
            jittered_weather['wind_v'] = base_wind_v * np.random.normal(1.0, wind_jitter_pct)
            
            # Fuel anomaly jitter (shift the z-score slightly)
            fuel_noise = np.random.normal(0.0, fuel_jitter_pct, size=base_fuel.shape)
            jittered_weather['fuel_anomaly'] = base_fuel + fuel_noise
            
            # Run deterministic simulation for this iteration
            final_phi = self.simulate_spread(
                initial_phi, terrain_dict, jittered_weather, sim_time_minutes, dt_minutes
            )
            
            # Record burned pixels (where phi <= 0)
            burn_counts += (final_phi <= 0).astype(int)
            
            if (i + 1) % 10 == 0:
                log.info(f"  MC Iteration {i + 1}/{n_iterations} completed.")
                
        # Calculate probabilities
        probability_map = burn_counts / float(n_iterations)
        return probability_map

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Simple test execution to verify shapes and flow
    grid_size = 128
    
    # Create a dummy initial fire (a circle in the center)
    y, x = np.ogrid[-grid_size//2:grid_size//2, -grid_size//2:grid_size//2]
    radius = 10
    initial_phi = np.sqrt(x**2 + y**2) - radius
    
    terrain = {
        'slope': np.full((grid_size, grid_size), 15.0), # 15 degree slope
        'aspect': np.full((grid_size, grid_size), 180.0) # South facing
    }
    weather = {
        'wind_u': 5.0,
        'wind_v': 2.0,
        'fuel_anomaly': np.full((grid_size, grid_size), -1.5) # Very dry
    }
    
    simulator = Muhurta2DSimulator()
    prob_map = simulator.simulate_probabilistic_spread(
        initial_phi, terrain, weather, sim_time_minutes=30, dt_minutes=5.0, n_iterations=10
    )
    
    print(f"Initial Fire Area: {(initial_phi <= 0).sum()} pixels")
    print(f"Probable Fire Area (>50% chance): {(prob_map > 0.5).sum()} pixels")
    print(f"Max Probability: {prob_map.max():.2f}")
