#!/usr/bin/env python3
"""Quick test of LoL Esports API"""
import requests

# Test LoL Esports API (no Riot API key needed!)
url = "https://esports-api.lolesports.com/persisted/gw/getLive"
headers = {"x-api-key": "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"}
params = {"hl": "en-US"}

r = requests.get(url, headers=headers, params=params)
print(f"Status: {r.status_code}")

data = r.json()
events = data.get("data", {}).get("schedule", {}).get("events", [])
live_events = [e for e in events if e.get("state") == "inProgress"]

print(f"Total events: {len(events)}")
print(f"Live events: {len(live_events)}")

for event in live_events:
    match = event.get("match", {})
    teams = match.get("teams", [])
    if len(teams) >= 2:
        print(f"  - {teams[0].get('name')} vs {teams[1].get('name')}")
