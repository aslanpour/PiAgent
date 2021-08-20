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
import os #file path
from collections import Counter #get different items in a list
#test_plan file exists?
dir_path=os.path.dirname(os.path.realpath(__file__))
if os.path.exists(dir_path + "/test_plan.py"): import test_plan

app = Flask(__name__)
app.config["DEBUG"] = True

#config
node_name=socket.gethostname() 
node_role=""   #MONITOR #LOAD_GENERATOR #STANDALONE #MASTER
def set_ip():
    s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    actual_ip=s.getsockname()[0]
    s.close()
    return actual_ip
node_IP=set_ip() 
gateway_IP="10.0.0.90" #??? set individually
peers=[]
test_name = socket.gethostname() + "_test"
#local_value #local_ref #offload_value #offload_ref
debug=False
report_path ="/home/pi/Desktop/logs/" + test_name + "/"
if not os.path.exists(report_path):
    os.makedirs(report_path)

bluetooth_addr = "00:15:A3:00:52:2B"
#master: #00:15:A3:00:52:2B #w1: 00:15:A3:00:68:C4 #w2: 00:15:A5:00:03:E7 #W3: 00:15:A5:00:02:ED #w4: 00:15:A3:00:19:A7 #w5: 00:15:A3:00:5A:6F
pics_folder = "/home/pi/pics/"
pics_num = 170 #pics name "pic_#.jpg"
storage_folder = "/home/pi/storage/"
if not os.path.exists(storage_folder):
    os.makedirs(storage_folder)
#settings
#[0]app name
#[1] run/not
#[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
#[3] workload: [[0]iteration
                #[1]interval/exponential lambda(10=avg 8s)
                #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
#[4] func_name [5] func_data [6] sent [7] recv
#[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
apps=[['yolo3', False, 'static', [100, 12, 1, 5], 'yolo3', 'reference', 0, 0,
       ["1", "1", "50", "100", "0", "0", "3679","30s","30s","30s","30s",
        "disabled", "queue-worker", "yolo3",]],
      ['crop-monitor', False, 'static', [600, 1, 9, 5], 'crop-monitor', 'value', 0, 0,
       ["1", "1", "50", "100", "0", "0", "3679","30s","30s","30s","30s",
        "disabled", "queue-worker", "crop-monitor",]],
      ['irrigation', False, 'static', [600, 1, 9, 5], 'irrigation', 'value', 0, 0,
       ["1", "1", "50", "100", "0", "0", "3679","30s","30s","30s","30s",
        "disabled", "queue-worker", "irrigation",]],
      ['short', False, 'static', [300, 1, 5, 5], 'short', 'value', 0, 0,
       ["1", "1", "50", "100", "0", "0", "3679","30s","30s","30s","30s",
        "disabled", "queue-worker", "short",]]]

usb_meter_involved = False
#Either battery_operated or battery_cfg should be True, if the second, usb meter needs enabling
battery_operated=False
#Battery simulation
battery_cfg = [False, 850,850, 850, [5,5], 10] #1:max,2:initial #3:current SoC, 4:renwable seed&lambda, 5:interval
#NOTE: apps and battery_cfg values change during execution
time_based_termination= [False, 3600] 
snapshot_report=['False', '200', '800'] #begin and end time
request_timeout = 30
http_admission_timeout = 3
monitor_interval=1
failure_handler_interval = 3
scheduling_interval=600
overlapped_allowed= True
cpu_capacity=4000
raspbian_upgrade_error= False #True, if psutil io_disk error due to upgrade
#controllers
test_started = None
test_finished = None
under_test=False
lock = threading.Lock()
actuations = 0


sock = None #bluetooth connection
sensor_log ={}
suspended_replies = []
#monitoring parameters
    #in owl_actuator
response_time = []
    #in pi_monitor
response_time_accumulative = []
current_time = []
current_time_ts = []
battery_charge = []
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


def set_plan(coordinator):
    global logger
    global node_name
    global node_IP
    logger.info('set_plan: start')   
    
    #set plan for coordinator itself.
    name=coordinator[1]
    ip=coordinator[2]
    plan=test_plan.plan[name]
    
    #verify node_name 
    if name!=node_name:
        logger.error('MAIN: Mismatch node name: actual= ' + node_name + ' assigned= ' + name)
        return 'set_plan: Mismatch node name: actual= ' + node_name + ' assigned= ' + name
    #verify assigned ip
    if ip != node_IP:
        logger.error('set_plan: Mismatch node ip: actual= ' + node_IP + ' assigned= ' + ip)
        return ""
    
    sender=plan["node_role"] #used in sending plan to peers
    logger.info('set_plan: ' + name + ': ' + str(ip))

    reply=pi_service('plan', 'INTERNAL', plan)
    
    if reply != "success":
        logger.error('set_plan: INTERNAL interrupted and stopped')
        return "failed"
    
    reply_success=0
    #set peers plan
    for node in test_plan.nodes:
        position=node[0]
        name=node[1]
        ip=node[2]
        plan=test_plan.plan[name]
        if position is "PEER":
            logger.info('set_plan: peers:' + name + ': ' + str(ip)) 
            try:
                response=requests.post('http://'+ip+':5000/pi_service/plan/' + sender, json=plan)
            except Exception as e:
                logger.error('set_plan: peers: failed for ' + name + ":" + ip)
                logger.error('set_plan: peers: exception:' + str(e))
            if response.text=="success":
                logger.info('set_plan: ' + name + ' reply: ' + 'success')
                reply_success+=1
            else:
                logger.error('set_plan: peers: request.text for ' + name + ' ' + str(request.text))
        
        
    #verify peers reply
    peers= len([node for node in test_plan.nodes if node[0]=="PEER"])
    if reply_success== peers:
        logger.info('set_plan: all ' + str(peers) + ' nodes successful')
        
        #run local pi_service on
        logger.info('set_plan: run all nodes pi_service')
        
        #internal
        thread_pi_service_on = threading.Thread(target= pi_service, args=('on', 'INTERNAL',)).start()
        
        #function scheduler roll-out
        logger.info('set_plan: function roll out wait ' + str(test_plan.function_creation_roll_out) + 's')
        time.sleep(test_plan.function_creation_roll_out)
        
        #set peers on
        reply_success=0
        for node in test_plan.nodes:
            position=node[0]
            name=node[1]
            ip=node[2]
            if position is "PEER":
                logger.info('set_plan:pi_service on: peers:' + name + ': ' + str(ip)) 
                try:
                    response=requests.post('http://'+ip+':5000/pi_service/on/' + sender)
                except Exception as e:
                    logger.error('set_plan: pi_service on: peers: failed for ' + name + ":" + ip)
                    logger.error('set_plan: pi_service on: peers: exception:' + str(e))
                if response.text=="success":
                    logger.info('set_plan: pi_service on:' + name + ' reply: ' + 'success')
                    reply_success+=1
                else:
                    logger.info('set_plan: pi_service on:' + name + ' reply: ' + str(response.text))
        #verify peers reply
        peers= len([node for node in test_plan.nodes if node[0]=="PEER"])
        if reply_success== peers:
            logger.info('set_plan: pi_service on: all ' + str(peers) + ' nodes successful')
        else:
            logger.info('set_plan: pi_service on: only ' + str(reply_success) + ' of ' + str(peers))
        
        
        
        
    else:
        logger.info('set_plan: failed: only ' + str(reply_success) + ' of ' + str(len(test_plan.nodes)))
    logger.info('set_plan: stop')
 
def scheduler():
    global under_test
    global logger
    global scheduling_interval
    global node_role
    global battery_cfg
    logger.info('scheduler:start')

    #worker (peer) nodes:name, ip
    workers=[]
    functions=[]
    scheduling_round = 0
    
    for node in test_plan.nodes:
        position = node[0]
        name = node[1]
        ip= node[2]
        charge= battery_cfg[3]#current SoC
        capacity=test_plan.plan[name]["cpu_capacity"]
        if position == "PEER":
            #add worker
            worker =[name,ip, charge, capacity]
            workers.append(worker)
            logger.info('scheduler:workers:\n' + (str(worker) + '\n' for worker in workers))
            #add functions
            apps=plan[name]["apps"]
            for app in apps:
                if app[1]==True:
                    worker_name=worker[0]
                    app_name=app[0]
                    identity = [worker_name, app_name]
                    host=[]
                    func_info=app[7]
                    profile = app[8]
                    
                    function=[]
                    
                    #per replicas
                    for rep in range (func_info[1]): #max replica
                        
                        #update host capacity
                        func_cpu_limits = func_info[3]
                        index=workers.index(worker)
                        workers[index][3]-=func_cpu_limits
                        
                        #default is local placement
                        host.append(worker)
                        
                    function = [identity, host, func_info, profile]
                    functions.append(function)
                    f_name= function[0][0]+ '-'+function[0][1]
                    logger.info('scheduler:initial:function (' + f_name + '):\n' + str(function))
    
    logger.info('scheduler:workers:\n' + (str(worker) + '\n' for worker in workers))
    logger.info('scheduler:functions:\n' + (str(function) + '\n' for function in functions))
    #placement
    max_cpu_capacity=4000
    max_battery_charge=100
    min_battery_charge=10
    
    #execute initial placements (all local)
    logger.info('scheduler:executor')
    duration = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    for function in functions:
        scheduler_executor_create_profile(function)
        #wait to profile gets effective
        time.sleep(test_plan.profile_creation_wait)
        
        scheduler_executor_create_function(function, scheduling_round)
        
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp() - duration
    logger.info('scheduler:executor:initial placements done in ' + str(int(duration)) + 'sec')   
    #send updated cpu_capacity to workers ????
        
    
    logger.info('scheduler: initial sleep for ' + str(scheduling_interval) + ' sec...')
    time.sleep(scheduling_interval)
    

    while under_test:
        scheduling_round +=1
        logger.info('scheduler: MAPE LOOP START: ' + str(scheduling_round))
        #definitions
        
        #MONITOR
        for worker in workers:
            ip=worker[1]
            response=requests.get('http://' + ip + ':5000/pi_service/charge/' + node_role)
            charge=response.text
            index=workers.index(worker)
            workers[index][2]=charge
        logger.info('scheduler:monitor:\n' + (str(worker) for worker in workers))
        #ANALYZE
        
        #PLAN
        
        #EXECUTE
        
        
        #sliced interval in 1 minutes
        logger.info('scheduler: sleep for ' + str(scheduling_interval) + ' sec...')
        remained= scheduling_interval
        minute=60
        while remained>0:
            if remained>=minute:
                time.sleep(minute)
                remained-=minute
                if not under_test:
                    break
            else:
                time.sleep(remained)
                remained=0
        
        
        
    logger.info('scheduler:stop')
        
def scheduler_executor_create_profile(function):
    global logger
    
    nodeAffinity_required_filter1= "unknown"
    nodeAffinity_required_filter2 = "unknown"
    nodeAffinity_required_filter3 = "unknown"
    nodeAffinity_preferred_sort1 = "unknown"
    podAntiAffinity_preferred_functionName = "unknown"
    podAntiAffinity_required_functionName = "unknown"
    
    owner_name = function[0][0]
    app_name = function[0][1]
    function_name= owner_name + '-' + app_name
    hosts= function[1]
    logger.info("scheduler_executor_create_profile:" + function_name + "start")
    selected_nodes=[]
    for host in hosts:
        selected_nodes.append(host[0])
        
    selected_nodes_set=list(set(selected_nodes))
    #if selected_nodes=[w1,w2,w2] then selected_nodes_set result is [w1, w2]
    #place on 1 node
    if len(selected_nodes_set)==1:
        nodeAffinity_required_filter1 = selected_nodes_set[0]
    #place on 2 nodes
    elif len(selected_nodes_set)==2:
        nodeAffinity_required_filter1 = selected_nodes_set[0]
        nodeAffinity_required_filter2 = selected_nodes_set[1]
        preference = ""
        if selected_nodes.count(selected_nodes_set[0])==2:
            preference = selected_nodes_set[0]
        else:
            preference = selected_nodes_set[1]
        
        nodeAffinity_preferred_sort1 = preference
        podAntiAffinity_preferred_functionName= function_name
    #place on 3 nodes
    elif len(selected_nodes_set)==3:
        nodeAffinity_required_filter1 = selected_nodes_set[0]
        nodeAffinity_required_filter2 = selected_nodes_set[1]
        nodeAffinity_required_filter3 = selected_nodes_set[2]
        podAntiAffinity_required_functionName = function_name
    else:
        logger.error('scheduler_set_profile:' + function_name + 'selected_nodes_set length > 3')
        
    
    #create profile by helm chart
    cmd = ("helm upgrade " + test_plan.profile_chart[0] + " " + test_plan.profile_chart[1]
        + " --install --wait -n openfaas "
        + " --set profile.name=" + app_name
        + " --set profile.nodeAffinity.required.filter1=" +
           nodeAffinity_required_filter1
        + " --set profile.nodeAffinity.required.filter2=" +
           nodeAffinity_required_filter2
        + " --set profile.nodeAffinity.required.filter3=" +
           nodeAffinity_required_filter3
        + " --set profile.nodeAffinity.preferred.sort1=" +
           nodeAffinity_preferred_sort1
        + " --set profile.podAntiAffinity.preferred.functionName=" +
           podAntiAffinity_preferred_functionName
        + " --set profile.podAntiAffinity.required.functionName=" +
           podAntiAffinity_required_functionName)
    #run the cmd
    try:
        msg=os.system(cmd)
        logger.info("scheduler_executor_create_profile:"+ function_name +"return:" + str(msg))
        #update profile in function
        function[3]= [nodeAffinity_required_filter1, nodeAffinity_required_filter2, nodeAffinity_required_filter3,
            nodeAffinity_preferred_sort1, podAntiAffinity_preferred_functionName, podAntiAffinity_required_functionName]

    except Exception as e:
        logger.error("scheduler_executor_create_profile:" + function_name + "failed:" + str(e))
    logger.info("scheduler_executor_create_profile:" + function_name + "stop")
    
def scheduler_executor_create_function(function, version):
    global logger
    global node_IP
    app_version = version
    identity= function[0]
    node_name= identity[0]
    app_name= identity[1] #app_name is also used for function image name
    function_name = node_name + '-' + app_name
    logger.info("scheduler_executor_create_function:start:" + function_name)
    
    func_info=function[2]
    
    #create function by helm chart
    cmd = ("helm upgrade " + test_plan.function_chart[0] + " " + test_plan.function_chart[1]
            + " --install --wait -n openfaas-fn --set function.gateway=http://" + node_IP + ":31112"
            + " --set function.name=" + function_name
            + " --set function.scale.min=" + function[2][0]
            + " --set function.scale.max=" + function[2][1]
           + " --set function.requests.cpu=" + function[2][2]
           + " --set function.limits.cpu=" + function[2][3]
           + " --set function.env.counter=" + function[2][4]
           + " --set function.env.redisServerIp=" + function[2][5]
           + " --set function.env.redisServerPort=" + function[2][6]
           + " --set function.env.readTimeout=" + function[2][7]
           + " --set function.env.writeTimeout=" + function[2][8]
           + " --set function.env.execTimeout=" + function[2][9]
           + " --set function.env.handlerWaitDuration=" + function[2][10]
           + " --set function.annotations.linkerd=" + function[2][11]
           + " --set function.annotations.queue=" + function[2][12]
           + " --set function.annotations.profile="
           + function_name
           + " --set function.imageName="
           + app_name
           + " --set function.env.version=" + str(app_version))
    
    logger.info('scheduler_executor_create_function:cmd:' + function_name + ':' + cmd)
    try:
        msg = os.system(cmd)
        logger.info('scheduler_executor_create_function:' + function_name + 'msg:' + str(msg))
    except Exception as e:
        logger.error('scheduler_executor_create_function:error:' + function_name + ':' + str(msg))
        
    logger.info("scheduler_executor_create_function:" + function_name + ":stop")
        
@app.route('/workload', methods=['POST'])
def workload(my_app):
    time.sleep(1)  # Give enough time gap to send req to server to avoid connection error. or use sessions
    global logger
    global test_started
    global test_finished
    global apps
    global request_timeout
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
    
    
    
    logger.info("workload: App {0} \n workload: {1} \n Iteration: {2} \n Interval {3} Avg.({4}) \n Concurrently {5} Avg. ({6})\n"
                " Seed {7} \n function {8} data {9}\n------------------------------".format(
        func_name, workload_type, iteration,
        interval, sum(interval)/len(intervaintl) if "exponential" in workload_type else "--",
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
            
        #check termination: do not sleep after the final iteration or test is forced to finish
        if i == iteration-1 or under_test==False:
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
            logger.error('Workload: Iteration #' + str(i) + ' overlapped! (' + str(iter_elapsed) + ')')
            print('Workload Iteration #' + str(i) + ' overlapped!')
            time.sleep(3600)
            
    #break   
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    logger.info('workload: done: ' + func_name +': finished in ' + str(round(now-test_started,2)) + ' sec')
    
    #set sent
    apps[apps.index(my_app)][6] = sent
    
    #wait for all actuators of this app, or for timeout, then move
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: app: ' + my_app[0] + ' sleep 5sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(5)
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: app: ' + my_app[0] + ' sleep 10sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(10)
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: app: ' + my_app[0] + ' sleep 15sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(15)
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: app: ' + my_app[0] + ' sleep ' + str(request_timeout-30+1) + 'sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(request_timeout-30+1)
        
    logger.info("Workload: done, app: " + my_app[0] + " sent:" + str(my_app[6])
                + " recv:" + str(apps[apps.index(my_app)][7]))
    
    #App workload is finished, call pi_service if timer is not already stopped
    if under_test:
        pi_service('app_done','INTERNAL')
    logger.info('workload: app: ' + my_app[0] + ' stop') 
    return 'workload: Generator done'


def all_apps_done():
    global logger
    global apps
    global sensor_log
    global time_based_termination
    global test_finished # by the last app
    global node_role
    global peers
    global request_timeout
    global lock
    global sensor_log
    logger.info('all_apps_done: start')
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    #alternative, if exist any -1 in finished time list, wait for timeout and then finish
    
    #all apps termination
    all_apps_done = True
    for app in apps:
        #Among enabled apps
        if app[1] == True:
            #Have you finished sending?
            if app[6] != 0:
                #Have you finished receiving?
                if app[6] == app[7]:
                    #app is done
                    logger.info("all_apps_done: True: App {0} done, recv {1} of {2}".format(
                        app[0], str(app[7]), str(app[6])))
                else:
                    #receiving in progress
                    logger.info('all_apps_done: False: app ' + app[0] + ' send < recv: ' + str(app[6]) + " < " + str(app[7]))
                    all_apps_done = False
                    break
            else:# sending in progres
                logger.info('all_apps_done:False: app ' + app[0] + ' not set sent yet')
                all_apps_done = False
                break

                
    logger.info('all_apps_done: stop: ' +str(all_apps_done))
    return all_apps_done

    
def send_sensor(counter, func_name, func_data,admission_deadline):
    global pics_num
    global pics_folder
    global sensor_log
    global gateway_IP
    global node_IP
    global overlapped_allowed
    global debug
    #one-off sensor
    sample_started = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    try:
        #random image name, pic names must be like "pic_1.jpg"
        n = random.randint(1,pics_num) 
        file_name ='pic_' + str(n) + '.jpg'
        file={'image_file': open(pics_folder + file_name, 'rb')}
    
        #create sensor id
        sensor_id= str(sample_started) + '#' + func_name + '-#' + str(counter) 
        #[0] func_name [1]created, [2]submitted/admission-dur, [3]queue-dur, [4]exec-dur,
        #[5] finished, [6]rt, [7] status, [8] repeat
        sensor_log[sensor_id]= [func_name, sample_started, 0, 0, 0, 0, 0, -1, 0]
        
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
            #send
            response=requests.post(url, headers=header, files=img, json=json_list, timeout=http_admission_timeout)

            
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
        
        #handle 404 error ?????                                 
        if response.status_code==202 or response.status_code==200:
            
            now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            sample_elapsed = now - sample_started
            if debug: logger.info('send_sensor:' + func_name + ':# ' + str(counter) + ': '+ '- Success, admission (' + str(round(sample_elapsed,2)) + 's)')
            #Set admission time
            sensor_log[sensor_id][2]= sample_elapsed
            if (sample_elapsed) >= admission_deadline:
                logger.warning('send_sensor:' + func_name + ':#' + str(counter) + ': ' + ' admission overlapped (' + str(sample_elapsed) + 's)')
                if not overlapped_allowed:
                    logger.error('send_sensor:'+ func_name + ':# ' + str(counter) + ': ' + ' admission overlapped (' + str(sample_elapsed) + 's)')
  
        else:
            logger.error('send_sensor:' + func_name + ':# ' + str(counter) + ': ' +str(response.status_code))
                    
    except requests.exceptions.RequestException as e:
        logger.error('send_sensor except (e):' + func_name + ':# ' + str(counter) + str(e))
    except requests.exceptions.ReadTimeout: 
        logger.error('send_sensor except:' + func_name + ':# ' + str(counter) + 'timeout')
    except Exception as ee:
        logger.error('send_sensor except (ee):' + func_name + ':# ' + str(counter) + str(ee))
   
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
    global debug
    #write operations
    if request.method == 'POST':
        if debug: logger.info('Pioss Write')
        try:
            with lock:
                #get image
                file = request.files['image_file']
                #download
                file.save(storage_folder + file_name)
                if debug: logger.info('Pioss: write done - func:' + func_name + ' - ' + file_name)
                
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
                    if debug: logger.info('Pioss: Notification Sent: ' + url)
                else:
                    logger.error('Pioss: Failed')
                return "write&notification done"
        except:
            logger.error('Pioss: write failed')
            time.sleep(3600)
            
    #read operation
    elif request.method == 'GET':
        if debug: logger.info('Pioss Read')
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
    global sensor_log
    global time_based_termination
    global apps
    global peers
    global suspended_replies
    global debug
    
    with lock:
        if debug: logger.info('actuator, sensor-ID=' + str(request.headers.get('Sensor-Id')) + ' -')
        data=request.get_data(as_text=True)       
        
        #print('ID: ' + get_id)
        #id_temp=get_id.split("#")[1]
        #logger.info('Actuator #' + str(actuations) + ' Sensor #'+ id_temp)
        #logger.warning('--------------------------')
        if debug and 'yolo3' in str(request.headers): logger.warning(str(request.headers))
        #logger.warning(str(data))
        #print(str(data))
        #print(str(request.headers))
        #print('ACT:Sensor Source: ', str(request.headers.get('Host')))
        #print('ACT: Sensor Date: ', str(request.headers.get('Date')))
         
        actuations+=1
        
        #get sensor id
        #X-Function-Status: 500
        #X-Function-Name: yolo3
        get_id = str(request.headers.get('Sensor-Id'))
        #print('get_id: ' + str(get_id))
        
        #if failed 
        if get_id=='None':
            if debug: logger.warning('Actuator - Sensor-ID=None| app: ' +request.headers.get("X-Function-Name") + '| code: ' + request.headers.get("X-Function-Status") +' for #' + str(actuations))
            if debug: logger.warning("Actuator: " + str(request.headers))
            func_name= str(request.headers.get("X-Function-Name"))
            status = int(request.headers.get("X-Function-Status"))
            #IGNORED
            #NOTE: X-start-Time in headers is based on a different timeslot and format than my timestamp
            #sometimes X-Start-Time header is missed in replies with code 500, so set start_time=now
            if str(request.headers.get("X-Start-Time")) !='None':
                start_time= float(request.headers.get("X-Start-Time"))
            else: start_time = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            #END IGNORED
            
            stop_time = start_time = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            exec_dur= float(request.headers.get("X-Duration-Seconds"))
            
            #add to suspended replies
            suspended_replies.append([func_name, status, stop_time, exec_dur])
        else: #code=200
            print('Actuator: Duration: ', str(request.headers.get('X-Duration-Seconds')))
        
            response_time.append(float(request.headers.get('X-Duration-Seconds')))
        
            #[0] function_name already set
            #[1]created time already set     
            #[2]admission duration already set
            #[3] set NATstream queuing duration
            #NOTE: Openfaas X-Start-Time value is in 19 digits, not simillar to my timestamp
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
            #[7] status code
            sensor_log[get_id][7]=int(request.headers.get('X-Function-Status'))
            #[8] replies
            sensor_log[get_id][8]= sensor_log[get_id][8]+ 1
            #increment received
            c= [index for index, app in enumerate(apps) if app[0] == sensor_log[get_id][0]]
            apps[c[0]][7] +=1
            
            #if repetitious 
            if sensor_log[get_id][8] >1:
                logger.error('Actuator: a repetitious reply received: ' + str(sensor_log[get_id]))
                
    return 'Actuator Sample Done'


#---------------------------------------
def failure_handler():
    global logger
    global sensor_log
    global request_timeout
    global failure_handler_interval
    global suspended_replies
    global apps
    global under_test
    logger.info('failure_handler: start')
    #status codes:
    #404: happens in send_sensor: not submitted to gateway as function does not exist (already removed)
    #500: happens after submission: submitted but while executing, function started rescheduling to going down. Partial execution of task can happen here
    #502: happens after submission: submitted but function is in scheduling process and is not up yet
    #502: function timeout (especified in function yaml file)
    #503: gateway timeout (especified in gateway yaml by kubectl edit deploy/gateway -n openfaas
    #note: queue-worker timeout seems ineffective
    #function and gateway have timeout settings.
    wrap_up=request_timeout + (failure_handler_interval*2)
    
    while under_test or wrap_up > 0:
        #missed sensors
        missed_sensor_log = {}
        
        now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        #exist suspended replies
        if len(suspended_replies) > 0:
            #set missed sensors
            for key, sensor in sensor_log.items():
                #among those with no reply received by code
                if sensor[7]==-1:
                    #make sure it will not receive any reply
                    #and outdated (must have received a timeout reply at least, so it's missed)
                    if sensor[1] + request_timeout < now:
                        #add to missed sensors
                        missed_sensor_log[key]=sensor
            #sort missed sensors ascendingly by creation time
                        #NOTE: sort, remove, etc. return None and should not be assigned to anything
            sorted(missed_sensor_log.items(), key=lambda e: e[1][1])
            
            #sort suspended replies ascendingly by stop_time
            suspended_replies.sort(key=lambda x:x[2])
            
            #assign suspended_replies to outdated missed_sensors
            for key, missed_sensor in missed_sensor_log.items():
                for reply in suspended_replies:
                    #As sorted, get the first match and break
                    #same application
                    #reply=[func_name, status, stop_time, exec_dur] #start_time is not used???? It is sometimes missed in replies 500 by OpenFaaS
                    if missed_sensor[0] == reply[0]:
                        #set exec_duration
                        missed_sensor[4]= reply[3]
                        #set status
                        missed_sensor[7]= reply[1]
                        #set reply counter
                        missed_sensor[8]= missed_sensor[8] + 1
                        
                        #update sensor_log
                        sensor_log[key]= missed_sensor
                        
                        #increment received
                        c= [index for index, app in enumerate(apps) if app[0] == missed_sensor[0]]
                        apps[c[0]][7] +=1
                        
                        #removal of the suspended reply
                        suspended_replies.remove(reply)
                        break
        time.sleep(failure_handler_interval)
        
        if not under_test:
            #only first time run
            if wrap_up ==request_timeout + (failure_handler_interval*2):
                logger.info("failure_handler: wrapping up: " + str(wrap_up) + "sec...")
            if not all_apps_done(): #is all_apps_done, no need to wait for failure handler
                wrap_up -= failure_handler_interval
            else:
                break
            #only last time run
            if wrap_up<=0:
                logger.info('failure_handler:missed' + str(missed_sensor_log) )
                logger.info('failure_handler:suspended' + str(suspended_replies))
    logger.info('failure_handler: stop')
    
    
    
# monitoring
def pi_monitor():
    logger.info('pi_monitor: start')
    global monitor_interval
    
    global current_time
    global current_time_ts
    global response_time_accumulative
    global battery_charge
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
            battery_charge.append(int(charge['data']))
        #battery sim    
        elif battery_cfg[0]==True:
            battery_max_cap = battery_cfg[1]
            soc = battery_cfg[3]
            soc_percent = round(soc / battery_max_cap * 100)
            battery_charge.append(soc_percent)
    
        else:
            battery_charge.append(-1)
        
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
        
        time.sleep(monitor_interval)
        
    
    #close bluetooth connection
    if usb_meter_involved:
        sock.close()
    
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
    addr = bluetooth_addr
    sock = BluetoothSocket(RFCOMM)
    
    attempts =1
    connected=None
    
    while True:
        try:
            res = sock.connect((addr, 1))
        except:
            logger.error("usb_meter_connection: Failed to connect to USB Meter:" + addr)
            connected=False
            break
        else:
            print("Connected OK")
            logger.info('usb_meter_connection: USB Meter Connected Ok (' + addr + ')')
            connected=True
            break
    
    attempts -=1
    #time.sleep(60)
    if attempts <=0 and connected==False:
        #wifi on
        cmd = "rfkill unblock all"
        print(cmd)
        logger.info(cmd)
        os.system(cmd)
        print('usb_meter_connection: ERROR-USB Meter Failed to connect!!!!!')
        logger.error('ERROR-USB Meter Failed to connect!!!!!')
        if battery_operated: battery_power('ON')
        #logger.error('usb_meter_connection: Pi in Sleep...')
        #time.sleep(86400)
             
    return connected
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
    
    test_finished= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()

    #print logs
    logger.critical('save_reports: Test ' + test_name + ' lasted: ' + str(test_finished - test_started) + ' sec')
    
    if node_role=="LOAD_GENERATOR" or node_role=="STANDALONE":
        #OVERALL
        
        #calculate response times
        app_name = []
        creation_time=[]
        admission_duration=[]
        queuing_duration=[]
        execution_duration=[]
        useless_execution_duration = []
        finished_time=[]
        response_time_sens=[]
        
        #send/recv sensors
        send = 0
        recv = 0
        for app in apps: #???index based on apps order, in future if apps change, it changes
            if app[1]==True:
                send+=app[6]
                recv+=app[7]
                
        logger.critical('send {} recv {}'.format(send,recv))
        
        #replies
        #actuator/reply counter
        replies_counter = [0]*len(apps)
        #reply status
        replies_status = [[0]*6 for _ in range(len(apps))]#*len(apps) #status code of 200, 500, 502, 503, others
        
#[0] func_name [1]created, [2]submitted/admission-dur, [3]queue-dur, [4]exec-dur. [5] finished, [6]rt
        sensor_data = []
        for sensor in sensor_log.values(): #consider failed ones ?????
            
            admission_duration.append(sensor[2])
            if sensor[7]==200: #only success sensors contribute in response time????? weight of failed ones???
                creation_time.append(sensor[1])
                finished_time.append(sensor[5])
                
                queuing_duration.append(sensor[3])
                execution_duration.append(sensor[4])
                
                response_time_sens.append(sensor[6])
            
            else:
                useless_execution_duration.append(sensor[4])
                
            c= [index for index, app in enumerate(apps) if app[0] == sensor[0]]
            app_index= apps.index(apps[c[0]])

            #apps[c[0]][7] +=1
            #reply counter
            replies_counter[app_index]+=sensor[8]

            #reply status
            if sensor[7]==200:
                replies_status[app_index][0]+=1
            elif sensor[7]== 500:
                replies_status[app_index][1]+=1
            elif sensor[7]==502:
                replies_status[app_index][2]+=1
            elif sensor[7]==503:
                replies_status[app_index][3]+=1
            elif sensor[7]==-1:
                replies_status[app_index][4]+=1
            else:#others
                replies_status[app_index][5]+=1
            
            
            #data list
            sensor_data.append([sensor[0],sensor[1],sensor[2], sensor[3], sensor[4], sensor[5], sensor[6], sensor[7], sensor[8]])
        #save sensor data
        log_index = report_path + "sensors.csv"
        logger.critical('save_reports: ' + log_index)
        np.savetxt(log_index, sensor_data, delimiter=",", fmt="%s")
        
        
        #PRINT LOGS of METRICS
        logger.critical('METRICS: OVERALL****************************')
        
        #OVERALL send recv by replies (actuators)
        logger.critical('OVERALL: REQ. SENT: ' +str(send)
        + ' RECV (by apps): ' + str(recv) + ' RECV (by sensor[8] counter): ' + str(sum(replies_counter)) )
        
        #OVERALL status codes
        code200=0
        code500=0
        code502=0
        code503=0
        code_1=0
        others=0
        for row in replies_status:
            code200+=row[0]
            code500+=row[1]
            code502+=row[2]
            code503+=row[3]
            code_1+=row[4]
            others+=row[5]
            
        logger.critical("OVERALL: Success Rate: {}%".format(round((code200/sum([code200,code500,code502,code503,code_1,others]))*100,2) if sum([code200,code500,code502,code503,code_1,others])>0 else "0"))
        logger.critical("OVERALL: {0}{1}{2}{3}{4}{5}".format(
                    'CODE200=' + str(code200) if code200>0 else ' ',
                    ', CODE500=' + str(code500) if code500>0 else ' ',
                    ', CODE502=' + str(code502) if code502>0 else ' ',
                    ', CODE503=' + str(code503) if code503>0 else ' ',
                    ', CODE-1=' + str(code_1) if code_1>0 else ' ',
                    ', OTHERS=' + str(others) if others>0 else ' '))
        
        #OVERALL response time
        logger.critical('OVERALL: avg. Adm. Dur.: ' + (str(round(sum(admission_duration)/len(admission_duration),2)) if len(admission_duration)>0 else "No Value"))
        logger.critical('OVERALL: avg. Q. Dur. (success only): ' + (str(round(sum(queuing_duration)/len(queuing_duration),2)) if len(queuing_duration)>0 else "No Value"))
        logger.critical('OVERALL: avg. Exec. +(scheduling) Dur. (success only): ' + (str(round(sum(execution_duration)/len(execution_duration),2))if len(execution_duration)>0 else "NO Value"))
        logger.critical('OVERALL: sum Useless Exec. Dur.: ' + (str(round(sum(useless_execution_duration),2)) if len(useless_execution_duration)>0 else "No Value"))                
        logger.critical('OVERALL: avg. RT (soccess only): ' + (str(round(sum(response_time_sens)/len(response_time_sens),2)) if len(response_time_sens)>0 else "No Value"))
        
        #Percentile
        percentiles = (np.percentile(response_time_sens, [0, 25, 50, 75, 90, 95, 99, 99.9, 100])if len(response_time_sens)>0 else "No Value")
        logger.critical('OVERALL: Percentiles (success only): ' + str(percentiles))
        
        #Throughput (every 30sec)
        throughput=[]
        throughput2=[]
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
        
        logger.critical('OVERALL:throughput (success only)='+ str(round(sum(throughput)/len(throughput),2)))
        #logger.critical('######throughput='+ str(throughput))
        logger.critical('OVERALL: throughput2 (success only)='+ str(round(sum(throughput2)/len(throughput2),2)))


        logger.critical('METRICS PER APP****************************')
        #per app rt
        #how many apps?
        for app in apps:
            creation_time=[]
            admission_duration=[]
            queuing_duration=[]
            execution_duration=[]
            useless_execution_duration = []
            finished_time=[]
            response_time_sens=[]
            
            reply = 0
            status=[0]*6

            if app[1]== True:
                for sensor in sensor_log.values():
                    if sensor[0] == app[0]:
                        
                        admission_duration.append(sensor[2])
                        reply+=sensor[8]
                        if sensor[7]==200: #respoonse time only based on success tasks????weight of failed????
                            creation_time.append(sensor[1])
                            queuing_duration.append(sensor[3])
                            execution_duration.append(sensor[4])
                            finished_time.append(sensor[5])
                            response_time_sens.append(sensor[6])
                            
                            
                        else:
                            useless_execution_duration.append(sensor[4])
                            
                        #get status
                        if sensor[7]==200:
                            status[0]+=1
                        elif sensor[7]== 500:
                            status[1]+=1
                        elif sensor[7]==502:
                            status[2]+=1
                        elif sensor[7]==503:
                            status[3]+=1
                        elif sensor[7]==-1:
                            status[4]+=1
                        else:#others
                            status[5]+=1
                            
                #calculate metrics of this app

                #OVERALL send recv by replies (actuators)
                send = app[6]
                recv=app[7]
                
                logger.critical('APP('+app[0]+'): REQ. SENT: ' +str(send)
                + ' RECV (by apps): ' + str(recv) + ' RECV (by counter): ' + str(reply) )

                #status
                logger.critical("APP("+app[0]+"): Success Rate: {}%".format(round(status[0]/sum([status[0],status[1],status[2],status[3],status[4],status[5]])*100,2)))
                logger.critical('APP('+app[0]+'): {0}{1}{2}{3}{4}{5}'.format(
                'CODE200=' + str(status[0]) if status[0]>0 else ' ',
                'CODE500=' + str(status[1]) if status[1]>0 else ' ',
                'CODE502=' + str(status[2]) if status[2]>0 else ' ',
                'CODE503=' + str(status[3]) if status[3]>0 else ' ',
                'CODE-1=' + str(status[4]) if status[4]>0 else ' ',
                'OTHERS=' + str(status[5]) if status[5]>0 else ' '))
    

                #print per app
                logger.critical('APP('+app[0]+'): avg. Adm. Dur.: ' + (str(round(sum(admission_duration)/len(admission_duration),2)) if len(admission_duration)>0 else "No Value"))
                logger.critical('APP('+app[0]+'): avg. Q. Dur. (success only): ' + (str(round(sum(queuing_duration)/len(queuing_duration),2)) if len(queuing_duration)>0 else "No Value"))
                logger.critical('APP('+app[0]+'): avg. Exec. +(scheduling) Dur. (success only): ' + (str(round(sum(execution_duration)/len(execution_duration),2)) if len(execution_duration)>0 else "No Value"))
                logger.critical('APP('+app[0]+'): sum Useless Exec. Dur.: ' + (str(round(sum(useless_execution_duration),2)) if len(useless_execution_duration)>0 else "No Value"))                
                logger.critical('APP('+app[0]+'): avg. RT (success only): ' + (str(round(sum(response_time_sens)/len(response_time_sens),2)) if len(response_time_sens)>0 else "No Value"))
                
                #Percentile
                percentiles = (np.percentile(response_time_sens, [0, 25, 50, 75, 90, 95, 99, 99.9, 100]) if len(response_time_sens)>0 else [])
                logger.critical('APP('+app[0]+'): Percentiles (success only): ' + str(percentiles) )
                
                        
                #System Throughput (every 30sec)
                throughput=[]
                throughput2=[]
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
                
                logger.critical('APP('+app[0]+'):throughput (success only)='+ str(round(sum(throughput)/len(throughput),2)))
                #logger.critical('######throughput='+ str(throughput))
                logger.critical('APP('+app[0]+'): throughput2 (success only)='+ str(round(sum(throughput2)/len(throughput2),2)))

         
                
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
        curr_list.append(str(battery_charge[i]))
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
    logger.critical('METRICS********************')
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
    
    mwh_sum=0
    mwh_first=power_usage[0][0]
    mwh_second=0
    for row in power_usage[1:]:
        mwh_second=row[0]
        usage=mwh_second-mwh_first
        if usage<0: #loop point
            usage=(99999-mwh_first) + (mwh_second-97222)
    
        mwh_sum+=usage
        #exchange
        mwh_first=mwh_second
        
    usb_meter_loop_index=-1
    for row in power_usage:
        if row[0]==99999:
            usb_meter_loop_index = power_usage.index(row)
            break
    if usb_meter_loop_index==-1:
        logger.critical('######power_usage=' + str(power_usage[-1][0]- power_usage[0][0]) + ' new (' + str(mwh_sum) + ')')
    else:
        usage=power_usage[usb_meter_loop_index][0] - power_usage[0][0]
        usage += power_usage[-1][0] - power_usage[usb_meter_loop_index+1][0]                       
        logger.critical('######power_usage_loop=' + str(usage) + ' new (' + str(mwh_sum) + ')')
        
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


@app.route('/pi_service/<cmd>/<sender>',methods=['POST'])   
def pi_service(cmd, sender, plan={}):
    global under_test
    global monitor_interval
    global logger
    global node_role
    global test_started
    global test_finished
    global battery_cfg
    global apps
    global time_based_termination
    global sensor_log
    global request_timeout
    global battery_cfg
    global monitor_interval
    global battery_charge
    logger.info('pi_service: cmd = '+ cmd + ', sender = ' + sender)
    
    if cmd=='plan':
        #ACTIONS BASED ON SENDER role or location
        #wait
        if under_test==True:            
            under_test=False
            cooldown()
            
        #reset times, battery_cfg(current SoC), apps (send/recv), monitor, free up resources,
        reset()
            
        #plan
        #set plan for LOAD_GENERATOR, MONITOR, STANDALONE by master node
        if sender=='MASTER': 
            plan = request.json
                
            #verify plan
            if plan==None:
                logger.warning('pi_service:plan:master:no plan received, so default values are used')
            else:
                apply_plan(plan)
        #set plan for coordinator (master or standalone) by itself
        elif sender=="INTERNAL": 
            if len(plan)>0:
                apply_plan(plan)
            else:
                logger.error('pi_service:plan:INTERNAL: no plan received for coordinator')
                return "pi_service: plan: no plan received for master"
        #set plan for MONITOR only in standalone tests by STANDALONE node       
        elif sender=="STANDALONE":
            plan = request.json
            if plan==None:
                logger.warning('pi_service:plan:standalone: no plan received, so default values are used')        
            else:
                apply_plan(plan)
                
            if node_role!="MONITOR":
                logger.error('pi_service:plan:standalone: no monitor role for monitor')
                return "pi_service:plan:standalone: no monitor role for monitor"
        else:
            logger.error("pi_service:plan:unknown sender")
            return "pi_service:plan:unknown sender"     
             
        #show_plan()
        
        #verify usb meter connection
        if usb_meter_involved==True:
            if usb_meter_connection()==False:
                logger.error('pi_service:plan:usb_meter_connection:failed')
                return "pi_service:plan:usb_meter_connection:failed"
        
        return "success"
    
    #cmd=on        
    elif cmd=='on':
        #ACTIONS BASED ON assigned node_role
        #wait
        if under_test==True:            
            under_test=False
            cooldown()
            
        #reset times, battery_cfg(current SoC), apps (send/recv), monitor, free up resources,
        #reset()
        
        #get plan
        show_plan()
        
        #under test
        under_test=True
        
        #set start time
        test_started= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        
        #run pi_monitor
        thread_monitor= threading.Thread(target = pi_monitor, args=()).start()
            
        #run battery_sim
        if battery_cfg[0]==True:
            if usb_meter_involved==False:
                logger.error('pi_service:on: USB Meter is needed for Battery Sim')
                return "pi_service:on: USB Meter is needed for Battery Sim"
            thread_battery_sim = threading.Thread(target = battery_sim, args=()).start()

        #run timer
        if time_based_termination[0]==True:
            thread_timer = threading.Thread(target = timer, args=()).start()
                
        #run failuer handler
        if node_role=='LOAD_GENERATOR' or node_role=='STANDALONE':
            thread_failure_handler = threading.Thread(target = failure_handler, args=()).start()
            
        #run workload
        if node_role=="LOAD_GENERATOR" or node_role=='STANDALONE':
            #per apps
            for my_app in apps:
                if my_app[1] == True:
                    threading.Thread(target = workload, args=(my_app,)).start()
                    
        #run scheduler
        if node_role=="MASTER":
            threading.Thread(target = scheduler, args=()).start()
                
        return 'success'
    
    #called if an app workload finishes
    elif cmd=='app_done':
        if all_apps_done()==True:
            #avoid double stop at the same time
            if under_test==False:
                logger.info('pi_service:app_done: all apps done already or timer trigerred')
                return 'success'
            
            logger.info('pi_service:app_done: all apps done')
            
            if time_based_termination[0]==True:
                pass #refer to timer
            #not time based
            else:     
                if node_role=="STANDALONE":
                    peers_stop()
                #stop monitor and battery_sim
                under_test=False
                
                time.sleep(monitor_interval)
                logger.info('pi_service:app_done: call save reports')
                save_reports()
        else: logger.info('pi_service:app_done: a workload done, but not all apps yet')
          
    elif cmd=='stop':
        #stop monitor and battery_sim
        logger.info('pi_service:stop: under_test=False')
        under_test=False
        #stop workload in background, workload waits for req timeout
        cooldown()
        
        if node_role=="STANDALONE":
            peers_stop()
            
        if node_role=="MONITOR":
            test_finished= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        logger.info('pi_service:stop: call save_reports')
        save_reports()
    elif cmd=="charge":
        logger.info("pi_service:charge: sender:" + str(sender) + ": start")
        logger.info("pi_service:charge: sender:" + str(sender) + ": " + str(battery_charge[len(battery_charge)-1]) + ":" + str(battery_charge[-1]))
        return battery_charge[-1]
        logger.info("pi_service:charge: sender:" + str(sender) + ": stop")
    else:
        logger.error('pi_service: unknown cmd')
        return 'failed'
    
    logger.info('pi_service: stop')
 
def cooldown():
    global node_role
    global battery_cfg
    global monitor_interval
    global request_timeout
    global failure_handler_interval
    global apps
    global logger
    logger.info('cooldown:start')
    wait=0
    
    if node_role=="MONITOR" or node_role=="MASTER":
        if battery_cfg[0]==True:
            wait=sum([monitor_interval, battery_cfg[5]])
        else: wait=sum(monitor_interval)
        
    else: #node_role == "STANDALONE or LOAD_GENERATOR"
        if battery_cfg[0]==True:
            wait=sum([monitor_interval, battery_cfg[5], failure_handler_interval,request_timeout]) #sum get no more than 2 args
        else: wait=sum([monitor_interval, failure_handler_interval,request_timeout])
        #while any([True if app[1]==True and app[6]!=app[7] else False for app in apps ])==True:
        #    wait=3
        #    logger.info('cooldown: wait for ' + str(wait) + ' sec')
        #    time.sleep(wait)    
    logger.info('cooldown: wait for ' + str(wait) + ' sec...')
    time.sleep(wait)
    
    logger.info('cooldown: stop')
    
def show_plan():
    global test_name
    global node_name
    global debug
    global bluetooth_addr
    global apps
    global battery_cfg
    global time_based_termination
    global request_timeout
    global node_role
    global peers
    global monitor_interval
    global scheduling_interval
    global failure_handler_interval
    global usb_meter_involved
    global battery_operated
    global node_IP
    global socket
    global cpu_capacity
    global raspbian_upgrade_error
    
    logger.info('show_plan: start')
    show_plan= ("test_name: " + test_name
                + "node_name: " + str(socket.gethostname()) + " / " + str(node_name)
                + "\n IP: " + node_IP
                + "\n node_role: " + node_role
                + "\n Debug: " + str(debug)
                + "\n bluetooth_addr: " + bluetooth_addr
                + "\n apps: " + str(apps)
                + "\n peers: " + str(peers)
                + "\n usb_meter_involved: " + str(usb_meter_involved)
                + "\n battery_operated: " + str(battery_operated)
                + "\n battery_cfg: " + str(battery_cfg)
                + "\n time_based_termination: " + str(time_based_termination)
                + "\n monitor_interval: " + str(monitor_interval)
                + "\n scheduling_interval: " + str(scheduling_interval)
                + "\n failure_handler_interval: " + str(failure_handler_interval)
                + "\n request_timeout: " + str(request_timeout)
                + "\n cpu_capacity: " + str(cpu_capacity)
                + "\n raspbian_upgrade_error: " + str(raspbian_upgrade_error))
    logger.info("show_plan: " + show_plan)
    
    logger.info('show_plan: stop')
    
def apply_plan(plan):
    global test_name
    global debug
    global bluetooth_addr
    global apps
    global battery_cfg
    global time_based_termination
    global request_timeout
    global node_role
    global peers
    global monitor_interval
    global scheduling_interval
    global failure_handler_interval
    global usb_meter_involved
    global battery_operated
    global cpu_capacity
    global raspbian_upgrade_error
    logger.info('apply_plan: start')
    
    test_name = socket.gethostname() + "_" + plan["test_name"] 
    node_role = plan["node_role"]
    debug=plan["debug"]
    bluetooth_addr = plan["bluetooth_addr"]
    apps= plan["apps"]
    peers = plan["peers"]
    usb_meter_involved = plan["usb_meter_involved"]
    #Either battery_operated or battery_cfg should be True, if the second, usb meter needs enabling
    battery_operated=plan["battery_operated"]
    #Battery simulation
    battery_cfg = plan["battery_cfg"] #1:max,2:initial (and current) SoC, 3:renwable seed&lambda, 4:interval
    #NOTE: apps and battery_cfg values change during execution
    time_based_termination= plan["time_based_termination"] # end time-must be longer than actual test duration
    monitor_interval = plan["monitor_interval"]
    scheduling_interval=plan["scheduling_interval"]
    failure_handler_interval =plan["failure_handler_interval"]
    request_timeout=plan["request_timeout"]
    cpu_capacity =plan["cpu_capacity"]
    raspbian_upgrade_error = plan["raspbian_upgrade_error"]

    logger.info('apply_plan: stop')
    
    
def timer():
    global monitor_interval
    global request_timeout
    global failure_handler_interval
    global time_based_termination
    global test_started
    global under_test
    logger.info('timer: start')
    
    while under_test:
        now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        elapsed = now-test_started
        if elapsed>= time_based_termination[1]:
            break
        else:
            time.sleep(min(failure_handler_interval,monitor_interval, request_timeout))
    
    if under_test==True:
        #alarm pi_service
        pi_service('stop','INTERNAL')
        
def peers_stop():
    global logger
    global peers
    
    logger.info('peers_stop: all_apps_done or time ended')
    #remote pi_monitors stop
    reply=[]
    try:
        for i in range(len(peers)):
            response=requests.get('http://10.0.0.' + peers[i] + ':5000/pi_service/stop/STANDALONE')
            reply.append(response.text)
    except Exception as e:
        logger.error('peers_stop:error:' +peers[i] + ':' + str(s))
    
    if len([r for r in reply if "success" in r])==len(peers):
        if len(peers)==0:
            logger.info('peers_stop: No Peers')
        else:
            logger.info('peers_stop: Remote Peer Monitor Inactive')

    else:
        logger.error('peers_stop: Failed - remote peers monitors')

        
def battery_sim():
    global logger
    global under_test
    global battery_cfg
    logger.info('battery_sim: Start')
    battery_max_cap = battery_cfg[1] #theta: maximum battery capacity in mWh
    
    #Generate renewable energy traces
    np.random.seed(battery_cfg[4][0])
    renewable = np.random.poisson(battery_cfg[4][1], 10000)
    renewable_index = 0;
    
    previous_usb_meter = read_power_meter()[0][0]
    
    while under_test:
        #GET
        soc = battery_cfg[3] #soc: previous observed SoC in Mwh
        renewable_value = renewable[renewable_index]
        usb_meter = read_power_meter()[0][0]
        energy_usage = usb_meter - previous_usb_meter
        #fix USB meter loop in 99999 to 97223. NOTE: INTERVALS SHOULD NOT BE TOO LONG: > 2500mWH
        if usb_meter - previous_usb_meter < 0:
            energy_usage = (99999 - previous_usb_meter) + (usb_meter - 97222)
        #UPDATE
        #min to avoid overcharge. max to avoid undercharge
        soc= min(battery_max_cap, max(0, soc + renewable_value - energy_usage))

        battery_cfg[3] = soc
        
        renewable_index+=1
        previous_usb_meter = usb_meter      
                
        time.sleep(battery_cfg[5])
    
    logger.info('battery_sim: Stop')
# ---------------------------------

@app.route('/reset',methods=['POST']) 
def reset():
    logger.info('reset:start')
    global under_test
    global test_started
    global test_finished
    global sensor_log
    global battery_cfg
    global apps
    global failure_handler_interval
    global suspended_replies
    
    #monitoring parameters
    global response_time 
        #in pi_monitor
    global response_time_accumulative
    global current_time 
    global current_time_ts
    global battery_charge 
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
    global throughput
    global throughput2
    
    #preparation
    logger.info('recet: Turn off USB, HDMI and free up memory')
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
    
    #variables
    under_test = False
    test_started=None
    test_finished=None
    sensor_log ={}
    
    for i in range(len(apps)):
        apps[i][6]=0 #send
        apps[i][7]=0 #recv
    battery_cfg[3]=battery_cfg[2]#current =initial
    
    suspended_replies = []
    #monitoring parameters
        #in owl_actuator
    response_time = []
        #in pi_monitor
    response_time_accumulative = []
    current_time = []
    current_time_ts = []
    battery_charge = []
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
    
    logger.info('reset:stop')
    
'''def call_peer_monitor():
    global peers
    global logger
    logger.info('call_peer_monitor: start')
    reply=[]
    try:
        for i in range(len(peers)):
            response=requests.get('http://10.0.0.' + peers[i] + ':5000/pi_service/on/STANDALONE') 
            reply.append(response.text)
    except Exception as e:
        print(str(e))
        logger.error('call_peer_monitor: Peers unavailable: IP:' + peers[i])
        time.sleep(60)
    
    if len([r for r in reply if "success" in r])==len(peers):
        if len(peers)==0:
            logger.info('call_peer_monitor: No Peers')
        else:
            logger.info('call_peer_monitor: Peer Monitor Active')
    else:
        logger.error('call_peer_monitor: remote monitors failed')
        time.sleep(300)
        
    logger.info('call_peer_monitor: stop')'''
    


if __name__ == "__main__":
    logger = logging.getLogger('dev')
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    #default mode is append 'a' to existing log file. But, 'w' is write from scratch
    fileHandler = logging.FileHandler(report_path+ 'PiService.log', mode='w')
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.INFO)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    consoleHandler.setLevel(logging.INFO)

    logger.addHandler(fileHandler)
    logger.addHandler(consoleHandler)         

    #test_plan file exists?
    dir_path=os.path.dirname(os.path.realpath(__file__))
    if os.path.exists(dir_path + "/test_plan.py"):
        
        #run set_plan if coordinator
        for node in test_plan.nodes:
            #find this node in nodes
            position=node[0]
            name=node[1]
            if name==socket.gethostname():
                #verify if this node's position is COORDINATOR
                if position=="COORDINATOR":
                    #just MASTER and STANDALONE are eligible to be a COORDINATOR
                    if test_plan.plan[name]["node_role"]== "MASTER" or test_plan.plan[name]["node_role"]== "STANDALONE":
                        logger.info('MAIN: Node position is coordinator')
                        thread = threading.Thread(target= set_plan, args=(node,)).start()
                        
                        break
                    else:
                        logger.error('MAIN: Node role in its plan must be MASTER or STANDALONE')
                else:
                    logger.info('MAIN: Node position is ' + position)
    else:
        logger.info('MAIN: No test_plan found, so wait for a coordinator')

    serve(app, host= '0.0.0.0', port='5000')
    
    