"""
Demo script to trigger a workflow via the API locally.
This simulates a user submitting a refactoring request.
"""
import requests
import json
import time

API_URL = "http://localhost:8000"

SAMPLE_CODE = '''def process_user_data(users):
    """
    Process user data and return stats.
    """
    total_age = 0
    valid_users = []
    
    for u in users:
        if u.get('age') and u.get('name'):
            total_age += u['age']
            valid_users.append(u)
            
    avg_age = total_age / len(valid_users) if valid_users else 0
    return {"count": len(valid_users), "average_age": avg_age}
'''

def run_demo():
    print(f"Connecting to API at {API_URL}...")
    
    # 1. Start Refactoring
    print("\n[1/3] Starting new refactoring workflow...")
    try:
        response = requests.post(
            f"{API_URL}/start_refactor",
            json={
                "refactoring_goal": "Add type hints and improve variable names",
                "files": {"user_stats.py": SAMPLE_CODE},
                "max_iterations": 3
            }
        )
        response.raise_for_status()
        data = response.json()
        workflow_id = data['workflow_id']
        print(f"✅ Workflow started! ID: {workflow_id}")
        print("-> CHECK YOUR DASHBOARD NOW! The new workflow should appear shortly.")
        
    except Exception as e:
        print(f"❌ Failed to start workflow: {e}")
        return

    # 2. Monitor status for a bit (just to show progress in terminal too)
    print("\n[2/3] Monitoring status (Ctrl+C to stop)...")
    for _ in range(30):
        try:
            status_resp = requests.get(f"{API_URL}/get_status/{workflow_id}")
            if status_resp.ok:
                status = status_resp.json()
                print(f"Status: {status['status']} | Iteration: {status['iteration_count']} | Err: {status.get('error_message') or ''}")
                if status['status'] in ['COMPLETED', 'AWAITING_REVIEW', 'ERROR']:
                    break
            time.sleep(2)
        except Exception:
            pass

if __name__ == "__main__":
    run_demo()
