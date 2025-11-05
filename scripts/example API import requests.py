import requests

url = "http://127.0.0.1:8000/assessment/api/assessment/"
headers = {
    "Authorization": "Token 98839383f15ac09ab07403e20c1aebe7c6614221",
    "Content-Type": "application/json"
}
data = {
    "name": "LASER-AI Derived Assessment for PFHxS",
    "year": 2025,
    "project_type": "EVIDENCE_SYNTHESIS",
    "description": "Generated automatically from LASER-AI analysis pipeline.",
    "public": False,
    "editable": True,
    "enable_animal": True,
    "enable_epidemiology": True,
    "enable_invitro": True,
    "enable_visuals": True
}
response = requests.post(url, headers=headers, json=data)
print(response.status_code, response.json())
