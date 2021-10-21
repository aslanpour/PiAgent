from bluetooth import *
import time
import socket

sock = None
connected=False
    
while True:
    sock = BluetoothSocket(RFCOMM)
    #sock.settimeout(10)
    try:
        print('try...')
        res = sock.connect(("00:15:A5:00:02:ED", 1))
    except btcommon.BluetoothError as e:
        print('error1: ' + str(e))
        connected = False
    except Exception as e:
        print('error2 ' + str(e))
        connected=False
    else:
        print("Connected OK")
        
        connected=True
        break
    time.sleep(1)

#read
def read_power_meter():
    global sock
    while True:
        output = []
        # Send request to USB meter
        d = b""
        while True:
            sock.send((0xF0).to_bytes(1, byteorder="big"))
            d += sock.recv(130)
            if len(d) != 130:
                continue
            else:
                break
    
        #read data
        data = {}
        data["Volts"] = struct.unpack(">h", d[2 : 3 + 1])[0] / 1000.0  # volts
        data["Amps"] = struct.unpack(">h", d[4 : 5 + 1])[0] / 10000.0  # amps
        data["Watts"] = struct.unpack(">I", d[6 : 9 + 1])[0] / 1000.0  # watts
        data["temp_C"] = struct.unpack(">h", d[10 : 11 + 1])[0]  # temp in C
        
        
        g = 0
        for i in range(16, 95, 8):
            ma, mw = struct.unpack(">II", d[i : i + 8])  # mAh,mWh respectively
            gs = str(g)
            
            data[gs + "_mAh"] = ma
            data[gs + "_mWh"] = mw
            g += 1
        
        temp = [data["0_mWh"], data["0_mAh"],
                data["Watts"], data["Amps"], data["Volts"], 
                data["temp_C"]]
        
        output=temp
        print('output= ' + str(output))
        time.sleep(1)

read_power_meter()