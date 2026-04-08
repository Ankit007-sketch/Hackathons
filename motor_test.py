import serial
import time

arduino = serial.Serial('COM5', 9600)
time.sleep(2)

arduino.write(b'MOVE\n')
print("Motor moving")

time.sleep(5)

arduino.write(b'STOP\n')
print("Motor stopped")