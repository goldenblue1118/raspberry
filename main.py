"""
CrackBot 主程序 - Web 控制台

功能整合:
  - 遥控小车(前后左右)
  - 自动走停扫描
  - 实时日志推送
  - 失败队列重传
  - 摄像头实时预览(可选)

启动:
    sudo ~/crackbot-env/bin/python main.py
浏览器访问:
    http://crackbot.local:5000
"""

import os
import threading
import time
from datetime import datetime

import cv2
from flask import Flask, jsonify, render_template_string, request, Response

from camera import Camera, preprocess, draw_score
from motor import Motor
from uploader import Uploader
from gimbal import Gimbal


# ============= 配置区 =============
BACKEND_URL = "http://192.168.43.80:5000"  # ← 改成实际后端地址
DEFAULT_SPEED = 10
DEFAULT_SEGMENTS = 3
DEFAULT_MOVE_TIME = 1.5
DEFAULT_BLUR_THRESHOLD = 100.0
SCAN_BASE_DIR = "scans"
# ===================================


app = Flask(__name__)

gimbal = Gimbal()
car = Motor()
cam = Camera(flip_code = -1)
uploader = Uploader(BACKEND_URL)


# 全局状态
state = {
    "scan_running": False,
    "scan_progress": 0,
    "scan_total": 0,
    "scan_session": None,
    "log": [],
    "last_image": None,
    "queue_size": 0,
}
state_lock = threading.Lock()


def log(msg, level="INFO"):
    """记录日志,同时打印到控制台和写入 state"""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    with state_lock:
        state["log"].append(line)
        if len(state["log"]) > 200:
            state["log"] = state["log"][-200:]


# ============= HTML 模板 =============
HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CrackBot 控制台</title>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    margin: 0; padding: 16px; background: #f5f5f7; color: #222;
  }
  h1 { margin: 0 0 16px; font-size: 22px; }
  h3 { margin: 16px 0 8px; font-size: 16px; color: #555; }
  .card {
    background: white; border-radius: 12px; padding: 16px;
    margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  }
  .container {
    max-width: 720px; margin: 0 auto;
  }
  .pad-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 8px; max-width: 320px; margin: 0 auto;
  }
  .pad-grid button {
    padding: 18px 0; font-size: 20px; border: none;
    border-radius: 8px; background: #0066cc; color: white;
    cursor: pointer; user-select: none;
  }
  .pad-grid button:active { background: #004999; }
  .pad-grid .empty { background: transparent; }
  .pad-grid .stop { background: #cc0000; }
  .pad-grid .stop:active { background: #990000; }

  .scan-controls {
    display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  }
  .scan-controls input { padding: 8px; font-size: 14px;
    border: 1px solid #ccc; border-radius: 6px; width: 80px; }
  .scan-controls button {
    padding: 12px 24px; font-size: 16px; border: none;
    border-radius: 8px; background: #34c759; color: white;
    cursor: pointer;
  }
  .scan-controls button:disabled { background: #999; cursor: not-allowed; }

  .status {
    padding: 8px 12px; background: #eef; border-radius: 6px;
    font-size: 14px; margin: 8px 0;
  }
  .status.active { background: #ffefdf; color: #b95c00; }

  #log {
    background: #1e1e1e; color: #d4d4d4; padding: 12px;
    height: 280px; overflow-y: scroll; font-family: monospace;
    font-size: 12px; border-radius: 6px; line-height: 1.5;
  }
  .log-INFO { color: #d4d4d4; }
  .log-WARN { color: #f0ad4e; }
  .log-ERROR { color: #d9534f; }
  .log-OK { color: #5cb85c; }

  .row { display: flex; gap: 16px; flex-wrap: wrap; }
  .row > * { flex: 1; min-width: 280px; }
</style>
</head>
<body>
<div class="container">
  <h1>🤖 CrackBot 前端控制台</h1>

  <div class="card">
    <h3>遥控驾驶</h3>
    <div class="pad-grid">
      <div class="empty"></div>
      <button onmousedown="cmd('forward')" onmouseup="cmd('stop')"
              ontouchstart="cmd('forward')" ontouchend="cmd('stop')">↑</button>
      <div class="empty"></div>
      <button onmousedown="cmd('left')" onmouseup="cmd('stop')"
              ontouchstart="cmd('left')" ontouchend="cmd('stop')">←</button>
      <button class="stop" onclick="cmd('stop')">■</button>
      <button onmousedown="cmd('right')" onmouseup="cmd('stop')"
              ontouchstart="cmd('right')" ontouchend="cmd('stop')">→</button>
      <div class="empty"></div>
      <button onmousedown="cmd('backward')" onmouseup="cmd('stop')"
              ontouchstart="cmd('backward')" ontouchend="cmd('stop')">↓</button>
      <div class="empty"></div>
    </div>
  </div>

  <div class="card">
    <h3>自动扫描</h3>
    <div class="scan-controls">
      段数: <input type="number" id="segs" value="3" min="1" max="50">
      速度: <input type="number" id="speed" value="10" min="10" max="100">
      角度: <input type="text" id="angles" value="135, 90, 60" style="width:100px">
      <button id="btn-scan" onclick="startScan()">开始扫描</button>
      <button id="btn-retry" onclick="retryQueue()" style="background:#ff9500;">
        重传失败队列</button>
    </div>
    <div id="status" class="status">等待中...</div>
  </div>

  <div class="card">
    <h3>实时日志</h3>
    <div id="log"></div>
  </div>
</div>

<script>
function cmd(action) {
  fetch('/cmd/' + action).catch(e => console.error(e));
}

function startScan() {
  const segs = document.getElementById('segs').value;
  const speed = document.getElementById('speed').value;
  const angles = document.getElementById('angles').value;
  fetch(`/scan?segments=${segs}&speed=${speed}&angles=${angles}`)
    .then(r => r.json())
    .then(d => console.log('scan started', d));
}

function retryQueue() {
  fetch('/retry_queue').then(r => r.json()).then(d => {
    alert(`重传完成: 成功 ${d.success}, 失败 ${d.failed}`);
  });
}

function updateStatus() {
  fetch('/status').then(r => r.json()).then(d => {
    const s = document.getElementById('status');
    if (d.scan_running) {
      s.className = 'status active';
      s.innerText = `扫描中 ${d.scan_progress}/${d.scan_total} ` +
                    `(session: ${d.scan_session})`;
      document.getElementById('btn-scan').disabled = true;
    } else {
      s.className = 'status';
      s.innerText = `空闲 | 失败队列: ${d.queue_size} 张`;
      document.getElementById('btn-scan').disabled = false;
    }

    const logEl = document.getElementById('log');
    const wasAtBottom = logEl.scrollTop + logEl.clientHeight >=
                        logEl.scrollHeight - 5;
    logEl.innerHTML = d.log.map(line => {
      let cls = 'log-INFO';
      if (line.includes('[ERROR]')) cls = 'log-ERROR';
      else if (line.includes('[WARN]')) cls = 'log-WARN';
      else if (line.includes('[OK]')) cls = 'log-OK';
      return `<div class="${cls}">${escapeHtml(line)}</div>`;
    }).join('');
    if (wasAtBottom) logEl.scrollTop = logEl.scrollHeight;
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"
  })[c]);
}

setInterval(updateStatus, 1000);
updateStatus();
</script>
</body>
</html>
"""


# ============= Flask 路由 =============

@app.route('/')
def index():
    return render_template_string(HTML)


@app.route('/cmd/<action>')
def do_cmd(action):
    """遥控指令"""
    speed = DEFAULT_SPEED
    actions = {
        'forward': lambda: car.forward(speed),
        'backward': lambda: car.backward(speed),
        'left': lambda: car.turn_left(speed),
        'right': lambda: car.turn_right(speed),
        'stop': lambda: car.stop(),
    }
    if action not in actions:
        return jsonify({"error": "unknown action"}), 400
    actions[action]()
    return jsonify({"status": "ok", "action": action})


@app.route('/scan')
def start_scan():
    """启动自动扫描"""
    with state_lock:
        if state["scan_running"]:
            return jsonify({"error": "scan in progress"}), 409

    segments = int(request.args.get('segments', DEFAULT_SEGMENTS))
    speed = int(request.args.get('speed', 10))
    move_time = float(request.args.get('move_time', DEFAULT_MOVE_TIME))
    angles_raw = request.args.get('angles', '135, 90, 60')
    angles = [int(a) for a in angles_raw.split(',')]

    threading.Thread(
        target=scan_worker,
        args=(segments, speed, move_time, angles),
        daemon=True
    ).start()

    return jsonify({
        "status": "started",
        "segments": segments,
        "speed": speed,
    })


@app.route('/status')
def get_status():
    with state_lock:
        state["queue_size"] = uploader.queue_size()
        return jsonify(dict(state))


@app.route('/retry_queue')
def retry_queue():
    log("开始重传失败队列")
    success, failed = uploader.retry_queue()
    log(f"重传完成: 成功 {success}, 失败 {failed}",
        "OK" if failed == 0 else "WARN")
    return jsonify({"success": success, "failed": failed})


@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "service": "crackbot-frontend"})


# ============= 扫描后台线程 =============

def scan_worker(segments, speed, move_time, angles=[135, 90, 60]):
    session = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = os.path.join(SCAN_BASE_DIR, session)
    os.makedirs(session_dir, exist_ok=True)

    with state_lock:
        state["scan_running"] = True
        state["scan_progress"] = 0
        state["scan_total"] = segments
        state["scan_session"] = session

    log(f"扫描开始: session={session}, 段数={segments}, "
        f"速度={speed}, 时间={move_time}s")

    try:
        for i in range(segments):
            with state_lock:
                state["scan_progress"] = i + 1

            # 行进
            log(f"段 {i+1}/{segments}: 行进 {move_time}s")
            car.forward(speed)
            time.sleep(move_time)
            car.stop()
            time.sleep(0.5)  # 静置

            # 多角度拍照
            log(f"段 {i+1}/{segments}: 多角度拍照 (角度: {angles})")
            
            for angle in gimbal.sweep(angles):
                log(f"段 {i+1}: 仰角 {angle}°")
                img, score, ok = cam.capture_with_quality_check(
                    threshold=DEFAULT_BLUR_THRESHOLD)
                
                level = "OK" if ok else "WARN"
                log(f"  清晰度={score:.1f} 合格={ok}", level)
                
                # 保存
                raw_path = os.path.join(session_dir, f"seg{i:03d}_angle{angle:03d}_raw.jpg")
                proc_path = os.path.join(session_dir, f"seg{i:03d}_angle{angle:03d}_proc.jpg")
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                cv2.imwrite(raw_path, img_rgb, [cv2.IMWRITE_JPEG_QUALITY, 90])
                cv2.imwrite(proc_path, preprocess(img),
                            [cv2.IMWRITE_JPEG_QUALITY, 90])

                # 上传
                ok_up, resp = uploader.upload_image(
                    raw_path,
                    metadata={
                        "session": session,
                        "segment": i,
                        "angle": angle,
                        "blur_score": round(score, 2),
                    }
                )
                if ok_up:
                    log(f"  上传成功", "OK")
                else:
                    log(f"  上传失败 {resp.get('error', '')}", "ERROR")
            
            # 云台归位
            gimbal.home()

        log(f"扫描完成,会话: {session}", "OK")

    except Exception as e:
        log(f"扫描异常: {e}", "ERROR")
        car.stop()
    finally:
        with state_lock:
            state["scan_running"] = False


# ============= 启动 =============

def cleanup():
    print("\n清理资源...")
    try:
        car.cleanup()
    except Exception:
        pass
    try:
        cam.close()
    except Exception:
        pass
    try:
        gimbal.cleanup()
    except Exception:
        pass


if __name__ == '__main__':
    log(f"CrackBot 前端启动,后端地址: {BACKEND_URL}")
    log(f"队列中有 {uploader.queue_size()} 张待重传")

    try:
        app.run(host='0.0.0.0', port=5000,
                threaded=True, debug=False)
    except KeyboardInterrupt:
        print("\n[中断] 用户停止")
    finally:
        cleanup()
