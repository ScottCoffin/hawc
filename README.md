# Health Assessment Workspace Collaborative (HAWC)

[![Documentation Status](https://readthedocs.org/projects/hawc/badge/)](https://hawc.readthedocs.io)

HAWC is a web-based platform for capturing key data and analyses used in human-health assessments of environmental chemicals — enabling hazard identification and derivation of levels of concern.

---

## 🚀 Local Development Setup (Conda + PostgreSQL + VS Code)

These are step-by-step instructions for running HAWC locally on Windows using **Miniconda**, **PostgreSQL**, and **VS Code**.

> ✅ VS Code users: once setup is complete, you can use the provided `.vscode/tasks.json` to **start/stop backend, frontend, and database with one click**.

### 1. Prerequisites

* Install **Miniconda (Python 3.13, 64‑bit)** → [https://docs.conda.io/en/latest/miniconda.html](https://docs.conda.io/en/latest/miniconda.html)
* Install **VS Code** with the **Python** + **ESLint/Ruff** + **Yarn** extensions
* Git clone this repository

### 2. Create & activate the Conda environment

```powershell
conda create -n hawc python=3.13 -y
conda activate hawc
```

### 3. Install backend & frontend dependencies

```powershell
poe sync-dev  # installs Python deps + JS deps via yarn
```

### 4. Initialize the local PostgreSQL database

```powershell
# (only first time)
pg_ctl -D "%HOMEPATH%/dev/pgdata-hawc" -l "%HOMEPATH%/dev/pgdata-hawc/logs/logfile" start
createuser --superuser --no-password hawc
createdb -U hawc hawc
createdb -U hawc hawc-test
```

### 5. Apply Django migrations

```powershell
python manage.py migrate
```

### 6. Start the development servers

**Backend:**

```powershell
poe run-py
```

**Frontend (in a second terminal):**

```powershell
cd frontend
yarn start   # or: poe run-js
```

Then visit → **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🔐 Create your admin user

```powershell
python manage.py createsuperuser
```

Login at: **[http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)**

---

## 🛑 Stopping Services

```powershell
# Stop database
pg_ctl -D "%HOMEPATH%/dev/pgdata-hawc" stop
```

If that doesn't work, try:
```powershell
pg_ctl -D "C:\Users\Scott.Coffin\dev\pgdata-hawc" start
```

(You can also add `pgstart` and `pgstop` helper functions to your PowerShell profile.)

---

## ▶️ Using VS Code Tasks (Recommended)

Once your environment is set up, you can run HAWC using VS Code tasks instead of manually starting services.

**1. Open Command Palette (ctrl + shift + P) → `Tasks: Run Task`**
You’ll see tasks like:

* `run backend` → starts Django dev server
* `run frontend` → starts `yarn`/JS hot reload
* `start db` → starts local PostgreSQL
* `stop db` → stops database cleanly

These tasks automatically activate the `hawc` Conda environment.

**2. Tasks are defined in `.vscode/tasks.json`.**
You may customize these or add additional helper tasks.

---

## Additional Documentation

* [Systematic Evidence Map Intake](docs/systematic_evidence_map_intake.md) – Guidance for preparing and importing interoperable systematic evidence map data.

---

Let us know if you want Docker instructions or auto‑launch scripts included.

## API Uploading
To access the API documentation in HAWC, login as admin in the local deployment, navigate to "Admin" tab, then click on "Swagger".


* Create a user token using http://127.0.0.1:8000/admin/authtoken/ and copy that key (API token)

* Ensure an assessment exists in HAWC for the data being uploaded, with a list of studies that has study identifier values matching those in the Laser AI

* To check if the assessment exists and obtain details:

```powershell
(hawc) > python
```
->
```python
import requests

url = "http://127.0.0.1:8000/assessment/api/assessment/"
params = {"assessment_id": "1"} # enter assessment ID associated with assessment
headers = {"Authorization": "Token 98839383f15ac09ab07403e20c1aebe7c6614221"}

r = requests.get(url, headers=headers, params=params)
print(r.status_code)
print(r.json())
```

* HAWC requires JSON format for input, while Laser AI exports extracted data in either csv or excel format. Accordingly, in Python:

```python
import pandas as pd, json, numpy as np

df = pd.read_csv("tests/data/laser_ai/laser_animal_test.csv") #replace with filename

# Replace invalid numeric values (NaN, inf, -inf) with None (JSON null)
df = df.replace([np.nan, np.inf, -np.inf], None)

records = df.to_dict(orient="records")

with open("tests/data/laser_ai/laser_ai_studies.json", "w") as f:
    json.dump(records, f, indent=2)

# optionally validate before upload
import math
bad = [(i, c, v) for i, row in df.iterrows() for c, v in row.items() if isinstance(v, float) and not math.isfinite(v)]
print(bad)  # should be empty list []
```
 - this creates laser_ai_studies.json file

 ## Upload via API
 ### Verify formatting with custom python script (currently only designed for epi - NOT for animal studies)

 * will not work for animal studies:
 ```powershell
conda activate hawc
python "c:/Users/Scott.Coffin/OneDrive - California OEHHA/R_new/hawc/scripts/verify_systematic_evidence_map_example.py" "C:\Users\Scott.Coffin\OneDrive - California OEHHA\R_new\hawc\tests\data\laser_ai\laser_animal_test.csv"

 ```

 ###
  ```python
import requests, json

url = "http://127.0.0.1:8000/study/api/study/"
headers = {
    "Authorization": "Token 98839383f15ac09ab07403e20c1aebe7c6614221",
    "Content-Type": "application/json"
}

with open("tests/data/laser_ai/laser_animal_test.json") as f:
    data = json.load(f)

r = requests.post(url, headers=headers, json=data)
print(r.status_code)
print(r.json())
```


