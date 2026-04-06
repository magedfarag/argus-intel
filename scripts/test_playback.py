"""Direct API query to debug playback response."""
import requests
import json

# Query playback with correct time range (last 31 hours from NOW)
from datetime import datetime, timedelta, UTC
now = datetime.now(UTC)
start_time = now - timedelta(hours=31)

body = {
    "aoi_id": "618bd4ea-9c30-4f7e-9f88-3c03199ab293",
    "event_types": ["ship_position"],
    "start_time": start_time.isoformat(),
    "end_time": now.isoformat(),
    "limit": 5000
}

print("Querying playback...")
response = requests.post(
    "http://127.0.0.1:8000/api/v1/playback/query",
    json=body,
    headers={"Content-Type": "application/json"}
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Total frames: {data['total_frames']}")
    print(f"Sources: {data['sources_included']}")
    
    if data['frames']:
        # Extract all MMSI values
        mmsis = set()
        for frame in data['frames']:
            mmsi = frame['event']['attributes'].get('mmsi')
            if mmsi:
                mmsis.add(mmsi)
        print(f"\nUnique MMSIs found: {len(mmsis)}")
        print(f"Sample MMSIs: {sorted(list(mmsis))[:10]}")
        
        # Check for flagged ships
        flagged = ['215631000', '538006712', '636021800']
        for mmsi in flagged:
            count = sum(1 for f in data['frames'] if f['event']['attributes'].get('mmsi') == mmsi)
            print(f"  MMSI {mmsi}: {count} events")
            
            # Check coordinate bounds for this MMSI
            lats = []
            lons = []
            for frame in data['frames']:
                if frame['event']['attributes'].get('mmsi') == mmsi:
                    coords = frame['event']['geometry']['coordinates']
                    lons.append(coords[0])
                    lats.append(coords[1])
            
            if lats:
                print(f"    Lat range: [{min(lats):.4f}, {max(lats):.4f}]")
                print(f"    Lon range: [{min(lons):.4f}, {max(lons):.4f}]")
                offshore_violations = [lat for lat in lats if lat < 25.50 or lat > 25.62]
                if offshore_violations:
                    print(f"    ⚠️  WARNING: {len(offshore_violations)} positions outside offshore bounds [25.50, 25.62]")
                else:
                    print(f"    ✓ All positions within offshore bounds")
    else:
        print("No frames returned!")
else:
    print(f"Error: {response.text}")
