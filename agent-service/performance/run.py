"""Headless, budgeted performance runner. Run from any working directory."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

from stats import classify, summarize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CONFIG = HERE / "workloads.json"


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def container_resources() -> dict:
    try:
        result = subprocess.run(["docker", "inspect", "agent-house-price-python-agent"],
                                cwd=ROOT, capture_output=True, text=True)
    except OSError:
        return {"status": "未获取"}
    if result.returncode:
        return {"status": "未获取"}
    item = json.loads(result.stdout)[0]
    return {"image_id": item.get("Image"), "memory_limit_bytes": item.get("HostConfig", {}).get("Memory"),
            "nano_cpus": item.get("HostConfig", {}).get("NanoCpus")}


def read_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def max_spawned_users(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return max((int(row.get("User Count") or 0) for row in csv.DictReader(stream)), default=0)


def preflight(client: httpx.Client, name: str, case: dict, capabilities: dict, timeout: float) -> tuple[bool, str, dict | None]:
    if name == "sql_hive" and not capabilities.get("hive"):
        return False, "Hive 未启用，未测", None
    if name != "health" and not capabilities.get("model_configured"):
        return False, "LLM 未配置", None
    try:
        if name == "health":
            response = client.get("/health", timeout=timeout)
            return (response.status_code == 200 and response.json() == {"status": "ok"}, "进程健康检查失败", response.json())
        response = client.post("/api/v1/chat", json={"message": case["question"]}, timeout=timeout)
        body = response.json()
        category = classify(response.status_code, body, None, case)
        if category != "success":
            return False, f"预检题 {case['case_id']} 未通过：{category}，源={body.get('details', {}).get('data_source')}，trace_id={body.get('trace_id')}", body
        return True, "", body
    except (httpx.HTTPError, ValueError) as exc:
        return False, f"预检请求失败：{type(exc).__name__}", None


def report(meta: dict, results: list[dict], output: Path) -> None:
    def cell(value):
        return "未采集" if value is None else str(value)
    lines = ["# 性能与稳定性测试报告", "", "## 1. 测试范围与环境", "",
        f"时间：{meta['timestamp']}；Git：{meta['git_commit']}（dirty={meta['git_dirty']}）；系统：{meta['system']}。",
        f"服务：{meta['base_url']}；版本：{meta.get('service_version', '未获取')}；模型：{meta.get('model') or '未获取'}；Jev：{meta['jev_kind']}；数据集：{meta['dataset']}。",
        f"硬件/容器：CPU {meta.get('cpu_count')} 核，{meta.get('architecture')}；容器资源 {meta.get('container_resources')}。",
        f"并发档：{meta['users']}；预热 {meta['warmup']}s；采样 {meta['sample']}s；超时 {meta['timeout']}s；请求上限 {meta['max_requests']}；估算预算上限 ${meta['budget_usd']}。",
        "`/health` 只说明 Python Agent 进程可响应，不代表依赖健康。每个聊天请求均开启新会话。", "",
        "测试题与数据源：" + "；".join(f"{k}={v['case_id'] or '无'}→{v['expected_source'] or '进程'}" for k, v in meta['workloads'].items()), "",
        "## 2. 结果总表", "",
        "| 负载 | 数据源 | 目标用户数 | 实际启动峰值 | 实际在途峰值 | 有效样本数 | P50(ms) | P95(ms) | 吞吐(req/s) | HTTP错误率 | 业务失败率 | 备注 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for item in results:
        s = item.get("summary")
        notes = [note for note in (item.get('reason'), s.get('p95_note') if s else None, item.get('warning')) if note]
        lines.append(f"| {item['workload']} | {item['source']} | {item['users']} | {cell(item.get('spawned_users')) if s else '未测'} | {cell(s['peak_inflight']) if s else '未测'} | {cell(s['n']) if s else '未测'} | {cell(s['p50_ms']) if s else '未测'} | {cell(s['p95_ms']) if s else '未测'} | {cell(s['throughput_rps']) if s else '未测'} | {f'{s["http_error_rate"]:.1%}' if s and s['http_error_rate'] is not None else '未测'} | {f'{s["business_failure_rate"]:.1%}' if s and s['business_failure_rate'] is not None else '未测'} | {'；'.join(notes)} |")
    throughput_note = ("本次按配置的采样时长计算吞吐；部分档位提前触及请求上限，因此吞吐是保守估计。" if any((r.get('summary') or {}).get('throughput_note') for r in results) else
                       "吞吐按实际正式采样窗口计算；提前触及请求上限的档位以当时已持续的采样时间为分母。")
    lines += ["", throughput_note + " HTTP/网络、超时、业务失败、Jev/LLM 限流额度和安全降级在 JSON 中单列。", "", "## 3. 分段耗时", "",
        "各段可嵌套或重叠，不能相加；`route_duration_ms` 可能包含路由复核，Jev 单独计时。", "",
        "| 负载/用户 | 分段 | 样本 | P50(ms) | P95(ms) |", "|---|---|---:|---:|---:|"]
    labels = {"jev_duration_ms":"Jev", "route_duration_ms":"路由含复核", "llm_duration_ms":"LLM合计", "qdrant_duration_ms":"Qdrant检索", "rerank_duration_ms":"本地重排", "mysql_duration_ms":"MySQL", "hive_duration_ms":"Hive", "policy_tool_duration_ms":"政策工具", "duration_ms":"服务端总耗时"}
    for item in results:
        for key, label in labels.items():
            span = (item.get("summary") or {}).get("spans", {}).get(key)
            missing = "不适用" if (key == "hive_duration_ms" and item['source'] != 'hive') or (key == 'mysql_duration_ms' and item['source'] not in {'mysql'}) else "未采集"
            lines.append(f"| {item['workload']}/{item['users']} | {label} | {span['n'] if span else 0} | {cell(span['p50_ms']) if span and span['n'] else missing} | {cell(span['p95_ms']) if span and span['n'] else missing} |")
    lines += ["", "## 4. Jev 故障与恢复", ""]
    if meta.get('fault_stages'):
        lines += [f"独立本地 stub 演练：{meta.get('fault_report')}。stub 性能不可作为真实 Jev 性能。", "",
                  "| 阶段 | 起止时间 | 请求数 | 成功回答 | 安全降级 | HTTP/网络失败 | P95(ms) | 检测/恢复耗时(s) |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]
        for stage, value in meta['fault_stages'].items():
            counts = value.get('categories', {})
            times = meta.get('fault_phase_times', {}).get(stage, {})
            lines.append(f"| {stage} | {times.get('start','未记录')} → {times.get('end','未记录')} | {value['requests']} | {counts.get('success',0)} | {counts.get('safe_degradation',0)} | {counts.get('http_error',0)+counts.get('network_failure',0)+counts.get('timeout',0)} | {cell(value.get('p95_ms'))} | {cell(value.get('detection_or_recovery_seconds'))} |")
        lines += [""]
    else:
        lines += ["本次常规负载运行未执行故障演练；故障演练结果单独命名，不能当真实 Jev 性能。", ""]
    lines += ["## 5. 发现的问题", ""]
    failures = [r for r in results if r.get('reason')]
    findings = [f"- 现象：{r['workload']}/{r['users']} 未测或中断；复现条件：本次预检或运行；证据：{r['reason']}；影响：无该档性能结论；可能原因：待核实；严重度：待定；建议动作：排除原因后重跑。" for r in failures]
    for r in results:
        s = r.get('summary') or {}
        bad = s.get('classes', {}).get('business_failure', 0)
        if bad:
            traces = ', '.join(r.get('failure_traces', [])[:3]) or '无 trace_id'
            findings.append(f"- 现象：{r['workload']}/{r['users']} 业务校验失败 {bad}/{s['n']}；复现条件：当前审核题与并发档；证据：trace_id {traces}；影响：回答或证据不满足最小断言；可能原因：模型输出或检索波动（推测，未验证）；严重度：中；建议动作：按 trace_id 核对安全审计与响应，再用更大样本复测。")
    lines += findings or ["未发现已验证的问题；小样本不代表不存在问题。"]
    lines += ["", "## 6. 结论与限制", "", "结论仅限本机、当前数据和已执行并发档。外部 API 限流、网络抖动、合成数据和样本数可能影响解释。样本少于 100 的 P95 标记为‘样本不足、仅供观察’。此前 20 题串行回归 P95 是功能回归耗时，不能当本次压测结果。", ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "report.json").write_text(json.dumps({"metadata": meta, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--workloads", nargs="+", default=["health", "sql_mysql", "rag", "mixed"])
    parser.add_argument("--users", nargs="+", type=int, default=[1, 5, 10])
    parser.add_argument("--warmup", type=float, default=10)
    parser.add_argument("--sample", type=float, default=120)
    parser.add_argument("--spawn-rate", type=float, default=10)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-requests", type=int, default=10000, help="Global cap including preflight")
    parser.add_argument("--max-requests-per-cell", type=int, default=200, help="Per chat workload/user-count cell")
    parser.add_argument("--max-health-requests-per-cell", type=int, default=3000)
    parser.add_argument("--max-external-calls", type=int, default=13500, help="Conservative upper bound, 9 Jev/LLM calls per chat")
    parser.add_argument("--budget-usd", type=float, default=25)
    parser.add_argument("--estimated-usd-per-chat", type=float, default=0.02)
    parser.add_argument("--output-root", type=Path, default=ROOT / "performance-results")
    parser.add_argument("--jev-kind", choices=["real", "stub"], default="real")
    parser.add_argument("--fault-report", type=Path, help="Existing independent stub report.json to summarize in section 4")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if (any(name not in config['workloads'] for name in args.workloads) or any(n < 1 for n in args.users)
            or args.spawn_rate <= 0 or args.warmup < 0 or args.sample <= 0 or args.timeout <= 0
            or min(args.max_requests, args.max_requests_per_cell, args.max_health_requests_per_cell,
                   args.max_external_calls) < 1 or args.budget_usd <= 0 or args.estimated_usd_per_chat <= 0):
        parser.error("Invalid workload or users")
    output = args.output_root / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    meta = {"timestamp": datetime.now(timezone.utc).isoformat(), "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")), "system": platform.platform(),
        "base_url": args.base_url, "dataset": config['dataset'], "workloads": {n: config['workloads'][n] for n in args.workloads},
        "users": args.users, "warmup": args.warmup, "sample": args.sample, "timeout": args.timeout,
        "spawn_rate": args.spawn_rate, "seed": args.seed, "max_requests": args.max_requests,
        "max_requests_per_cell": args.max_requests_per_cell,
        "max_health_requests_per_cell": args.max_health_requests_per_cell,
        "budget_usd": args.budget_usd, "estimated_usd_per_chat": args.estimated_usd_per_chat,
        "max_external_calls": args.max_external_calls, "external_calls_upper_bound_per_chat": 9,
        "cpu_count": os.cpu_count(), "architecture": platform.machine(), "jev_kind": args.jev_kind,
        "service_version": "0.1.0", "container_resources": container_resources()}
    if args.fault_report:
        fault = json.loads(args.fault_report.read_text(encoding='utf-8'))
        if fault.get('kind') != 'jev_stub_fault':
            parser.error('fault report kind must be jev_stub_fault')
        meta['fault_report'] = str(args.fault_report)
        meta['fault_stages'] = fault['stages']
        meta['fault_phase_times'] = fault.get('phase_times', {})
    results = []
    remaining = args.max_requests
    external_remaining = args.max_external_calls
    chat_requests_used = 0
    try:
        with httpx.Client(base_url=args.base_url) as client:
            health = client.get("/health", timeout=5)
            if health.status_code != 200 or health.json() != {"status": "ok"}:
                raise RuntimeError("Python Agent /health failed")
            capabilities = client.get("/api/v1/capabilities", timeout=5).json()
            meta['model'] = capabilities.get('model')
            (output / 'parameters.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            for name in args.workloads:
                case = config['workloads'][name]
                budget_slots = max(0, math.floor((args.budget_usd + 1e-9) / args.estimated_usd_per_chat) - chat_requests_used)
                if remaining < 1 or (name != 'health' and (external_remaining < 9 or budget_slots < 1)):
                    ok, reason, body = False, "请求数或成本预算已达上限", None
                else:
                    ok, reason, body = preflight(client, name, case, capabilities, args.timeout)
                    remaining -= 1
                    if name != 'health':
                        external_remaining -= 9
                        chat_requests_used += 1
                (output / f'preflight-{name}.json').write_text(json.dumps({"ok": ok, "reason": reason, "trace_id": (body or {}).get('trace_id'), "source": ((body or {}).get('details') or {}).get('data_source')}, ensure_ascii=False, indent=2), encoding='utf-8')
                for users in args.users:
                    item = {"workload": name, "source": case['expected_source'] or 'process', "users": users}
                    if not ok or remaining < 1:
                        item['reason'] = reason if not ok else '请求上限已达，未测'
                    else:
                        allowed = min(remaining, args.max_health_requests_per_cell if name == 'health'
                                      else args.max_requests_per_cell)
                        if name != 'health':
                            budget_slots = max(0, math.floor((args.budget_usd + 1e-9) / args.estimated_usd_per_chat) - chat_requests_used)
                            allowed = min(allowed, budget_slots, external_remaining // 9)
                        if allowed < users:
                            item['reason'] = '剩余请求或成本额度不足以启动目标用户数，未测'
                        else:
                            prefix = output / f'{name}-{users}u'
                            env = {**os.environ, 'PERF_CONFIG': str(CONFIG), 'PERF_WORKLOAD': name,
                                'PERF_WARMUP': str(args.warmup), 'PERF_MAX_REQUESTS': str(allowed),
                                'PERF_SAMPLE': str(args.sample),
                                'PERF_TIMEOUT': str(args.timeout), 'PERF_RECORDS': str(prefix) + '.jsonl',
                                'PERF_SEED': str(args.seed),
                                'PYTHONPATH': str(HERE)}
                            cmd = [sys.executable, '-m', 'locust', '-f', str(HERE / 'locustfile.py'), '--headless',
                                '-H', args.base_url, '-u', str(users), '-r', str(args.spawn_rate),
                                '--run-time', f'{math.ceil(args.warmup + args.sample + users / args.spawn_rate + args.timeout + 10)}s',
                                '--csv', str(prefix), '--csv-full-history', '--stop-timeout', str(int(args.timeout + 2))]
                            run = subprocess.run(cmd, env=env, cwd=HERE, capture_output=True, text=True)
                            (Path(str(prefix) + '.log')).write_text(run.stdout[-3000:] + run.stderr[-3000:], encoding='utf-8')
                            rows = read_records(Path(str(prefix) + '.jsonl'))
                            remaining -= len(rows)
                            if name != 'health':
                                external_remaining -= 9 * len(rows)
                                chat_requests_used += len(rows)
                            if rows:
                                timing_file = Path(str(prefix) + '.jsonl.meta.json')
                                timing = json.loads(timing_file.read_text(encoding='utf-8')) if timing_file.exists() else {}
                                sample_elapsed = timing.get('sample_elapsed_s', 0)
                                item['spawned_users'] = max_spawned_users(Path(str(prefix) + '_stats_history.csv'))
                                item['summary'] = summarize(rows, max(sample_elapsed, 0.001))
                                item['summary']['sample_elapsed_s'] = round(sample_elapsed, 3)
                                warnings = []
                                if item['spawned_users'] < users or not timing.get('all_users_spawned'):
                                    warnings.append('目标用户数未全部启动')
                                if sample_elapsed < args.sample * .95:
                                    warnings.append(f'采样提前结束（{sample_elapsed:.1f}/{args.sample:g}s）')
                                if warnings:
                                    item['warning'] = '；'.join(warnings)
                                item['failure_traces'] = [r['trace_id'] for r in rows if r.get('phase') == 'sample' and r.get('category') == 'business_failure' and r.get('trace_id')]
                            else:
                                item['reason'] = f'Locust 无请求记录，退出码 {run.returncode}'
                    results.append(item)
                    report(meta, results, output)
    except Exception as exc:
        meta['preflight_error'] = f'{type(exc).__name__}: {exc}'
        report(meta, results, output)
        print(f'Preflight stopped: {meta["preflight_error"]}; report={output / "report.md"}', file=sys.stderr)
        return 2
    report(meta, results, output)
    print(output / 'report.md')
    return 0 if all('summary' in r for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
