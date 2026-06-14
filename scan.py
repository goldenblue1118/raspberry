"""
走停式扫描主流程(命令行版)

逻辑:
  1. 小车前进 N 秒
  2. 停下,等震动消除
  3. 高分辨率拍照,做清晰度评估
  4. 本地图像预处理
  5. 上传到后端
  6. 重复,直到完成指定段数
"""

import argparse
import os
import time
from datetime import datetime

import cv2

from camera import Camera, preprocess
from motor import Motor
from uploader import Uploader
from gimbal import Gimbal


class Scanner:
    """走停扫描器"""

    def __init__(self, server_url=None, base_dir="scans"):
        self.car = Motor()
        self.cam = Camera(flip_code = -1)
        self.uploader = Uploader(server_url) if server_url else None
        self.gimbal = Gimbal()

        self.session = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(base_dir, self.session)
        os.makedirs(self.session_dir, exist_ok=True)

    def scan(self, segments=5, move_seconds=1.5, speed=40,
             settle_time=0.5, blur_threshold=100):
        """执行扫描

        参数:
            segments: 扫描段数
            move_seconds: 每段前进时间(秒)
            speed: 电机 PWM 速度 0-100
            settle_time: 停车后静置时间(等震动消除)
            blur_threshold: 清晰度合格阈值
        """
        results = []

        print(f"\n{'='*50}")
        print(f"开始扫描 session={self.session}")
        print(f"目标 {segments} 段,速度={speed},每段{move_seconds}s")
        print(f"{'='*50}\n")

        for i in range(segments):
            print(f"--- 第 {i+1}/{segments} 段 ---")

            # 1. 行进
            print(f"  [行进] {move_seconds}s @ speed={speed}")
            self.car.forward(speed)
            time.sleep(move_seconds)
            self.car.stop()

            # 2. 静置
            time.sleep(settle_time)

            # 3. 多角度拍照(带清晰度检查)
            ANGLES = [135,90,60]  # 每段拍摄的角度列表,可按需调整
            
            for angle in self.gimbal.sweep(ANGLES):
                print(f"  [拍照] 段 {i+1}: 仰角 {angle}°, 清晰度阈值={blur_threshold}")
                img, score, ok = self.cam.capture_with_quality_check(
                    threshold=blur_threshold)
                
                raw_path = os.path.join(
                    self.session_dir,
                    f"seg{i:03d}_angle{angle:03d}_raw.jpg")
                proc_path = os.path.join(
                    self.session_dir,
                    f"seg{i:03d}_angle{angle:03d}_proc.jpg")
                
                cv2.imwrite(raw_path, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                cv2.imwrite(proc_path, preprocess(img), [cv2.IMWRITE_JPEG_QUALITY, 90])
                print(f"  [评估] 清晰度={score:.1f} 合格={ok}")
                
                if self.uploader:
                    ok_up, _ = self.uploader.upload_image(proc_path, metadata={
                        "session": self.session,
                        "segment": i,
                        "angle": angle,
                        "blur_score": round(score, 2),
                    })
                    print(f"  [上传] {'成功' if ok_up else '失败'}")

            # 云台归位
            self.gimbal.home()

            results.append({
                "segment": i,
                "raw": raw_path,
                "processed": proc_path,
                "blur_score": round(score, 2),
                "quality_ok": ok,
                "upload_ok": upload_ok,
            })

        print(f"\n{'='*50}")
        print(f"扫描完成,共 {len(results)} 段")
        print(f"清晰度合格: "
              f"{sum(1 for r in results if r['quality_ok'])}/{len(results)}")
        if self.uploader:
            print(f"上传成功: "
                  f"{sum(1 for r in results if r['upload_ok'])}/{len(results)}")
        print(f"会话目录: {self.session_dir}")
        print(f"{'='*50}\n")

        return results

    def cleanup(self):
        self.gimbal.cleanup() 
        self.car.cleanup()
        self.cam.close()


def main():
    parser = argparse.ArgumentParser(description="CrackBot 走停扫描")
    parser.add_argument('-n', '--segments', type=int, default=5,
                        help='扫描段数(默认5)')
    parser.add_argument('-t', '--move-time', type=float, default=1.5,
                        help='每段前进时间秒(默认1.5)')
    parser.add_argument('-s', '--speed', type=int, default=40,
                        help='电机速度0-100(默认40)')
    parser.add_argument('--threshold', type=float, default=100,
                        help='清晰度阈值(默认100)')
    parser.add_argument('--server', type=str, default=None,
                        help='后端地址,如 http://192.168.1.100:8080')

    args = parser.parse_args()

    scanner = Scanner(server_url=args.server)
    try:
        scanner.scan(
            segments=args.segments,
            move_seconds=args.move_time,
            speed=args.speed,
            blur_threshold=args.threshold,
        )
    except KeyboardInterrupt:
        print("\n[中断] 用户取消")
    finally:
        scanner.cleanup()


if __name__ == "__main__":
    main()
