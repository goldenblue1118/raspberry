"""
电机控制模块
基于 TB6612FNG 双路电机驱动,控制四轮小车(同侧两轮并联为一路)

引脚分配(BCM 编号):
    STBY:           GPIO 17  (使能)
    左电机 IN1/IN2: GPIO 27 / GPIO 22
    左电机 PWM:     GPIO 18  (硬件 PWM)
    右电机 IN1/IN2: GPIO 23 / GPIO 24
    右电机 PWM:     GPIO 13  (硬件 PWM)
"""

import RPi.GPIO as GPIO
import time


class Motor:
    """TB6612 电机控制类"""

    # 引脚定义(BCM)
    PIN_STBY = 17
    PIN_AIN1 = 27   # 左电机
    PIN_AIN2 = 22
    PIN_PWMA = 18
    PIN_BIN1 = 23   # 右电机
    PIN_BIN2 = 24
    PIN_PWMB = 13

    PWM_FREQ = 1000  # PWM 频率 1kHz
     
    #bias = 1.1

    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # 初始化所有控制引脚为输出
        for pin in [self.PIN_STBY, self.PIN_AIN1, self.PIN_AIN2,
                    self.PIN_BIN1, self.PIN_BIN2,
                    self.PIN_PWMA, self.PIN_PWMB]:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

        # PWM 对象
        self.pwm_a = GPIO.PWM(self.PIN_PWMA, self.PWM_FREQ)
        self.pwm_b = GPIO.PWM(self.PIN_PWMB, self.PWM_FREQ)
        self.pwm_a.start(0)
        self.pwm_b.start(0)

        # 使能驱动
        GPIO.output(self.PIN_STBY, GPIO.HIGH)

        self._current_speed = 0

    # ------- 私有方法 -------

    def _set_left(self, direction, speed):
        """direction: 1=正转, -1=反转, 0=停"""
        if direction > 0:
            GPIO.output(self.PIN_AIN1, GPIO.HIGH)
            GPIO.output(self.PIN_AIN2, GPIO.LOW)
        elif direction < 0:
            GPIO.output(self.PIN_AIN1, GPIO.LOW)
            GPIO.output(self.PIN_AIN2, GPIO.HIGH)
        else:
            GPIO.output(self.PIN_AIN1, GPIO.LOW)
            GPIO.output(self.PIN_AIN2, GPIO.LOW)
        self.pwm_a.ChangeDutyCycle(max(0, min(100, speed)))

    def _set_right(self, direction, speed):
        if direction > 0:
            GPIO.output(self.PIN_BIN1, GPIO.HIGH)
            GPIO.output(self.PIN_BIN2, GPIO.LOW)
        elif direction < 0:
            GPIO.output(self.PIN_BIN1, GPIO.LOW)
            GPIO.output(self.PIN_BIN2, GPIO.HIGH)
        else:
            GPIO.output(self.PIN_BIN1, GPIO.LOW)
            GPIO.output(self.PIN_BIN2, GPIO.LOW)
        self.pwm_b.ChangeDutyCycle(max(0, min(100, speed)))

    # ------- 公开运动方法 -------

    def forward(self, speed=60):
        """前进, speed 范围 0-100"""
        self._set_right(1, speed * 1.052)
        self._set_left(1, speed * 0.97)
        
        
        
        self._current_speed = speed

    def backward(self, speed=50):
        self._set_left(-1, speed)
        self._set_right(-1, speed)
        self._current_speed = -speed

    def turn_left(self, speed=50):
        """原地左转(左轮反转,右轮正转)"""
        self._set_left(-1, speed)
        self._set_right(1, speed)

    def turn_right(self, speed=50):
        self._set_left(1, speed)
        self._set_right(-1, speed)

    def stop(self):
        self._set_left(0, 0)
        self._set_right(0, 0)
        self._current_speed = 0

    def move_for(self, action, speed=50, seconds=1.0):
        """执行动作 N 秒后自动停止
        action: 'forward' / 'backward' / 'left' / 'right'
        """
        actions = {
            'forward': self.forward,
            'backward': self.backward,
            'left': self.turn_left,
            'right': self.turn_right,
        }
        if action not in actions:
            raise ValueError(f"未知动作: {action}")
        actions[action](speed)
        time.sleep(seconds)
        self.stop()

    def cleanup(self):
        """释放 GPIO 资源,程序退出前必调"""
        try:
            self.stop()
            self.pwm_a.stop()
            self.pwm_b.stop()
            GPIO.output(self.PIN_STBY, GPIO.LOW)
        except Exception:
            pass
        GPIO.cleanup()


# ------- 自测主程序 -------
if __name__ == "__main__":
    print("=== 电机自测程序 ===")
    print("请把小车架空,避免乱跑撞人!")
    input("准备好按回车继续...")

    car = Motor()
    try:
        print("[1/5] 前进 2 秒")
        car.move_for('forward', speed=60, seconds=2)
        time.sleep(0.5)

        print("[2/5] 后退 2 秒")
        car.move_for('backward', speed=60, seconds=2)
        time.sleep(0.5)

        print("[3/5] 左转 1 秒")
        car.move_for('left', speed=60, seconds=1)
        time.sleep(0.5)

        print("[4/5] 右转 1 秒")
        car.move_for('right', speed=60, seconds=1)
        time.sleep(0.5)

        print("[5/5] 停止")
        car.stop()
        print("自测完成 ✓")

    finally:
        car.cleanup()
