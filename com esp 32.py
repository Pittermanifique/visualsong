import serial
import time
import random

ser = serial.Serial(port="COM7", baudrate=115200)

while True:
    if ser.isOpen():
        choice = f"{random.choice([0, 1])}\n"
        print(choice.strip())
        ser.write(choice.encode("utf-8"))
        time.sleep(2)  # ou moins