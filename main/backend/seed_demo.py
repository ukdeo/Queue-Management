"""
Seed 10 diverse tokens per department per day (20 today + 20 tomorrow).
Run:  python seed_demo.py
"""
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_URL = "http://localhost:8000"
NPT = ZoneInfo("Asia/Kathmandu")

# ── Org & Queues ─────────────────────────────────────────────────────────────
orgs = requests.get(f"{BASE_URL}/organizations").json()
org_id = orgs[0]["id"]
queues = requests.get(f"{BASE_URL}/organizations/{org_id}/queues").json()

if len(queues) < 1:
    print("No queues found. Create at least one queue first."); exit(1)

for q in queues:
    print(f"  Queue: {q['name']} ({q['id'][:8]}...)")

# ── Dates ────────────────────────────────────────────────────────────────────
now_npt  = datetime.now(NPT)
today    = now_npt.strftime("%Y-%m-%d")
tomorrow = (now_npt + timedelta(days=1)).strftime("%Y-%m-%d")

# ── 10 diverse people per department (different phones each day block) ────────
# Priority: 0=Normal, 100=Urgent, 1000=Critical
DEPT_A_TODAY = [
    ("Ram Prasad Shrestha",    "+9779801001001", 0,    "Normal"),
    ("Sita Devi Maharjan",     "+9779801002002", 1000, "Critical – Emergency"),
    ("Bikram Bahadur Rai",     "+9779801003003", 0,    "Normal"),
    ("Kamala Kumari Tamang",   "+9779801004004", 100,  "Urgent – Elderly"),
    ("Dev Narayan Yadav",      "+9779801005005", 0,    "Normal"),
    ("Anita Shrestha Gurung",  "+9779801006006", 0,    "Normal"),
    ("Suresh Kumar Thapa",     "+9779801007007", 1000, "Critical – Infant"),
    ("Puja Laxmi Karki",       "+9779801008008", 100,  "Urgent – Pregnant"),
    ("Navin Prasad Pokhrel",   "+9779801009009", 0,    "Normal"),
    ("Gita Maya Lama",         "+9779801010010", 0,    "Normal"),
]

DEPT_B_TODAY = [
    ("Rajesh Kumar Koirala",   "+9779802001001", 0,    "Normal"),
    ("Sunita Devi Bista",      "+9779802002002", 100,  "Urgent – Disabled"),
    ("Arun Bahadur Magar",     "+9779802003003", 0,    "Normal"),
    ("Nirmala Rai Limbu",      "+9779802004004", 0,    "Normal"),
    ("Prakash Narayan Paudel", "+9779802005005", 1000, "Critical – Cardiac"),
    ("Meena Kumari Pandey",    "+9779802006006", 0,    "Normal"),
    ("Roshan Bahadur Khatri",  "+9779802007007", 0,    "Normal"),
    ("Sarita Giri Joshi",      "+9779802008008", 100,  "Urgent – Elderly 80+"),
    ("Deepak Raj Bhattarai",   "+9779802009009", 0,    "Normal"),
    ("Laxmi Devi Dhungana",    "+9779802010010", 0,    "Normal"),
]

DEPT_A_TOMORROW = [
    ("Hari Prasad Neupane",    "+9779803001001", 0,    "Normal"),
    ("Durga Devi Adhikari",    "+9779803002002", 100,  "Urgent – Post Surgery"),
    ("Tilak Bahadur Nepali",   "+9779803003003", 0,    "Normal"),
    ("Binita Shrestha Rana",   "+9779803004004", 0,    "Normal"),
    ("Umesh Kumar Ghimire",    "+9779803005005", 1000, "Critical – Stroke"),
    ("Sabina Malla Thakuri",   "+9779803006006", 0,    "Normal"),
    ("Govind Prasad Regmi",    "+9779803007007", 0,    "Normal"),
    ("Rekha Kumari Sharma",    "+9779803008008", 100,  "Urgent – Wheelchair"),
    ("Santosh Raj Basnet",     "+9779803009009", 0,    "Normal"),
    ("Indira Devi Subedi",     "+9779803010010", 0,    "Normal"),
]

DEPT_B_TOMORROW = [
    ("Bishnu Prasad Aryal",    "+9779804001001", 0,    "Normal"),
    ("Mina Kumari Timilsina",  "+9779804002002", 1000, "Critical – Burn"),
    ("Chandra Bahadur Oli",    "+9779804003003", 0,    "Normal"),
    ("Puspa Lata Khadka",      "+9779804004004", 0,    "Normal"),
    ("Manoj Kumar Acharya",    "+9779804005005", 100,  "Urgent – Elderly 90+"),
    ("Sushila Devi Thapa",     "+9779804006006", 0,    "Normal"),
    ("Rajan Bahadur Gurung",   "+9779804007007", 0,    "Normal"),
    ("Anupama Rani Shrestha",  "+9779804008008", 1000, "Critical – Infant"),
    ("Dinesh Raj Pokhrel",     "+9779804009009", 0,    "Normal"),
    ("Kamana Devi Dhakal",     "+9779804010010", 100,  "Urgent – Fracture"),
]

# ── Seeder ───────────────────────────────────────────────────────────────────
def seed_batch(queue, people, service_date, label):
    print(f"\n  [{queue['name']}] {label} ({service_date})")
    ok = skip = err = 0
    for (name, phone, priority, desc) in people:
        payload = {
            "name": name,
            "phone": phone,
            "service_date": service_date,
            "priority_level": priority,
        }
        r = requests.post(f"{BASE_URL}/queues/{queue['id']}/tokens", json=payload)
        if r.status_code in (200, 201):
            num = r.json().get("number", "?")
            print(f"    ✓ #{num:>3}  [{desc:<25}] {name}")
            ok += 1
        elif r.status_code == 409:
            print(f"    ⚠ SKIP (already booked): {name}")
            skip += 1
        else:
            print(f"    ✗ ERR {r.status_code}: {name} – {r.json().get('detail','')}")
            err += 1
    print(f"    → {ok} created, {skip} skipped, {err} errors")

# ── Map batches to queues ─────────────────────────────────────────────────────
dept_a = queues[0]
dept_b = queues[1] if len(queues) > 1 else queues[0]

print(f"\n{'='*55}")
print(f"  SEEDING TODAY ({today})")
print(f"{'='*55}")
seed_batch(dept_a, DEPT_A_TODAY, today, "Dept A – Today")
seed_batch(dept_b, DEPT_B_TODAY, today, "Dept B – Today")

print(f"\n{'='*55}")
print(f"  SEEDING TOMORROW ({tomorrow})")
print(f"{'='*55}")
seed_batch(dept_a, DEPT_A_TOMORROW, tomorrow, "Dept A – Tomorrow")
seed_batch(dept_b, DEPT_B_TOMORROW, tomorrow, "Dept B – Tomorrow")

print(f"\n{'='*55}")
print(f"  ✅ Done! 40 tokens seeded across {len(queues)} dept(s).")
print(f"     Switch dates in the admin dashboard to preview.")
print(f"{'='*55}\n")
