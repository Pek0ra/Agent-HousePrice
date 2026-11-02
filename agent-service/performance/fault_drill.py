"""Five-user Jev fault timeline against a locally isolated stub endpoint."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from stats import classify, percentile, split_fault_phases
from run import git, container_resources

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--stage-seconds", type=float, default=8)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--jev-timeout", type=float, default=2)
    parser.add_argument("--max-requests", type=int, default=24)
    parser.add_argument("--output-root", type=Path, default=ROOT / "performance-results")
    args = parser.parse_args()
    config = json.loads((HERE / 'workloads.json').read_text(encoding='utf-8'))['workloads']['sql_mysql']
    output = args.output_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-jev-stub-fault')
    output.mkdir(parents=True, exist_ok=False)
    metadata = {'timestamp': datetime.now(timezone.utc).isoformat(), 'git_commit': git('rev-parse','HEAD'),
                'git_dirty': bool(git('status','--porcelain')), 'container_resources': container_resources(),
                'users': 5, 'request_timeout_seconds': args.timeout, 'jev_timeout_seconds': args.jev_timeout,
                'max_requests': args.max_requests, 'jev_kind': 'stub', 'case_id': config['case_id']}
    stub = None
    records = []
    issued = 0
    stage_issued = {}
    stage_budget = max(5, (args.max_requests - 1) // 4)
    lock = threading.Lock()
    original_env = dict(os.environ)
    phase_times = {}
    error = None
    try:
        stub = subprocess.Popen([sys.executable, str(HERE / 'jev_stub.py'), '--port', str(args.port),
                                 '--delay', str(args.jev_timeout + 3)], cwd=HERE,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            try:
                httpx.post(f'http://127.0.0.1:{args.port}/control', json={'mode': 'normal'}, timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(.2)
        else:
            raise RuntimeError('local Jev stub did not start')
        env = {**original_env, 'JEV_ENDPOINT': f'http://host.docker.internal:{args.port}/v1/systemone',
               'JEV_TIMEOUT_SECONDS': str(args.jev_timeout), 'TYPESAFE_API_KEY': 'local-stub-only'}
        subprocess.run(['docker', 'compose', 'up', '-d', '--no-deps', '--force-recreate', 'python-agent'],
                       cwd=ROOT, env=env, check=True, capture_output=True)
        with httpx.Client(base_url=args.base_url) as client:
            for _ in range(60):
                try:
                    if client.get('/health', timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError('Agent did not recover after stub configuration')
            response = client.post('/api/v1/chat', json={'message': config['question']}, timeout=args.timeout)
            if classify(response.status_code, response.json(), None, config) != 'success':
                raise RuntimeError('stub baseline did not follow verified MySQL route')
        issued += 1

        def worker(phase: str, deadline: float):
            nonlocal issued
            with httpx.Client(base_url=args.base_url) as client:
                while time.monotonic() < deadline:
                    with lock:
                        if issued >= args.max_requests:
                            return
                        if stage_issued.get(phase, 0) >= stage_budget:
                            return
                        issued += 1
                        stage_issued[phase] = stage_issued.get(phase, 0) + 1
                    at = time.time()
                    started = time.perf_counter()
                    status, body, category = None, None, None
                    try:
                        response = client.post('/api/v1/chat', json={'message': config['question']}, timeout=args.timeout)
                        status = response.status_code
                        body = response.json()
                        category = classify(status, body, None, config)
                        if category == 'safe_degradation' and '意图识别服务暂不可用' not in str(body.get('answer', '')):
                            category = 'business_failure'
                    except httpx.TimeoutException:
                        category = 'timeout'
                    except (httpx.HTTPError, ValueError):
                        category = 'network_failure'
                    details = (body or {}).get('details') or {}
                    with lock:
                        records.append({'phase': phase, 'at': at, 'completed_at': time.time(),
                            'duration_ms': round((time.perf_counter()-started)*1000, 3),
                            'status': status, 'category': category, 'trace_id': (body or {}).get('trace_id'),
                            'source': details.get('data_source'), 'successful_queries': details.get('successful_queries'),
                            'error_category': details.get('error_category')})

        for phase, mode in [('baseline','normal'), ('timeout','timeout'), ('disconnect','disconnect'), ('recovery','normal')]:
            httpx.post(f'http://127.0.0.1:{args.port}/control', json={'mode': mode}, timeout=2).raise_for_status()
            phase_times[phase] = {'start': datetime.now(timezone.utc).isoformat(), 'start_epoch': time.time()}
            deadline = time.monotonic() + args.stage_seconds
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                futures = [pool.submit(worker, phase, deadline) for _ in range(5)]
                for future in futures:
                    future.result()
            phase_times[phase]['end'] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    finally:
        try:
            subprocess.run(['docker', 'compose', 'up', '-d', '--no-deps', '--force-recreate', 'python-agent'],
                           cwd=ROOT, env=original_env, check=True, capture_output=True)
        except Exception as exc:
            error = (error or '') + f'; restore failed: {type(exc).__name__}'
        if stub:
            stub.terminate()
            try:
                stub.wait(timeout=3)
            except subprocess.TimeoutExpired:
                stub.kill()
        try:
            with httpx.Client(base_url=args.base_url) as client:
                for _ in range(60):
                    try:
                        if client.get('/health', timeout=2).json() == {'status':'ok'}:
                            break
                    except (httpx.HTTPError, ValueError):
                        pass
                    time.sleep(1)
                else:
                    error = (error or '') + '; final health failed'
        except Exception:
            error = (error or '') + '; final health failed'
        try:
            inspected = subprocess.run(['docker','inspect','agent-house-price-python-agent'],
                                       cwd=ROOT, check=True, capture_output=True, text=True)
            active_env = json.loads(inspected.stdout)[0]['Config']['Env']
            if any(item == f'JEV_ENDPOINT=http://host.docker.internal:{args.port}/v1/systemone' for item in active_env):
                error = (error or '') + '; Jev endpoint restore failed'
        except Exception:
            error = (error or '') + '; Jev endpoint verification failed'
    with (output / 'records.jsonl').open('x', encoding='utf-8') as stream:
        for row in records:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    phases = split_fault_phases(records)
    lines = ['# 性能与稳定性测试报告', '', '## 1. 测试范围与环境', '',
             f"时间：{metadata['timestamp']}；Git：{metadata['git_commit']}（dirty={metadata['git_dirty']}）；容器：{metadata['container_resources']}；本地 Jev stub，5 虚拟用户；四阶段各 {args.stage_seconds}s；Agent 请求超时 {args.timeout}s；请求上限 {args.max_requests}；题目 BLD13 / MySQL。",
             'stub 只提供 Jev Choice/Noul 路由，LLM 与 MySQL 仍使用真实依赖；stub 性能不可作为真实 Jev 性能。', '',
             '## 2. 结果总表', '', '本次是持续故障演练，阶段结果见第 4 节；不与真实 Jev 压测混合统计。', '',
             '## 3. 分段耗时', '', '阶段 P50/P95 见 report.json；本次未采集独立分段耗时，记为“未采集”。', '',
             '## 4. Jev 故障与恢复（本地 stub，5 用户）', '',
             '| 阶段 | 起止时间 | 请求数 | 成功回答 | 安全降级 | HTTP/网络失败 | P95(ms) | 检测/恢复耗时 |',
             '|---|---|---:|---:|---:|---:|---:|---|']
    result = {}
    for phase in ('baseline','timeout','disconnect','recovery'):
        rows = phases.get(phase, [])
        times = phase_times.get(phase, {})
        first = next((r for r in sorted(rows, key=lambda x:x['completed_at']) if r['category'] == ('success' if phase == 'recovery' else 'safe_degradation')), None)
        detect = round(first['completed_at'] - times['start_epoch'], 3) if first and 'start_epoch' in times else None
        result[phase] = {'requests':len(rows), 'p50_ms':percentile([r['duration_ms'] for r in rows],50),
                         'p95_ms':percentile([r['duration_ms'] for r in rows],95),
                         'detection_or_recovery_seconds':detect,
                         'timeout_rate':sum(r['error_category']=='jev_timeout' or r['category']=='timeout' for r in rows)/len(rows) if rows else None,
                         'safe_degradation_rate':sum(r['category']=='safe_degradation' for r in rows)/len(rows) if rows else None,
                         'categories':{c:sum(r['category']==c for r in rows) for c in set(r['category'] for r in rows)}}
        lines.append(f"| {phase} | {times.get('start','未运行')} → {times.get('end','未运行')} | {len(rows)} | {sum(r['category']=='success' for r in rows)} | {sum(r['category']=='safe_degradation' for r in rows)} | {sum(r['category'] in {'http_error','network_failure','timeout'} for r in rows)} | {result[phase]['p95_ms'] or '未测'} | {detect if detect is not None else '未测'} |")
    unsafe = [r for r in records if r['phase'] in {'timeout','disconnect'} and (r['source'] not in {None,'none'} or (r['successful_queries'] or 0) > 0)]
    recovery = sorted(phases.get('recovery', []), key=lambda row: row['completed_at'])
    consecutive = 0
    for row in recovery:
        if row['category'] != 'success':
            break
        consecutive += 1
    lines += ['', f"故障期错误选源或查询：{len(unsafe)}；恢复后连续成功：{consecutive}；恢复后残留失败：{sum(r['category']!='success' for r in phases.get('recovery',[]))}。",
              "各阶段超时率、P50、安全降级率见同目录 report.json；未观测到未授权查询不等于可证明所有越权风险不存在。",
              f"trace_id 样例：{', '.join(r['trace_id'] for r in records if r.get('trace_id'))[:500] or '无'}。",
              f"运行错误：{error or '无'}。", '', '## 5. 发现的问题', '',
              f"现象：故障期错误选源/查询 {len(unsafe)} 次、恢复残留失败 {sum(r['category']!='success' for r in recovery)} 次；复现条件：本地 stub 四阶段；证据：records.jsonl 与上述 trace_id；影响：仅限该演练；可能原因：若有失败需逐条调查；严重度：按实际失败评定；建议动作：复核失败 trace。", '',
              '## 6. 结论与限制', '',
              '仅证明本次本机 stub 故障窗口的可观察安全降级和恢复行为。超时、断连和网络调度均为合成环境；所有阶段样本不足，P95 仅供观察。此前 20 题串行回归 P95 不属于本次压测。', '']
    (output/'report.md').write_text('\n'.join(lines), encoding='utf-8')
    (output/'report.json').write_text(json.dumps({'kind':'jev_stub_fault', 'metadata':metadata,
        'phase_times': phase_times, 'stages':result,
        'unsafe_source_or_query':len(unsafe), 'recovery_consecutive_success':consecutive,
        'error':error, 'final_health_checked':not error}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output/'report.md')
    return 1 if error or unsafe else 0


if __name__ == '__main__':
    raise SystemExit(main())
