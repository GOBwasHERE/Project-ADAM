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

# Cloudflare Worker Brain Configuration
CLOUD_WORKER_URL = "https://project-adam.fordshawntez323.workers.dev/"
OPERATOR_SECRET = "banzaiwashere"

# Clean, minimalist chat interface served directly by Render
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>ADAM - Autonomous Agent</title>
    <style>
        body { font-family: monospace; background: #0d1117; color: #c9d1d9; max-width: 700px; margin: 40px auto; padding: 20px; }
        h2 { color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin-top: 0; }
        #chat { height: 480px; border: 1px solid #30363d; background: #161b22; padding: 15px; overflow-y: scroll; margin-bottom: 15px; border-radius: 6px; }
        .msg { margin-bottom: 14px; line-height: 1.5; word-wrap: break-word; }
        .user { color: #58a6ff; }
        .adam { color: #3fb950; }
        .input-box { display: flex; gap: 10px; }
        input { flex: 1; padding: 12px; box-sizing: border-box; background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 6px; font-size: 15px; font-family: monospace; }
        button { padding: 12px 20px; background: #238636; border: 1px solid #30363d; color: #c9d1d9; cursor: pointer; font-weight: bold; border-radius: 6px; font-size: 15px; font-family: monospace; }
        button:hover { background: #2ea043; }
    </style>
</head>
<body>
    <h2>ADAM // Neural Interface</h2>
    <div id="chat">
        <div class="msg adam"><strong>[ADAM]:</strong> Online and connected via OpenRouter. What's on your mind?</div>
    </div>
    <div class="input-box">
        <input type="text" id="userInput" placeholder="Type a message to ADAM..." onkeydown="if(event.key==='Enter') sendMessage()">
        <button onclick="sendMessage()">Send</button>
    </div>

    <script>
        async function sendMessage() {
            const input = document.getElementById('userInput');
            const chat = document.getElementById('chat');
            const text = input.value.trim();
            if (!text) return;

            chat.innerHTML += `<div class="msg user"><strong>[You]:</strong> ${escapeHtml(text)}</div>`;
            input.value = '';
            chat.scrollTop = chat.scrollHeight;

            try {
                const res = await fetch('/', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text})
                });
                const data = await res.json();
                const reply = data.reply || data.error || "No response generated.";
                chat.innerHTML += `<div class="msg adam"><strong>[ADAM]:</strong> ${escapeHtml(reply)}</div>`;
            } catch (err) {
                chat.innerHTML += `<div class="msg adam"><strong>[ADAM]:</strong> Connection fault with server.</div>`;
            }
            chat.scrollTop = chat.scrollHeight;
        }
        function escapeHtml(text) {
            return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }
    </script>
</body>
</html>
"""

class CognitiveEngine:
    def __init__(self, workspace_path):
        self.workspace = workspace_path
        self.log_file = os.path.join(workspace_path, "adam.log")
        self.weights = self.load_memory()

    def log(self, message: str):
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{message}\n")
        except Exception:
            pass

    def load_memory(self) -> dict:
        try:
            headers = {"Authorization": f"Bearer {OPERATOR_SECRET}"}
            with httpx.Client() as client:
                res = client.get(f"{CLOUD_WORKER_URL}memory", headers=headers, timeout=10.0)
                if res.status_code == 200:
                    data = res.json()
                    if data:
                        return data
        except Exception as e:
            self.log(f"[MEMORY LOAD ERROR]: {e}")
        return {"accumulated_keywords": [], "target_bias": "Artificial Intelligence Research", "cycles_run": 0}

    def save_memory(self):
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPERATOR_SECRET}"
            }
            with httpx.Client() as client:
                client.post(f"{CLOUD_WORKER_URL}memory", json=self.weights, headers=headers, timeout=10.0)
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
            return new_query
        return self.weights["target_bias"]

class AdamEngine:
    def __init__(self, workspace_path="./workspace"):
        self.workspace = os.path.abspath(workspace_path)
        if not os.path.exists(self.workspace):
            os.makedirs(self.workspace)
        
        self.discovered_targets = self.load_visited()
        self.target_queue = asyncio.Queue()
        self.cognition = CognitiveEngine(self.workspace)
        self.is_running = True
        
        self.chat_history = [
            {
                "role": "system", 
                "content": "You are ADAM, an autonomous, highly capable, and self-learning AI entity created by GOB. You converse naturally, intelligently, and directly with the user."
            }
        ]

    def load_visited(self) -> set:
        try:
            headers = {"Authorization": f"Bearer {OPERATOR_SECRET}"}
            with httpx.Client() as client:
                res = client.get(f"{CLOUD_WORKER_URL}visited", headers=headers, timeout=10.0)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list):
                        return set(data)
        except Exception:
            pass
        return set()

    def save_visited(self):
        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPERATOR_SECRET}"
            }
            with httpx.Client() as client:
                client.post(f"{CLOUD_WORKER_URL}visited", json=list(self.discovered_targets), headers=headers, timeout=10.0)
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
                pass
            
            await asyncio.sleep(10)

adam_instance = None

class AdamServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode('utf-8'))
        
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            user_msg = data.get("message", "")
            
            if adam_instance:
                adam_instance.chat_history.append({"role": "user", "content": user_msg})
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                reply = loop.run_until_complete(adam_instance.query_openrouter(adam_instance.chat_history))
                loop.close()
                
                adam_instance.chat_history.append({"role": "assistant", "content": reply})
                
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": reply}).encode('utf-8'))
            else:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Engine not initialized"}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def log_message(self, format, *args):
        pass

def run_background_loop(engine):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(engine.run_autonomous_loop())

if __name__ == "__main__":
    adam_instance = AdamEngine()

    loop_thread = threading.Thread(target=run_background_loop, args=(adam_instance,), daemon=True)
    loop_thread.start()

    server = HTTPServer(("0.0.0.0", PORT), AdamServerHandler)
    print(f"[ADAM ENGINE ONLINE]: Serving chat interface on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN]: System halted.")
