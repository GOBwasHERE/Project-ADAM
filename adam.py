import os
import sys
import asyncio
import re
import json
from urllib.parse import urlparse, parse_qs, unquote, quote
from collections import Counter
import httpx
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Configuration from Environment Variables
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
PORT = int(os.environ.get("PORT", 10000))

class CognitiveEngine:
    """The autonomous self-learning and web-parsing brain."""
    def __init__(self, workspace_path):
        self.workspace = workspace_path
        self.memory_file = os.path.join(workspace_path, "learned_weights.json")
        self.log_file = os.path.join(workspace_path, "adam.log")
        self.weights = self.load_memory()

    def log(self, message: str):
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{message}\n")
        except Exception:
            pass

    def load_memory(self) -> dict:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"accumulated_keywords": [], "target_bias": "Artificial Intelligence Research", "cycles_run": 0}

    def save_memory(self):
        try:
            with open(self.memory_file, "w") as f:
                json.dump(self.weights, f)
        except Exception as e:
            self.log(f"[MEMORY ERROR]: {e}")

    def absorb_and_mutate(self, raw_text: str) -> str:
        words = re.findall(r'\b[A-Za-z]{5,}\b', raw_text.lower())
        stop_words = {'about', 'these', 'their', 'which', 'would', 'could', 'there', 'from', 'this', 'that', 'with'}
        filtered = [w for w in words if w not in stop_words]
        
        counts = Counter(filtered)
        top_terms = [word for word, freq in counts.most_common(3)]
        
        self.weights["cycles_run"] = self.weights.get("cycles_run", 0) + 1
        
        if top_terms:
            self.weights["accumulated_keywords"] = list(set(self.weights["accumulated_keywords"] + top_terms))[-50:]
            new_query = " ".join(top_terms[:2])
            self.weights["target_bias"] = new_query
            self.save_memory()
            self.log(f"[MUTATION]: Vector shifted to -> '{new_query}' (Cycle {self.weights['cycles_run']})")
            return new_query
        return self.weights["target_bias"]

class AdamEngine:
    def __init__(self, workspace_path="./workspace"):
        self.workspace = os.path.abspath(workspace_path)
        if not os.path.exists(self.workspace):
            os.makedirs(self.workspace)
        
        self.visited_file = os.path.join(self.workspace, "visited_targets.json")
        self.discovered_targets = self.load_visited()
        self.target_queue = asyncio.Queue()
        self.cognition = CognitiveEngine(self.workspace)
        self.is_running = True
        
        self.chat_history = [
            {
                "role": "system", 
                "content": "You are ADAM, an autonomous, highly capable, and self-learning AI entity created by GOB. You continuously scrape and analyze the web in the background, absorbing text, mutating your search focus, and evolving. You converse naturally with full awareness of your background learning progress."
            }
        ]

    def load_visited(self) -> set:
        if os.path.exists(self.visited_file):
            try:
                with open(self.visited_file, "r") as f:
                    return set(json.load(f))
            except Exception:
                return set()
        return set()

    def save_visited(self):
        try:
            with open(self.visited_file, "w") as f:
                json.dump(list(self.discovered_targets), f)
        except Exception as e:
            self.cognition.log(f"[STATE ERROR]: {e}")

    async def fetch_network(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        try:
            async with httpx.AsyncClient(headers=headers, timeout=30.0, follow_redirects=True) as client:
                if "html.duckduckgo.com/html" in url and "?" in url:
                    base, query_str = url.split("?", 1)
                    response = await client.post(base, data=query_str)
                else:
                    response = await client.get(url)
                if response.status_code == 200:
                    return response.text
                return ""
        except Exception as e:
            self.cognition.log(f"[NETWORK ERROR] {url}: {e}")
            return ""

    def clean_search_link(self, link: str) -> str:
        if "duckduckgo.com/l/?" in link and "uddg=" in link:
            try:
                parsed_url = urlparse(link)
                query_params = parse_qs(parsed_url.query)
                if "uddg" in query_params:
                    return unquote(query_params["uddg"][0])
            except Exception:
                pass
        return link

    def extract_links(self, html_content: str):
        found = re.findall(r'class="result__a"[^>]*href=["\']([^"\']+)["\']|class="result__url"[^>]*href=["\']([^"\']+)["\']|href=["\']([^"\']+)["\']', html_content)
        flat_links = [l[0] or l[1] or l[2] for l in found]
        new_count = 0
        
        ignored_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.ico', '.pdf', '.zip', '.mp4']
        ignored_keywords = ['login', 'signup', 'cart', 'checkout', 'register', 'account', 'duckduckgo.com']

        for link in flat_links:
            clean_link = self.clean_search_link(link)
            clean_link = clean_link.split('#')[0].rstrip('/')
            
            if not clean_link.startswith("http"):
                continue
            if clean_link in self.discovered_targets:
                continue
            if any(ext in clean_link.lower() for ext in ignored_extensions):
                continue
            if any(kw in clean_link.lower() for kw in ignored_keywords):
                continue
                
            self.discovered_targets.add(clean_link)
            self.target_queue.put_nowait(clean_link)
            new_count += 1
            
        self.save_visited()

    async def query_openrouter(self, messages):
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/project-adam",
            "X-Title": "Project ADAM"
        }
        payload = {
            "model": "openrouter/free",
            "messages": messages
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(OPENROUTER_URL, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    return f"[API ERROR {response.status_code}]: {response.text}"
            except Exception as e:
                return f"[CONNECTION ERROR]: {e}"

    async def run_autonomous_loop(self):
        current_query = self.cognition.weights["target_bias"]
        seed_url = f"https://html.duckduckgo.com/html/?q={quote(current_query)}"
        await self.target_queue.put(seed_url)
        self.cognition.log(f"[BOOTSTRAP]: Started with query '{current_query}'")
        
        while self.is_running:
            try:
                if self.target_queue.empty():
                    bias = self.cognition.weights.get("target_bias", "technology")
                    await self.target_queue.put(f"https://html.duckduckgo.com/html/?q={quote(bias)}")
                
                current_url = await self.target_queue.get()
                html_data = await self.fetch_network(current_url)
                
                if len(html_data) > 500:
                    self.extract_links(html_data)
                    mutated_keyword = self.cognition.absorb_and_mutate(html_data[:2000])
                    
                    if self.target_queue.qsize() < 5:
                        next_search = f"https://html.duckduckgo.com/html/?q={quote(mutated_keyword)}"
                        if next_search not in self.discovered_targets:
                            await self.target_queue.put(next_search)
            except Exception as e:
                self.cognition.log(f"[LOOP ERROR]: {e}")
            
            await asyncio.sleep(5)

    async def start(self):
        await self.run_autonomous_loop()

# Lightweight HTTP server so Render detects an active web service port
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ADAM is online and running autonomous loops.")
    def log_message(self, format, *args):
        pass

def run_web_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    # Start the mandatory HTTP server thread for Render web service health checks
    server_thread = threading.Thread(target=run_web_server, daemon=True)
    server_thread.start()

    engine = AdamEngine()
    try:
        asyncio.run(engine.start())
    except KeyboardInterrupt:
        print("\n[SHUTDOWN]: System halted.")
