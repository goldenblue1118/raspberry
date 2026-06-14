"""
后端上传模块

功能:
  - 上传单张图片到后端 HTTP 接口(multipart/form-data)
  - 失败重试
  - 失败队列(网络恢复后重传)
"""

import json
import os
import time
from datetime import datetime

import requests


class Uploader:
    """后端上传客户端"""

    def __init__(self, server_url, queue_dir="upload_queue", timeout=10):
        """
        参数:
            server_url: 后端地址,如 'http://192.168.1.100:8080'
            queue_dir: 失败队列目录,网络恢复后可重传
            timeout: 单次请求超时秒数
        """
        self.url = server_url.rstrip('/')
        self.queue_dir = queue_dir
        self.timeout = timeout
        os.makedirs(queue_dir, exist_ok=True)

    # ------- 单次上传 -------

    def upload_image(self, image_path, metadata=None, max_retry=3):
        """上传单张图片,带失败重试

        参数:
            image_path: 本地图片路径
            metadata: 附加元信息(dict),如 session/segment/blur_score
            max_retry: 失败重试次数

        返回: (success, response_json or None)
        """
        if not os.path.exists(image_path):
            return False, {"error": "file not found"}

        metadata = metadata or {}
        last_err = None

        for attempt in range(max_retry):
            try:
                with open(image_path, 'rb') as f:
                    files = {
                        'image': (os.path.basename(image_path),
                                  f, 'image/jpeg')
                    }
                    data = {k: str(v) for k, v in metadata.items()}
                    r = requests.post(
                        f"{self.url}/api/upload",
                        files=files, data=data,
                        timeout=self.timeout
                    )
                    if r.status_code == 200:
                        try:
                            return True, r.json()
                        except ValueError:
                            return True, {"raw": r.text}
                    else:
                        last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            except requests.exceptions.RequestException as e:
                last_err = str(e)

            # 退避重试
            if attempt < max_retry - 1:
                time.sleep(0.5 * (attempt + 1))

        # 全部失败,加入队列
        self._enqueue(image_path, metadata, last_err)
        return False, {"error": last_err}

    # ------- 队列管理 -------

    def _enqueue(self, image_path, metadata, error):
        """把失败任务存入本地队列"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        record = {
            "image_path": os.path.abspath(image_path),
            "metadata": metadata,
            "error": error,
            "queued_at": ts,
        }
        record_path = os.path.join(self.queue_dir, f"{ts}.json")
        with open(record_path, 'w') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    def retry_queue(self, max_items=None):
        """重传失败队列中的所有任务

        返回: (成功数, 失败数)
        """
        files = sorted(os.listdir(self.queue_dir))
        if max_items:
            files = files[:max_items]

        success = failed = 0
        for fname in files:
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(self.queue_dir, fname)
            try:
                with open(fpath) as f:
                    record = json.load(f)
                ok, _ = self.upload_image(
                    record['image_path'],
                    record.get('metadata'),
                    max_retry=2
                )
                if ok:
                    os.remove(fpath)  # 上传成功,从队列移除
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"重传 {fname} 失败: {e}")
                failed += 1

        return success, failed

    def queue_size(self):
        """返回当前队列长度"""
        return len([f for f in os.listdir(self.queue_dir)
                    if f.endswith('.json')])

    # ------- 健康检查 -------

    def ping(self):
        """检查后端是否可达"""
        try:
            r = requests.get(f"{self.url}/api/health", timeout=3)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False


# ------- 自测 -------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python uploader.py <服务器URL> [测试图片路径]")
        print("示例: python uploader.py http://192.168.1.100:8080 test.jpg")
        sys.exit(1)

    url = sys.argv[1]
    img = sys.argv[2] if len(sys.argv) > 2 else "test.jpg"

    up = Uploader(url)
    print(f"后端地址: {url}")
    print(f"健康检查: {'可达 ✓' if up.ping() else '不可达 ✗'}")

    if os.path.exists(img):
        print(f"上传 {img}...")
        ok, resp = up.upload_image(img, {
            "session": "test", "segment": 0, "blur_score": 150.5
        })
        print(f"结果: {'成功' if ok else '失败'} - {resp}")
    else:
        print(f"未找到 {img},跳过上传测试")

    print(f"队列长度: {up.queue_size()}")
