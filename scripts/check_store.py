"""Check event store contents directly."""
import httpx

# Try a minimal query without filters
response = httpx.post(
    "http://127.0.0.1:8000/api/v1/playback/query",
    json={
        "start_time": "2026-03-01T00:00:00Z",
        "end_time": "2026-04-01T23:59:59Z",
        "limit": 5000
    },
    timeout=10.0
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Total frames: {data['total_frames']}")
    
    # Count by event type
    event_types = {}
    ship_count = 0
    for frame in data['frames']:
        et = frame['event']['event_type']
        event_types[et] = event_types.get(et, 0) + 1
        if et == 'ship_position':
            ship_count += 1
    
    print(f"\nEvent types found:")
    for et, count in sorted(event_types.items()):
        print(f"  {et}: {count}")
    
    print(f"\nShip position events: {ship_count}")
    
    if ship_count > 0:
        print(f"\nFirst 3 ship events:")
        ships_shown = 0
        for frame in data['frames']:
            event = frame['event']
            if event['event_type'] == 'ship_position':
                print(f"\n  {ships_shown+1}. MMSI: {event['payload']['mmsi']}")
                print(f"     Time: {event['event_time']}")
                print(f"     Position: {event['payload']['position']['coordinates']}")
                ships_shown += 1
                if ships_shown >= 3:
                    break
else:
    print(f"Error: {response.text}")
