from flask import Flask, request, send_file, make_response, json #pip3 install flask
from waitress import serve #pip3 install waitress
import requests
import threading
import logging
import datetime
import time
#Pi Monitor
import psutil
import numpy as np
import re
import RPi.GPIO as GPIO
from pijuice import PiJuice  #sudo apt-get install pijuice-gui
from bluetooth import * #sudo apt-get install bluetooth bluez libbluetooth-dev && sudo python3 -m pip install pybluez
# sudo systemctl start bluetooth
# echo "power on" | bluetoothctl
import random
import socket
import atexit

app = Flask(__name__)
app.config["DEBUG"] = True

#config
node_name="worker_1"
node_role="LOAD_GENERATOR"   #MONITOR #LOAD_GENERATOR
node_IP="10.0.0.91"
gateway_IP="10.0.0.90"
peers=[]
test_name = socket.gethostname() + "_test" 
#local_value #local_ref #offload_value #offload_ref

report_path ="/home/pi/Desktop/logs/" + test_name + "/"
if not os.path.exists(report_path):
    os.makedirs(report_path)

bluetooth_addr1 = "00:15:A5:00:03:E7"
#master"00:15:A3:00:52:2B" #w1#"00:15:A5:00:02:ED" #w2#"00:15:A5:00:02:ED" #w3"00:15:A3:00:5A:6F"
pics_folder = "/home/pi/pics/"
pics_num = 170 #pics name "pic_#.jpg"
storage_folder = "/home/pi/storage/"
if not os.path.exists(storage_folder):
    os.makedirs(storage_folder)
#settings
#[0]app name
#[1] run/not
#[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
#[3] workload: [[0]iteration [1]interval/exponential lambda(10=avg 8s)
                #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
#[4] func_name [5] func_data [6] sent [7] recv
apps=[['yolo3', False, 'static', [3, 1, 1, 5], 'yolo3', 'reference', 0, 0],
      ['crop-monitor', True, 'static', [3, 1, 1, 5], 'crop-monitor', 'value', 0, 0],
      ['irrigation', False, 'static', [30, 1, 20, 5], 'irrigation', 'value', 0, 0],
      ['short', False, 'static', [3, 2, 1, 5], 'short', 'value', 0, 0]]

usb_meter_involved = True
#Either battery_operated or battery_cfg should be True, if the second, usb meter needs enabling
battery_operated=False
#Battery simulation
battery_cfg = [True, 850,850, [5,5], 10] #1:max,2:initial (and current) SoC, 3:renwable seed&lambda, 4:interval

time_based_termination= ['False', '7200'] # end time-must be longer than actual test duration
snapshot_report=['False', '200', '800'] #begin and end time
http_admission_timeout = 3
overlapped_allowed= True
raspbian_upgrade_error= False #True, if psutil io_disk error due to upgrade
#controllers
test_started = None
test_finished = None
under_test=False
lock = threading.Lock()
actuations = 0


sock = None #bluetooth connection
sensor_log ={}
#monitoring parameters
    #in owl_actuator
response_time = []
    #in pi_monitor
response_time_accumulative = []
current_time = []
current_time_ts = []
battery_usage = []
cpuUtil = []
cpu_temp = []
cpu_freq_curr=[]
cpu_freq_max=[]
cpu_freq_min=[]
cpu_ctx_swt = []
cpu_inter = []
cpu_soft_inter=[]
memory = []
disk_usage = []
disk_io_usage = []
bw_usage = []

power_usage = []
throughput=[]
throughput2=[]

if battery_operated:
    relay_pin = 20
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    pijuice = PiJuice(1, 0x14)


@app.route('/app', methods=['POST'])
def workload(my_app):
    time.sleep(1)  # Give enough time gap to send req to server to avoid connection error. or use sessions
    global logger
    global test_started
    global apps
    logger.info('workload: started')
#[2] w type: "static" or "poisson" or "exponential-poisson"
#[3] workload: [[0]iteration [1]interval/exponential lambda(10=avg 8s)
                #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
#[4] func_name [5] func_data [6] sent [7] recv
    
    workload_type = my_app[2] #"static" or "poisson" or "exponential-poisson"
    w_config = my_app[3]
    
    iteration = 0
    interval = 0
    concurrently = 0
    seed = ""
    if workload_type == 'static':
        iteration = w_config[0]
        #interval
        interval = w_config[1]
        #concurrently
        concurrently = w_config[2]
    elif workload_type == 'poisson':
        iteration = w_config[0]
        #interval
        interval = w_config[1]
        #concurrently
        #set seed
        seed = w_config[3]
        np.random.seed(seed)
        
        lmd_rate = w_config[2] 
        concurrently = np.random.poisson(lmd_rate, iteration)
    elif workload_type == 'exponential-poisson':
        iteration = w_config[0]
        #interval
        #set seed
        seed = w_config[3]
        np.random.seed(seed)
        
        lmd_scale = w_config[1]
        #random.exponential(scale=1.0, size=None)
        interval = np.random.exponential(lmd_scale, iteration)
        #concurrently
        lmd_rate = w_config[2] 
        concurrently = np.random.poisson(lmd_rate, iteration)
    elif workload_type == 'exponential': #dynamic interval, static concurrently
        iteration = w_config[0]
        #interval
        #set seed
        seed = w_config[3]
        np.random.seed(seed)
        
        lmd_scale = w_config[1]
        #random.exponential(scale=1.0, size=None)
        interval = np.random.exponential(lmd_scale, iteration)
        concurrently=w_config[2]
        
    func_name = my_app[4]
    func_data = my_app[5]
    #my_app[6] sensor send counter
    #my_app[7] actuation recv counter
    
    
    
    logger.info("workload: App  \n-- workload: {0} \nIteration: {1} \nInterval {2} Avg.({3}) \n Concurrently {4} Avg. ({5})\n"
                "Seed {6} \n -- function {7} data {8}".format(
        workload_type, iteration,
        interval, sum(interval)/len(interval) if "exponential" in workload_type else "--",
        concurrently, sum(concurrently)/len(concurrently) if "poisson" in workload_type else "--",
        seed, func_name, func_data))
    
    generator_st = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()    
    #sensor counter
    sent = 0
    #iterations
    for i in range(iteration):
        iter_started = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        
        #interarrival
        interarrival = (interval[i] if "exponential" in workload_type else interval)
        
        threads = []
        
        #concurrently
        con = (concurrently[i] if "poisson" in workload_type else concurrently)
        for c in range (con):
            sent +=1
            thread = threading.Thread(target= send_sensor, args=(sent,func_name, func_data, interarrival,))
            
            threads.append(thread)
        
        for t in threads:
            t.start()
            
        #check termination: do not sleep after the latest iteration
        if i == iteration-1:
            break
        #Get iteration duration
        now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        iter_elapsed=now-iter_started
        #check duration
        if iter_elapsed < interarrival:
            if iter_elapsed > (interarrival/2):
                logger.warning('Workload iteration #' + str(i) +  ' rather long! (' + str(iter_elapsed) + ')')
            #wait untill next iteration -deduct elapsed time
            time.sleep(interarrival - iter_elapsed)
            
        else:
            logger.error('Motion Iteration #' + str(i) + ' overlapped! (' + str(iter_elapsed) + ')')
            print('Motion Iteration #' + str(i) + ' overlapped!')
            time.sleep(3600)
            
        
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    logger.info('workload: Generator\'s ' + func_name +' finished in ' + str(round(now-test_started,2)) + ' sec')
    
    #set sent
    apps[apps.index(my_app)][6] = sent
    logger.info('workload: done')
    return 'workload: Generator done'


def send_sensor(counter, func_name, func_data,admission_deadline):
    global pics_num
    global pics_folder
    global sensor_log
    global gateway_IP
    global node_IP
    global overlapped_allowed
    
    #one-off sensor
    sample_started = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    try:
        #random image name, pic names must be like "pic_1.jpg"
        n = random.randint(1,pics_num) 
        file_name ='pic_' + str(n) + '.jpg'
        file={'image_file': open(pics_folder + file_name, 'rb')}
    
        #create sensor id
        sensor_id= str(sample_started) + '#' + func_name + '-#' + str(counter) 
        #[0] func_name [1]created, [2]submitted/admission-dur, [3]queue-dur, [4]exec-dur. [5] finished, [6]rt
        sensor_log[sensor_id]= [func_name, sample_started, -1, -1, -1, -1, -1]
        
        # value: Send async req to yolo function along with image_file
        if func_data == 'value':
            #no response is received, just call back is received
            ##
            url = 'http://' + gateway_IP + ':31112/async-function/' + func_name
            header = {'X-Callback-Url':'http://' + node_IP + ':5000/actuator',
                          'Sensor-ID': sensor_id}
            img = (file if func_name== 'yolo3' else None)
            
            json_list = {}
            if func_name=='crop-monitor':
                json_list={"user":sensor_id, "temperature":"10", "humidity":"5",
                  "moisture":"3", "luminosity":"1"} 
            elif func_name == 'irrigation':
                json_list={"user":sensor_id, "temperature":"10", "humidity":"5",
                  "soil_temperature":"3", "water_level":"1", "spatial_location":"1"}
            
            response=requests.post(url, headers=header, files=img, json=json_list)
            
        #Pioss: Send the image to Pioss. Then, it notifies the yolo function.
        elif func_data == 'reference':
            url = 'http://' + node_IP + ':5000/pioss/api/write/' + func_name + '/' + file_name
            img = (file if func_name== 'yolo3' else None)
            header ={'Sensor-ID': sensor_id}
            response=requests.post(url, headers=header, timeout=http_admission_timeout, files=img)
            #no response is received
            # finished when next operation (sending actual requst to function) is done.
        else: #Minio
            pass
        
                                         
        if response.status_code==202 or response.status_code==200:
            
            now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            sample_elapsed = now - sample_started
            logger.info('send_sensor: Sample #' + str(counter) + ' App:' + func_name + '- Success, admission (' + str(round(sample_elapsed,2)) + 's)')
            #Set admission time
            sensor_log[sensor_id][2]= sample_elapsed
            if (sample_elapsed) >= admission_deadline:
                logger.warning('send_sensor: Sample #' + str(counter) + ' ' + func_name + ' admission overlapped (' + str(sample_elapsed) + 's)')
                if not overlapped_allowed:
                    logger.error('send_sensor: Sample #' + str(counter) + ' admission overlapped (' + str(sample_elapsed) + 's)')
                    print('Sleep....')
                    time.sleep(3600)
        else:
            logger.error('send_sensor: Sample #' + str(counter) +  ' Failed - code ' + str(response.status_code))
                    
    except requests.exceptions.RequestException as e:
        logger.error("send_sensor: Sample - erorr" +str(e))
    except requests.exceptions.ReadTimeout: 
        logger.error("send_sensor: Sample timeout")   
   
#Pi Object Storage System (Pioss)
# API-level and Method-level route decoration
@app.route('/pioss/api/write/<func_name>/<file_name>', methods=['POST'], endpoint='write_filename')  
@app.route('/pioss/api/read/<func_name>/<file_name>', methods=['GET'], endpoint='read_filename')
def pioss(func_name, file_name):
    global storage_folder
    global logger
    global lock
    global gateway_IP
    global http_admission_timeout
    
    #write operations
    if request.method == 'POST':
        logger.info('Pioss Write')
        try:
            with lock:
                #get image
                file = request.files['image_file']
                #download
                file.save(storage_folder + file_name)
                logger.info('Pioss: write done - func:' + func_name + ' - ' + file_name)
                
                #notification: trigger the object detection function
                #curl -X POST -H "X-Callback-Url: http://10.0.0.91:5000/actuator" -H "Image-API:http://10.0.0.91:5000/pioss/api/read/pic_41.jpg" http://10.0.0.91:31112/async-function/yolo3
                #Example: curl -X POST -F image_file=@./storage/pic_121.jpg  http://10.0.0.90:31112/function/yolo3
                #add sensor-id to -H
                
                #Trigger yolo function and pass Image_API
                url = 'http://' + gateway_IP + ':31112/async-function/' + func_name
                image_api = 'http://' + node_IP + ':5000/pioss/api/read/' + func_name + '/' + file_name
                callback_url = 'http://' + node_IP + ':5000/actuator'
                header = {'X-Callback-Url':callback_url,
                          'Image-API': image_api,
                          'Sensor-ID': str(request.headers.get('Sensor-ID'))}
                
                response=requests.post(url, headers=header, timeout=http_admission_timeout)
                #no response is received
                if response.status_code== 200 or response.status_code==202:
                    logger.info('Pioss: Notification Sent: ' + url)
                else:
                    logger.error('Pioss: Failed')
                return "write&notification done"
        except:
            logger.error('Pioss: write failed')
            time.sleep(3600)
            
    #read operation
    elif request.method == 'GET':
        logger.info('Pioss Read')
        #get file
        img = open(storage_folder + file_name, 'rb').read()
        #preapare response (either make_response or send_file)
        response = make_response(img)
        response.headers.set('Content-Type', 'image/jpeg')
        response.headers.set(
            'Content-Disposition', 'attachment', filename= file_name)
        
        return response
        #return send_file(io.BytesIO(img), attachment_filename=file_name)
    else:
        logger.error('Pioss: operation not found')
        return "Failed"
    

        

@app.route('/actuator', methods=['POST'])
def owl_actuator():
    global logger
    global actuations
    global response_time
    global test_started
    global test_finished
    global sensor_log
    global node_role
    global time_based_termination
    global apps
    global peers
    
    with lock:
        logger.info('actuator:' + str(request.headers.get('Sensor-Id')) + ' -')
        data=request.get_data(as_text=True)       
        
        #print('ID: ' + get_id)
        #id_temp=get_id.split("#")[1]
        #logger.info('Actuator #' + str(actuations) + ' Sensor #'+ id_temp)
        #logger.warning('--------------------------')
        #logger.warning(str(request.headers))
        #logger.warning(str(data))
        #print(str(data))
        #print(str(request.headers))
        #print('ACT:Sensor Source: ', str(request.headers.get('Host')))
        #print('ACT: Sensor Date: ', str(request.headers.get('Date')))
        print('actuator: Duration: ', str(request.headers.get('X-Duration-Seconds')))
        
        response_time.append(float(request.headers.get('X-Duration-Seconds')))
         
        
        
        #get sensor id
        get_id = str(request.headers.get('Sensor-Id'))
        if get_id==None:
            logger.error('actuator - Sensor-ID=None for #' + str(actuations))
            logger.warning("actuator: ", str(request.headers))
        #[0] function name
        actuations+=1
        #and
        c= [index for index, app in enumerate(apps) if app[0] == sensor_log[get_id][0]]
        apps[c[0]][7] +=1
        #[1]created time already set     
        #[2]admission duration already set
        #[3] set NATstream queuing duration
        #sensor_log[get_id][2]= float(request.headers.get('X-Start-Time')) - sensor_log[get_id][0] - sensor_log[get_id][1]
        sensor_log[get_id][3]= None
        #[4] set execution duration=given by openfaas
        sensor_log[get_id][4]= float(request.headers.get('X-Duration-Seconds'))
        
        #[5] finished time=now
        now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        sensor_log[get_id][5]= now
        
        #[6]set response time (round trip)=finished time- created time
        sensor_log[get_id][6]= sensor_log[get_id][5]-sensor_log[get_id][1]
        #[3] queuing=response time - admission dur. and execution dur.
        sensor_log[get_id][3]=sensor_log[get_id][6]-sensor_log[get_id][2]-sensor_log[get_id][4]
        if sensor_log[get_id][3]<0: sensor_log[get_id][3]=0
    
    
    #Termination
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    #alternative, if exist any -1 in finished time list, wait for timeout and then finish
    #check termination by received sensors or time
    logger.info(apps[0][0] + ' ' + str(apps[0][6]) + ' - ' + str(apps[0][7]) + '---' + apps[1][0] + ' ' + str(apps[1][6]) + ' - ' + str(apps[1][7]))
    all_apps_done = True
    for app in apps:
        #Among enabled apps
        if app[1] == True:
            #Have you finished sending?
            if app[6] != 0:
                #Have you finished receiving?
                if app[6] == app[7]:
                    #app is done
                    logger.info("actuator: App {0} done, recv {1} of {2}".format(
                        app[0], str(app[7]), str(app[6])))
                else:
                    #receiving in progress
                    all_apps_done = False
                    break
            else:# sending in progres
                all_apps_done = False
                break
        
    if all_apps_done == True: 
        #all apps done
        logger.info('actuator: all_apps_done')
        for sensor in sensor_log.values():
            if sensor[4]==-1: #finished time
                logger.error('actuator-missed sensor ' + sensor[0])
                time.sleep(300)
                
        #Time-based termination
        if time_based_termination[0]=='True':
            dur=int(time_based_termination[1])
            logger.info('actuator: Termination wait: ' + str(dur - (now-test_started)) + ' sec')
            time.sleep(dur - (now-test_started))
            now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        
        test_finished= now
        logger.info('actuator: test_finished  '+ str(test_finished))
        #local pi monitor off
        pi_service('off')
        
        if node_role=="LOAD_GENERATOR":
            #remote pi_monitors off
            reply=[]
            try:
                for i in range(len(peers)):
                    response=requests.get('http://10.0.0.' + peers[i] + ':5000/pi_service/off') #master
                    reply.append(response.text)
            except Exception as e:
                print(str(e))
                logger.error('actuator: Peers unavailable: IP:' + peers[i])
                time.sleep(300)
            
            if len([r for r in reply if "success" in r])==len(peers):
                if len(peers)==0:
                    logger.info('actuator: No Peers')
                else:
                    logger.info('actuator: Remote Peer Monitor Inactive')
    
            else:
                logger.error('actuator: Failed - remote peers monitors')
                time.sleep(300)
                
    return 'Actuator Sample Done'


#---------------------------------------
# monitoring
def pi_monitor():
    logger.info('pi_monitor: started')
    global current_time
    global current_time_ts
    global response_time_accumulative
    global battery_usage
    global pijuice
    global cpuUtil
    global cpu_temp
    global cpu_freq_curr
    global cpu_freq_max
    global cpu_freq_min
    global cpu_ctx_swt
    global cpu_inter
    global cpu_soft_inter
    global memory
    global disk_usage
    global disk_io_usage
    global bw_usage
    global power_usage
    global under_test
    global raspbian_upgrade_error
    global battery_cfg
    
    while under_test:
        #time
        #ct = datetime.datetime.now().strftime("%d%m%Y-%H%M%S")
        ct = datetime.datetime.now(datetime.timezone.utc).astimezone() # local
        ct_ts = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp() # local ts

        current_time.append(ct)
        current_time_ts.append(ct_ts)
        
        #response time
        if not response_time:
            response_time_accumulative.append(0)
        else:
            response_time_accumulative.append(sum(response_time)/len(response_time))
        # read battery
        if battery_operated:
            charge = pijuice.status.GetChargeLevel()
            battery_usage.append(int(charge['data']))
            
        elif battery_cfg[0]==True:
            battery_max_cap = battery_cfg[1]
            soc = battery_cfg[2]
            soc_percent = round(soc / battery_max_cap * 100)
            battery_usage.append(soc_percent)
    
        else:
            battery_usage.append(-1)
        
        # read cpu
        cpu = psutil.cpu_percent()
        cpuUtil.append(cpu)
        #cpu frequency
        freq=re.split(', |=', str(psutil.cpu_freq()).split(')')[0])
        cpu_freq_curr.append(freq[1])
        cpu_freq_min.append(freq[3])
        cpu_freq_max.append(freq[5])
        
        swt=re.split(', |=', str(psutil.cpu_stats()).split(')')[0])
        cpu_ctx_swt.append(int(swt[1]))
        cpu_inter.append(int(swt[3]))
        cpu_soft_inter.append(int(swt[5]))
        
        # read memory
        memory_tmp = psutil.virtual_memory().percent
        memory.append(memory_tmp)
        # read disk
        disk_usage_tmp = psutil.disk_usage("/").percent
        disk_usage.append(disk_usage_tmp)
        # read disk I/O: read_count, write_count, read_bytes, write_bytes
        if raspbian_upgrade_error:
            tmp=['-1','-1','-1','-1','-1','-1','-1','-1',]
        else:
            tmp = str(psutil.disk_io_counters()).split("(")[1].split(")")[0]
            tmp= re.split(', |=', tmp)
        tmp_list= [int(tmp[1]), int(tmp[3]), int(tmp[5]), int(tmp[7])]
        disk_io_usage.append(tmp_list)
        # read cpu temperature
        cpu_temp_tmp = psutil.sensors_temperatures()
        #print(cpu_temp_tmp)
        cpu_temp_temp2 = cpu_temp_tmp['cpu_thermal'][0]
        cpu_temp_tmp = re.split(', |=', str(cpu_temp_temp2))
        cpu_temp.append(cpu_temp_tmp[3])
        # read bandwidth: packets_sent, packets_rec, bytes_sent, bytes_rec, bytes_dropin, bytes_dropout
        bw_tmp = [psutil.net_io_counters().packets_sent, psutil.net_io_counters().packets_recv,
                  psutil.net_io_counters().bytes_sent, psutil.net_io_counters().bytes_recv,
                  psutil.net_io_counters().dropin, psutil.net_io_counters().dropout]
        bw_usage.append(bw_tmp)

        #read usb power meter
        if usb_meter_involved:
            power_usage.extend(read_power_meter())
        else:
            power_usage.append([-1,-1,-1,-1,-1,-1])
        
        time.sleep(1)
        
    logger.info("pi_monitor: stopped ->save_reports")
    #close bluetooth connection
    if usb_meter_involved:
        sock.close()
    #save reports in CSV files.
    save_reports()
    logger.info('pi_monitor: done')

def read_power_meter():
    global lock
    global sock
    output = []
    # Send request to USB meter
    d = b""
    with lock:
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
    
    output.append(temp)
    return output

#connect to USB power meter
def usb_meter_connection():
    #python usbmeter --addr 00:15:A5:00:03:E7 --timeout 10 --interval 1 --out /home/pi/logsusb
    global sock
    sock=None
    addr = bluetooth_addr1
    sock = BluetoothSocket(RFCOMM)
    
    attempts =3
    while True:
        try:
            res = sock.connect((addr, 1))
        except:
            logger.info("usb_meter_connection: Failed to connect to USB Meter:" + addr)
            
        else:
            print("Connected OK")
            logger.info('usb_meter_connection: USB Meter Connected Ok (' + addr + ')')
            break
    
        attempts -=1
        time.sleep(60)
        if attempts <=0:
            #wifi on
            cmd = "rfkill unblock all"
            print(cmd)
            logger.error(cmd)
            os.system(cmd)
            print('usb_meter_connection: ERROR-USB Meter Failed to connect!!!!!')
            logger.error('ERROR-USB Meter Failed to connect!!!!!')
            if battery_operated: battery_power('ON')
            logger.error('usb_meter_connection: Pi in Sleep...')
            time.sleep(86400)
             
    
# ---------------------------------

def save_reports():
    global apps
    global test_name
    global report_path
    global test_started
    global test_finished
    global sensor_log
    global node_role
    global snapshot_report
    global throughput
    global throughput2
    

    #print logs
    logger.critical('save_reports: Test ' + test_name + ' lasted: ' + str(test_finished - test_started) + ' sec')
    
    if node_role=="LOAD_GENERATOR":
        #calculate response times
        app_name = []
        creation_time=[]
        admission_duration=[]
        queuing_duration=[]
        execution_duration=[]
        finished_time=[]
        response_time_sens=[]
#[0] func_name [1]created, [2]submitted/admission-dur, [3]queue-dur, [4]exec-dur. [5] finished, [6]rt
        sensor_data = []
        for sensor in sensor_log.values():
            app_name.append(sensor[0])
            creation_time.append(sensor[1])
            admission_duration.append(sensor[2])
            queuing_duration.append(sensor[3])
            execution_duration.append(sensor[4])
            finished_time.append(sensor[5])
            response_time_sens.append(sensor[6])
            #rt.append(sensor[2]) #response time
            #roundt.append(sensor[3]) #round trip
            
            sensor_data.append([sensor[0],sensor[1],sensor[2], sensor[3], sensor[4], sensor[5], sensor[6]])
        
        log_index = report_path + "sensors.csv"
        logger.critical('save_reports: ' + log_index)
        np.savetxt(log_index, sensor_data, delimiter=",", fmt="%s")
        
        #overall rt
        logger.critical('Overall Response Time:')
        logger.critical('Avg. Adm. Dur.: ' + str(round(sum(admission_duration)/len(admission_duration),2)))
        logger.critical('Avg. Q. Dur.: ' + str(round(sum(queuing_duration)/len(queuing_duration),2)))
        logger.critical('Avg. Exec. +(scheduling) Dur.: ' + str(round(sum(execution_duration)/len(execution_duration),2)))
        logger.critical('Avg. RT: ' + str(round(sum(response_time_sens)/len(response_time_sens),2)))
        
        #Percentile
        percentiles = np.percentile(response_time_sens, [0, 25, 50, 75, 90, 95, 99, 99.9, 100])
        logger.critical('Percentiles: ' + str(percentiles))
        
        #per app rt
        #how many apps?
        for app in apps:
            app_name = []
            creation_time=[]
            admission_duration=[]
            queuing_duration=[]
            execution_duration=[]
            finished_time=[]
            response_time_sens=[]
            if app[1]== True:
                for sensor in sensor_log.values():
                    if sensor[0] == app[0]:
                        creation_time.append(sensor[1])
                        admission_duration.append(sensor[2])
                        queuing_duration.append(sensor[3])
                        execution_duration.append(sensor[4])
                        finished_time.append(sensor[5])
                        response_time_sens.append(sensor[6])
                        
                #print per app
                logger.critical('App ' + app[0])
                logger.critical('Avg. Adm. Dur.: ' + str(round(sum(admission_duration)/len(admission_duration),2)))
                logger.critical('Avg. Q. Dur.: ' + str(round(sum(queuing_duration)/len(queuing_duration),2)))
                logger.critical('Avg. Exec. +(scheduling) Dur.: ' + str(round(sum(execution_duration)/len(execution_duration),2)))
                logger.critical('Avg. RT: ' + str(round(sum(response_time_sens)/len(response_time_sens),2)))
                
                #Percentile
                percentiles = np.percentile(response_time_sens, [0, 25, 50, 75, 90, 95, 99, 99.9, 100])
                logger.critical('Percentiles: ' + str(percentiles))
                
                #System Throughput (every 30sec)
                timer=test_started + 30
                
                
                while True:
                    created=0
                    for time in creation_time:
                        if time < timer and time > timer - 30:
                            created+=1
                            
                    finished=0
                    for time in finished_time:
                        if time < timer and time > timer - 30:
                            finished+=1
                            
                    #avoid divided by zero
                    if created==0:
                        throughput.append(0)
                    else:
                        throughput.append((finished/created) * 100)
                    throughput2.append(finished/ 30)
                    
                    if timer >= (test_finished):
                        break
                    else:
                        timer+=30
                
                logger.critical('######throughput='+ str(round(sum(throughput)/len(throughput),2)))
                #logger.critical('######throughput='+ str(throughput))
                logger.critical('######throughput2='+ str(round(sum(throughput2)/len(throughput2),2)))

         
                
    #else role is MONITOR
    
    
    
    log_index = report_path + "monitor.csv"
    labels = ['time1', 'time2', 'rt_acc', 'battery', 'cpu_util', 'memory', 'disk',
        'cpu_temp','cpu_freq_curr', 'cpu_freq_min', 'cpu_freq_max', 'cpu_ctx_swt', 'cpu_inter', 'cpu_soft_inter',
        'io_read_count', 'io_write_count', 'io_read_bytes', 'io_write_bytes',
        'bw_pack_sent', 'bw_pack_rec', 'bw_bytes_sent', 'bw_bytes_rec', 'bw_bytes_dropin', 'bw_bytes_dropout',
        'mwh', 'mah', 'watts', 'amps', 'volts', 'temp']
    
    monitor_data = []
    monitor_data.append(labels)
    for i in range(len(cpuUtil)):
        curr_list =[]
        curr_list.append(str(current_time[i]))
        curr_list.append(str(current_time_ts[i]))
        curr_list.append(str(response_time_accumulative[i]))
        #???Throughput accumulative
        curr_list.append(str(battery_usage[i]))
        curr_list.append(str(cpuUtil[i]))
        curr_list.append(str(memory[i]))
        curr_list.append(str(disk_usage[i]))
        curr_list.append(str(cpu_temp[i]))
        curr_list.append(str(cpu_freq_curr[i]))
        curr_list.append(str(cpu_freq_min[i]))
        curr_list.append(str(cpu_freq_max[i]))
        curr_list.append(str(cpu_ctx_swt[i]))
        curr_list.append(str(cpu_inter[i]))
        curr_list.append(str(cpu_soft_inter[i]))
        curr_list.append(str(disk_io_usage[i][0]))
        curr_list.append(str(disk_io_usage[i][1]))
        curr_list.append(str(disk_io_usage[i][2]))
        curr_list.append(str(disk_io_usage[i][3]))
        curr_list.append(str(bw_usage[i][0]))
        curr_list.append(str(bw_usage[i][1]))
        curr_list.append(str(bw_usage[i][2]))
        curr_list.append(str(bw_usage[i][3]))
        curr_list.append(str(bw_usage[i][4]))
        curr_list.append(str(bw_usage[i][5]))
        if usb_meter_involved:
            curr_list.append(str(power_usage[i][0]))
            curr_list.append(str(power_usage[i][1]))
            curr_list.append(str(power_usage[i][2]))
            curr_list.append(str(power_usage[i][3]))
            curr_list.append(str(power_usage[i][4]))
            curr_list.append(str(power_usage[i][5]))
                
        
        monitor_data.append(curr_list)

    np.savetxt(log_index, monitor_data, delimiter=",", fmt="%s")
    
    
    logger.critical('Save_Reports: ' + log_index)
    if len(response_time)==0: response_time.append(1)
    logger.critical('Overal')
    logger.critical('######Exec. time avg='+ str(round(sum(response_time)/len(response_time),2)))
    logger.critical('######Exec. time accumulative='+ str(sum(response_time_accumulative)/len(response_time_accumulative)))
    logger.critical('######cpu=' + str(round(sum(cpuUtil)/len(cpuUtil),2)))
    logger.critical('######memory='+ str(round(sum(memory)/len(memory),2)))
    logger.critical('######disk_io_usage_Kbyte_read=' + str(round((disk_io_usage[-1][2] - disk_io_usage[0][2])/1024,2)))
    logger.critical('######disk_io_usage_Kbyte_write=' + str(round((disk_io_usage[-1][3] - disk_io_usage[0][3])/1024,2)))
    #logger.critical('######bw_packet_sent=' + str(round(bw_usage[-1][0] - bw_usage[0][0],2)))
    #logger.critical('######bw_packet_recv=' + str(round(bw_usage[-1][1]- bw_usage[0][1],2)))
    logger.critical('######bw_Kbytes_sent=' + str(round((bw_usage[-1][2] - bw_usage[0][2])/1024,2)))
    logger.critical('######bw_Kbytes_recv=' + str(round((bw_usage[-1][3] - bw_usage[0][3])/1024,2)))
    
    usb_meter_loop_index=-1
    for row in power_usage:
        if row[0]==99999:
            usb_meter_loop_index = power_usage.index(row)
            break
    if usb_meter_loop_index==-1:
        logger.critical('######power_usage=' + str(power_usage[-1][0]- power_usage[0][0]))
    else:
        usage=power_usage[usb_meter_loop_index][0] - power_usage[0][0]
        usage += power_usage[-1][0] - power_usage[usb_meter_loop_index+1][0]                       
        logger.critical('######power_usage_loop=' + str(usage))
        
    if snapshot_report[0]=='True':
        begin=int(snapshot_report[1])
        end=int(snapshot_report[2])
        logger.critical('Snapshot: ' + str(begin) + ' to ' + str(end))
        
        logger.critical('######Exec. time avg='+ str(round(sum(response_time)/len(response_time),2)))
        logger.critical('######Exec. time accumulative='+ str(sum(response_time_accumulative)/len(response_time_accumulative)))
        logger.critical('######cpu=' + str(round(sum(cpuUtil[begin:end])/len(cpuUtil[begin:end]),2)))
        logger.critical('######memory='+ str(round(sum(memory[begin:end])/len(memory[begin:end]),2)))
        logger.critical('######bw_packet_sent=' + str(round(bw_usage[end][0] - bw_usage[begin][0],2)))
        logger.critical('######bw_packet_recv=' + str(round(bw_usage[end][1]- bw_usage[begin][1],2)))
        logger.critical('######bw_Kbytes_sent=' + str(round((bw_usage[end][2] - bw_usage[begin][2])/1024,2)))
        logger.critical('######bw_Kbytes_recv=' + str(round((bw_usage[end][3] - bw_usage[begin][3])/1024,2)))
        if usb_meter_involved:
            logger.critical('######power_usage=' + str(power_usage[end][0]- power_usage[begin][0]))


@app.route('/pi_service/<cmd>')   
def pi_service(cmd):
    global under_test
    global logger
    global node_role
    global test_started
    global test_finished
    global battery_cfg
    logger.info('pi_service: '+ cmd)
    if cmd=='on':
        under_test=True
        thread_monitor= threading.Thread(target = pi_monitor, args=()).start()
        if battery_cfg[0]==True:
            if usb_meter_involved==False:
                logger.error('pi_service: USB Meter is needed for Battery Sim')
                time.sleep(300)
            thread_battery_sim = threading.Thread(target = battery_sim, args=()).start()
        if node_role=="MONITOR":
            test_started= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        return 'success'
    elif cmd=='off':
        under_test=False
        if node_role=="MONITOR":
            test_finished= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()

        return 'success'
    else:
        logger.error('pi_service: cmd not found')
        return 'failed'
    logger.info('pi_service: done')
   

def battery_sim():
    global logger
    global under_test
    global battery_cfg
    logger.info('battery_sim: Start')
    battery_max_cap = battery_cfg[1] #theta: maximum battery capacity in mWh
    
    #Generate renewable energy traces
    np.random.seed(battery_cfg[3][0])
    renewable = np.random.poisson(battery_cfg[3][1], 10000)
    renewable_index = 0;
    
    previous_usb_meter = read_power_meter()[0][0]
    
    while under_test:
        #GET
        soc = battery_cfg[2] #soc: prevous observed SoC in Mwh
        renewable_value = renewable[renewable_index]
        usb_meter = read_power_meter()[0][0]
        energy_usage = usb_meter - previous_usb_meter
        #fix USB meter loop in 99999 to 97223. NOTE: INTERVALS SHOULD NOT BE TOO LONG: > 2500mWH
        if usb_meter - previous_usb_meter < 0:
            energy_usage = (99999 - previous_usb_meter) + (usb_meter - 97222)
        #UPDATE
        soc= min(battery_max_cap, soc + renewable_value - energy_usage)
        battery_cfg[2] = soc
        
        renewable_index+=1
        previous_usb_meter = usb_meter      
                
        time.sleep(battery_cfg[4])
    
    logger.info('battery_sim: Stop')
# ---------------------------------

    

if __name__ == "__main__":
    logger = logging.getLogger('dev')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    fileHandler = logging.FileHandler(report_path+ 'PiService.log')
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.INFO)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    consoleHandler.setLevel(logging.INFO)

    logger.addHandler(fileHandler)
    logger.addHandler(consoleHandler)         
    
    logger.info('main: Turn off USB, HDMI and free up memory')
    #Turn OFF HDMI output
    cmd="sudo /opt/vc/bin/tvservice -o"
    os.system(cmd)
    #Turn OFF USB chip: https://learn.pi-supply.com/make/how-to-save-power-on-your-raspberry-pi/#disable-wi-fi-bluetooth
    cmd="echo '1-1' |sudo tee /sys/bus/usb/drivers/usb/unbind"
    os.system(cmd)
    # free up memory
        # cache (e.g., PageCache, dentries and inodes) and swap
    cmd = "sudo echo 3 > sudo /proc/sys/vm/drop_caches && sudo swapoff -a && sudo swapon -a && printf '\n%s\n' 'Ram-cache and Swap Cleared'"
    os.system(cmd)
    
    #connect to usb power meter
    if usb_meter_involved:
        usb_meter_connection()
    
    #only run this on worker 1
    #start
    if node_role=="LOAD_GENERATOR":    
        #1 run pi_monitor
        pi_service('on')
        
        #2 other pi_monitors
        reply=[]
        try:
            
            for i in range(len(peers)):
                response=requests.get('http://10.0.0.' + peers[i] + ':5000/pi_service/on') #master
                reply.append(response.text)
        except Exception as e:
            print(str(e))
            logger.error('main: Peers unavailable: IP:' + peers[i])
            time.sleep(60)
        
        if len([r for r in reply if "success" in r])==len(peers):
            if len(peers)==0:
                logger.info('main: No Peers')
            else:
                logger.info('main: Peer Monitor Active')
            #3 start test
            test_started= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            
            
            #4 run apps
            for my_app in apps:
                if my_app[1] == True:
                    threading.Thread(target = workload, args=(my_app,)).start()
                    #yolo3
                    #if my_app[0]=='yolo3':
                    #    thread_app_yolo3= threading.Thread(target = workload, args=(my_app,)).start()
                    #crop-monitor
                    #if my_app[0] == 'crop-monitor':
                    #    thread_app_short= threading.Thread(target = workload, args=(my_app,)).start()
                    #short
                    #if my_app[0] == 'short':
                    #    thread_app_short= threading.Thread(target = workload, args=(my_app,)).start()
        
        
        else:
            logger.error('main: remote monitors failed')
            time.sleep(300)
            
    #end
    serve(app, host= '0.0.0.0', port='5000')
    
    