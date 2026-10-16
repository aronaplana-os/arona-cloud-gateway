#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arona Cloud Gateway — 常驻云端的最小 AI 网关（纯标准库，可直接跑在任意容器 PaaS）

端点（OpenAI 兼容）：
  GET  /health
  GET  /v1/models
  POST /v1/chat/completions     model: auto | @cf/... | pollinations:openai-fast | llm7:gpt-oss:20b

环境变量：
  ARONA_KEY      必需，客户端 Bearer 校验
  CF_AI_TOKEN    可选，Cloudflare Workers AI REST 令牌（有则启用 @cf 模型）
  CF_ACCOUNT_ID  可选，默认内置
  PORT           可选，默认 8080
"""
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
ARONA_KEY = os.environ.get("ARONA_KEY", "")
CF_TOKEN = os.environ.get("CF_AI_TOKEN", "")
CF_ACCOUNT = os.environ.get("CF_ACCOUNT_ID", "26798a492cad412e10c0246649ca2ccf")

CF_SMALL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
CF_BIG = "@cf/openai/gpt-oss-120b"
CF_EXTRA = ["@cf/qwen/qwen2.5-coder-32b-instruct", "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b", "@cf/zai-org/glm-5.3-flash"]
EXTRA = ["pollinations:openai-fast", "pollinations:openai", "llm7:gpt-oss:20b"]


def http_json(url, data=None, headers=None, timeout=120):
    body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:300]}
    except Exception as e:
        return 0, {"error": str(e)}


def est_tokens(payload):
    try:
        txt = json.dumps(payload.get("messages") or [], ensure_ascii=False)
    except Exception:
        return 0
    return int(len(txt) / 3.2) + int(payload.get("max_tokens") or 0)


def call_cf(model, payload):
    if not CF_TOKEN:
        raise RuntimeError("CF_AI_TOKEN not set")
    url = "https://api.cloudflare.com/client/v4/accounts/%s/ai/run/%s" % (CF_ACCOUNT, model)
    st, doc = http_json(url, {"messages": payload.get("messages"),
                              "max_tokens": payload.get("max_tokens") or 1024,
                              **({"temperature": payload["temperature"]} if payload.get("temperature") is not None else {})},
                        {"Authorization": "Bearer " + CF_TOKEN}, 110)
    if st != 200 or (isinstance(doc, dict) and doc.get("success") is False):
        raise RuntimeError("cf %s: %s" % (st, json.dumps(doc)[:160]))
    res = doc.get("result") or {}
    text = res if isinstance(res, str) else (res.get("response") or json.dumps(res))
    return text, (res.get("usage") if isinstance(res, dict) else {}) or {}


def call_upstream(kind, model, payload):
    if kind == "pollinations":
        url, hdr = "https://text.pollinations.ai/openai", {}
    elif kind == "llm7":
        url, hdr = "https://api.llm7.io/v1/chat/completions", {"Authorization": "Bearer " + os.environ.get("LLM7_KEY", "unused")}
    else:
        raise RuntimeError("unknown upstream " + kind)
    st, doc = http_json(url, {"model": model, "messages": payload.get("messages"),
                              "max_tokens": payload.get("max_tokens") or 1024}, hdr, 110)
    if st != 200:
        raise RuntimeError("%s %s: %s" % (kind, st, json.dumps(doc)[:160]))
    msg = ((doc.get("choices") or [{}])[0].get("message") or {})
    return msg.get("content") or msg.get("reasoning") or "", doc.get("usage") or {}


def handle_chat(payload):
    want = payload.get("model") or "auto"
    chain = []
    if want.startswith("@cf/"):
        chain.append(("cf", want))
    elif ":" in want:
        k, rest = want.split(":", 1)
        chain.append((k, rest))
    elif want not in ("auto", "best", "fast", ""):
        chain.append(("cf", want))
    if not chain:
        first = CF_BIG if est_tokens(payload) >= 12000 else CF_SMALL
        second = CF_SMALL if first == CF_BIG else CF_BIG
        chain = [("cf", first), ("cf", second), ("pollinations", "openai-fast")]
    trail = []
    t0 = time.time()
    for kind, model in chain:
        try:
            if kind == "cf":
                text, usage = call_cf(model, payload)
            else:
                text, usage = call_upstream(kind, model, payload)
            return 200, {
                "id": "chatcmpl-%d" % int(time.time() * 1000), "object": "chat.completion",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": usage.get("prompt_tokens", 0) or 0,
                          "completion_tokens": usage.get("completion_tokens", 0) or 0,
                          "total_tokens": usage.get("total_tokens", 0) or 0},
                "_gateway": {"provider": kind, "model": model, "latency": round(time.time() - t0, 2),
                             "trail": trail + ["%s:%s:OK" % (kind, model)]},
            }
        except Exception as e:
            trail.append("%s:%s:ERR(%s)" % (kind, model, str(e)[:80]))
    return 502, {"error": {"message": "all providers failed", "trail": trail}}


class H(BaseHTTPRequestHandler):
    server_version = "arona-cloud-gateway/1.0"

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization,Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {"ok": True})

    def do_GET(self):
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True, "service": "arona-cloud-gateway", "ts": int(time.time() * 1000),
                                    "cf": bool(CF_TOKEN)})
        if self.path.startswith("/v1/models"):
            if not self._auth():
                return self._send(401, {"error": {"message": "unauthorized"}})
            ids = [CF_SMALL, CF_BIG] + CF_EXTRA + EXTRA
            return self._send(200, {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "arona"} for i in ids]})
        return self._send(404, {"error": {"message": "not found"}})

    def _auth(self):
        if not ARONA_KEY:
            return True
        got = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        return got == ARONA_KEY

    def do_POST(self):
        if not self.path.startswith("/v1/chat/completions"):
            return self._send(404, {"error": {"message": "not found"}})
        if not self._auth():
            return self._send(401, {"error": {"message": "unauthorized"}})
        try:
            ln = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(ln).decode("utf-8", "replace") or "{}")
        except Exception as e:
            return self._send(400, {"error": {"message": "bad json: %s" % e}})
        code, doc = handle_chat(payload)
        self._send(code, doc)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    print("arona-cloud-gateway listening on 0.0.0.0:%d (cf=%s)" % (PORT, bool(CF_TOKEN)), flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
