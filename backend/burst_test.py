import time
import concurrent.futures
import requests

URL = "http://127.0.0.1:8000/api/v1/health"
N = 80

start = time.time()
def hit(i):
    r = requests.get(URL)
    return i, r.status_code

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    results = list(ex.map(hit, range(N)))

elapsed = time.time() - start
codes = [code for _, code in results]
print(f"Fired {N} requests in {elapsed:.2f}s")
print(f"200 OK: {codes.count(200)}   429 blocked: {codes.count(429)}")