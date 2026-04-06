"""Validate ship positions from playback response."""
import json
from pathlib import Path

def main():
    # Load playback response
    data = json.loads(Path("playback_response.json").read_text())
    
    # Extract all events from frames
    all_events = []
    for frame in data['frames']:
        all_events.extend(frame['events'])
    
    print(f"Total events: {len(all_events)}")
    print(f"Total frames: {data['total_frames']}")
    
    # Filter for flagged MMSIs
    flagged_mmsis = ['215631000', '538006712', '636021800']
    filtered_events = [
        e for e in all_events 
        if e['payload'].get('mmsi') in flagged_mmsis
    ]
    
    print(f"Events for flagged MMSIs: {len(filtered_events)}")
    
    # Check coordinate bounds for each MMSI
    for mmsi in flagged_mmsis:
        mmsi_events = [e for e in filtered_events if e['payload'].get('mmsi') == mmsi]
        if not mmsi_events:
            print(f"\nMMSI {mmsi}: NO EVENTS FOUND")
            continue
            
        print(f"\nMMSI {mmsi}: {len(mmsi_events)} events")
        
        # Extract coordinates
        lats = []
        lons = []
        for event in mmsi_events:
            coords = event['payload']['position']['coordinates']
            lons.append(coords[0])
            lats.append(coords[1])
        
        print(f"  Lat range: [{min(lats):.4f}, {max(lats):.4f}]")
        print(f"  Lon range: [{min(lons):.4f}, {max(lons):.4f}]")
        
        # Check offshore bounds (lat 25.50-25.62)
        offshore_violations = [lat for lat in lats if lat < 25.50 or lat > 25.62]
        if offshore_violations:
            print(f"  ⚠️  WARNING: {len(offshore_violations)} positions outside offshore bounds [25.50, 25.62]")
        else:
            print(f"  ✓ All positions within offshore bounds")
        
        # Show first 3 positions
        print(f"  First 3 positions:")
        for event in mmsi_events[:3]:
            coords = event['payload']['position']['coordinates']
            time = event['timestamp']
            print(f"    {time}: [{coords[0]:.4f}, {coords[1]:.4f}]")

if __name__ == "__main__":
    main()
