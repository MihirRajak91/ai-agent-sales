import requests

base_url = "http://localhost:8000"

def get_token():
    resp = requests.get(f"{base_url}/auth/token/dev")
    resp.raise_for_status()
    return resp.json()["access_token"]

headers = {"Authorization": f"Bearer {get_token()}"}
query = "show open leads"
resp = requests.get(f"{base_url}/api/leads/search", params={"q": query}, headers=headers)
print(resp.status_code)
print(resp.text)
