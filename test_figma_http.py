import requests
import json

url = "https://mcp.figma.com/mcp"

# Test standard JSON-RPC tools/list
payloads = [
    {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    },
    {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }
]

for i, payload in enumerate(payloads):
    print(f"\n--- Payload {i+1} ({payload['method']}) ---")
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        print(f"Status Code: {response.status_code}")
        print("Response Headers:")
        for k, v in response.headers.items():
            print(f"  {k}: {v}")
        print("Response Body:")
        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(response.text)
    except Exception as e:
        print(f"Error: {e}")
