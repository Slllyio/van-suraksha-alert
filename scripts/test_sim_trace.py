import asyncio
import websockets
import json

async def run_test():
    uri = 'ws://localhost:8001/ws/simulate'
    try:
        async with websockets.connect(uri) as websocket:
            # Trigger simulation
            params = {
                'lat': 24.640,
                'lon': 77.320,
                'wind_u': 12.0, 
                'wind_v': 4.0,
                'interventions': [
                    {'type': 'FIRELINE', 'geometry': {'type': 'Point', 'coordinates': [77.325, 24.645]}}
                ]
            }
            await websocket.send(json.dumps(params))
            
            print("--- 🛰️ MUHURTA-2D ENGINE ENGAGED ---")
            print("Initial State: Fire detected at Guna Grid 77.320E, 24.640N")
            print("Weather: High Wind (12m/s West-to-East), Dry Fuel Anomaly (-1.0)")
            print("-" * 50)
            
            for i in range(4):
                resp = await websocket.recv()
                data = json.loads(resp)
                time = data.get('time_elapsed')
                # Show the first few coordinates to prove spatial expansion
                coords = data.get('polygons', [[]])[0][:2] 
                print(f"[T+{time:02d} mins] Boundary expanding... Leading Edge: {coords}")
                
            print("-" * 50)
            print("--- ✅ SIMULATION SEGMENT CAPTURED ---")
    except Exception as e:
        print(f"Connection Failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
