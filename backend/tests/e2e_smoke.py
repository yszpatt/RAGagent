#!/usr/bin/env python3
"""KnowledgePilot 端到端冒烟测试。

流程：启动 uvicorn + RQ worker → 等待 /health → 上传 txt/md 样例文档 →
轮询文档状态至 completed → 调用 /chat 断言回答与引用 → 打印 PASS/FAIL 汇总 → 清理进程。

前置条件（脚本不代劳，便于失败时人工排查）：
  1. PostgreSQL (kp-pg) 运行在 5432，schema 已建（Task 2/5）
  2. Redis 运行在 6379（docker run -d --name kp-redis -p 6379:6379 redis:7-alpine）
  3. bge-m3 模型已缓存于 ~/.cache/huggingface（缺省时 worker 会尝试联网下载，可能失败）

用法（在 backend/ 下执行）：
  .venv/bin/python tests/e2e_smoke.py
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

BACKEND_DIR = Path(__file__).resolve().parents[1]
VENV_BIN = BACKEND_DIR / ".venv" / "bin"
BASE_URL = "http://localhost:8000"

# bge-m3 缓存存在时启用 HF 离线模式：避免已下载过的大模型因
# hf.co 文件传输被墙/慢而反复触发下载（缓存在本地，离线可直接用）。
_MODEL_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / "models--BAAI--bge-m3"
if _MODEL_CACHE.exists() and "KP_E2E_ONLINE" not in os.environ:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    print("[setup] 检测到本地 bge-m3 缓存，启用 HF 离线模式（KP_E2E_ONLINE=1 可关闭）")
HEALTH_RETRY = 30          # /health 就绪最长等待（秒）
DOC_POLL_TIMEOUT = 180     # 文档处理完成最长等待（秒，bge-m3 首次加载慢）
POLL_INTERVAL = 3

TXT_CONTENT = (
    "违约金条款：卖方违约需支付合同金额的10%作为违约金，买方违约需支付合同金额的5%作为违约金。"
    "本合同适用中华人民共和国法律。争议解决方式为协商或向甲方所在地人民法院提起诉讼。"
)
MD_CONTENT = (
    "报销流程：先在系统提交申请，3个工作日内审批。审批通过后，财务将在5个工作日内完成打款。"
    "发票需为增值税专用发票，抬头必须与报销人所在公司一致。"
)


class SmokeResult:
    """记录单步结果，汇总打印 PASS/FAIL。"""

    def __init__(self):
        self.steps = []

    def record(self, name, ok, detail=""):
        self.steps.append((name, bool(ok), detail))
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {name}" + (f"  -- {detail}" if detail else ""))

    def summary(self):
        passed = sum(1 for _, ok, _ in self.steps if ok)
        failed = [n for n, ok, _ in self.steps if not ok]
        print("\n========== E2E SMOKE 汇总 ==========")
        print(f"通过: {passed}/{len(self.steps)}")
        if failed:
            print("失败项: " + ", ".join(failed))
            return False
        print("全部通过 ✓")
        return True


def start_process(cmd, log_path, name):
    """启动后台子进程，stdout/stderr 重定向到日志文件。"""
    f = open(log_path, "wb")
    p = subprocess.Popen(
        cmd, cwd=str(BACKEND_DIR), stdout=f, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    print(f"[setup] 启动 {name} (pid={p.pid}, log={log_path.name})")
    return p, f


def wait_health(result):
    deadline = time.time() + HEALTH_RETRY
    while time.time() < deadline:
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200 and r.json().get("status") == "ok":
                result.record("等待 /health 就绪", True)
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    result.record("等待 /health 就绪", False, "30s 内未就绪，见 api.log")
    return False


def upload_doc(path):
    with open(path, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/v1/documents/upload",
            files={"file": (Path(path).name, f)},
            timeout=30,
        )
    r.raise_for_status()
    return r.json()["document_id"]


def wait_doc_completed(doc_id, result):
    deadline = time.time() + DOC_POLL_TIMEOUT
    started = time.time()
    last_status = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/v1/documents/{doc_id}", timeout=10)
        # 上传端点只入队，documents 行由 worker 在 run_ingestion 内落库；
        # worker 未开工前 GET 会 404，视为"尚未创建"继续轮询即可。
        if r.status_code == 404:
            last_status = "pending"
            time.sleep(POLL_INTERVAL)
            continue
        data = r.json()["data"]
        last_status = data["status"]
        if last_status == "completed":
            elapsed = int(time.time() - started)
            result.record(f"文档 {doc_id[:8]} 处理完成", True, f"耗时 {elapsed}s")
            return True
        if last_status == "failed":
            result.record(f"文档 {doc_id[:8]} 处理完成", False, f"status=failed: {data.get('error_message')}")
            return False
        time.sleep(POLL_INTERVAL)
    result.record(f"文档 {doc_id[:8]} 处理完成", False, f"{DOC_POLL_TIMEOUT}s 超时，最后 status={last_status}")
    return False


def chat(query, result, expect_substr=None):
    r = requests.post(
        f"{BASE_URL}/api/v1/chat",
        headers={"Content-Type": "application/json"},
        json={"query": query},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    answer, citations, no_answer = data["answer"], data["citations"], data["no_answer"]
    ok = (not no_answer) and (not citations == [])
    if expect_substr:
        ok = ok and expect_substr in answer
    detail = f"no_answer={no_answer}, citations={len(citations)}, answer='{answer[:60]}…'"
    result.record(f"chat[{query[:12]}]", ok, detail)
    return data


def main():
    if not (VENV_BIN / "uvicorn").exists():
        print("缺少 .venv/bin/uvicorn，请先: pip install 'uvicorn[standard]'")
        sys.exit(2)

    # 前置依赖探测（只提示不自动拉起，避免掩盖失败原因）
    for host, port, name in [("localhost", 5432, "PostgreSQL(kp-pg)"), ("localhost", 6379, "Redis(kp-redis)")]:
        import socket
        s = socket.socket()
        try:
            s.settimeout(1)
            s.connect((host, port))
            print(f"[setup] {name} 已就绪 :{port}")
        except OSError:
            print(f"[setup] WARN: {name} 不可达 :{port}，任务可能失败")
        finally:
            s.close()

    result = SmokeResult()
    log_dir = Path(tempfile.gettempdir()) / "kp_e2e"
    log_dir.mkdir(parents=True, exist_ok=True)

    procs = []
    log_files = []
    try:
        # 1) 启动 uvicorn 与 RQ worker
        api_proc, api_log = start_process(
            [str(VENV_BIN / "uvicorn"), "app.main:app", "--port", "8000"],
            log_dir / "api.log", "uvicorn", )
        procs.append(api_proc); log_files.append(api_log)
        worker_proc, worker_log = start_process(
            [str(VENV_BIN / "rq"), "worker", "ingestion"],
            log_dir / "worker.log", "rq worker", )
        procs.append(worker_proc); log_files.append(worker_log)

        # 2) 等待健康检查
        if not wait_health(result):
            return result.summary()

        # 3) 创建样例文档
        tmpdir = Path(tempfile.mkdtemp(prefix="kp_sample_"))
        txt_path = tmpdir / "sample.txt"
        md_path = tmpdir / "sample.md"
        txt_path.write_text(TXT_CONTENT, encoding="utf-8")
        md_path.write_text(MD_CONTENT, encoding="utf-8")

        # 4) 上传 + 轮询完成
        txt_id = upload_doc(txt_path)
        result.record(f"上传 {txt_path.name}", True, f"document_id={txt_id}")
        md_id = upload_doc(md_path)
        result.record(f"上传 {md_path.name}", True, f"document_id={md_id}")

        for doc_id, doc_name in [(txt_id, "txt"), (md_id, "md")]:
            wait_doc_completed(doc_id, result)

        # 5) 问答断言（txt 违约金 + md 报销流程）
        chat("违约金是多少？", result, expect_substr="违约金")
        chat("报销流程怎么走？", result, expect_substr="报销流程")

        # 6) 兜底断言：明显无关问题应触发 no-answer（可选验证护栏）
        r = requests.post(
            f"{BASE_URL}/api/v1/chat",
            headers={"Content-Type": "application/json"},
            json={"query": "今天天气怎么样？"},
            timeout=60,
        )
        data = r.json()
        result.record("无关问题触发 no-answer 护栏",
                      bool(data.get("no_answer")) and not data.get("citations"),
                      f"no_answer={data.get('no_answer')}")

        return result.summary()
    except Exception as e:
        result.record("冒烟脚本执行异常", False, f"{type(e).__name__}: {e}")
        return result.summary()
    finally:
        # 清理：先杀 worker 再杀 uvicorn
        for p in procs:
            if p.poll() is None:
                p.terminate()
        time.sleep(2)
        for p in procs:
            if p.poll() is None:
                p.kill()
        for f in log_files:
            try:
                f.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
