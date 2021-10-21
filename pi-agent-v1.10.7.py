from flask import Flask, request, send_file, make_response, json #pip3 install flask
from waitress import serve #pip3 install waitress
import requests #pip3 install requests
import threading
import logging
import datetime
import time
import math
#Pi Monitor
import psutil
import numpy as np
import statistics #for using satistics.mean()  #numpy also has mean()
import re
import copy
import RPi.GPIO as GPIO
from pijuice import PiJuice  #sudo apt-get install pijuice-gui
from bluetooth import * #sudo apt-get install bluetooth bluez libbluetooth-dev && sudo python3 -m pip install pybluez
# sudo systemctl start bluetooth
# echo "power on" | bluetoothctl
import random
import socket
import os #file path
import shutil #empty a folder

#setup file exists?
dir_path=os.path.dirname(os.path.realpath(__file__))
if os.path.exists(dir_path + "/setup.py"): import setup
if os.path.exists(dir_path + "/excel_writer.py"): import excel_writer # pip3 install pythonpyxl
from os.path import expanduser #get home directory by home = expanduser("~")

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
test_index = 0
test_updates ={}

epoch = 0
test_name = socket.gethostname() + "_test"
workers = []
functions = []
history =  {'functions':{}, 'workers': {}}
metrics = {}

debug=False
waitress_threads = 6 # default is 4
#get home directory
home = expanduser("~")
log_path = home + "/" + test_name 
if not os.path.exists(log_path):
    os.makedirs(log_path)

bluetooth_addr = "00:15:A3:00:52:2B"
#master: #00:15:A3:00:52:2B #w1: 00:15:A3:00:68:C4 #w2: 00:15:A5:00:03:E7 #W3: 00:15:A5:00:02:ED #w4: 00:15:A3:00:19:A7 #w5: 00:15:A3:00:5A:6F
pics_folder = "/home/pi/pics/"
pics_num = 170 #pics name "pic_#.jpg"
file_storage_folder = "/home/pi/storage/"
if not os.path.exists(file_storage_folder):
    os.makedirs(file_storage_folder)
#settings
#[0]app name
#[1] run/not
#[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
#[3] workload: [[0]iteration
                #[1]interval/exponential lambda(10=avg 8s)
                #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
#[4] func_name [5] func_data [6] created [7] recv
#[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
apps=[]

usb_meter_involved = False
#Either battery_operated or battery_cfg should be True, if the second, usb meter needs enabling
battery_operated=False
#Battery simulation
#1:max,2:initial #3current SoC,
#4: renewable type, 5:poisson seed&lambda,6:dataset, 7:interval, 8 dead charge 
battery_cfg=[True, 906,906, 906,"poisson",[5,5], [], 30, 90]
#NOTE: apps and battery_cfg values change during execution
down_time = 0
time_based_termination= [False, 3600] 
snapshot_report=['False', '200', '800'] #begin and end time
max_request_timeout = 30
min_request_generation_interval = 0
sensor_admission_timeout = 3
monitor_interval=1
failure_handler_interval = 3
scheduling_interval=600
overlapped_allowed= True
max_cpu_capacity=4000
boot_up_delay = 0
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


def launcher(coordinator):
    global logger
    global node_name
    global node_IP
    logger.info('start')   
    
    #set plan for coordinator itself.
    name=coordinator[1]
    ip=coordinator[2]
    plan=setup.plan[name]
    #config for multi-tests
    plan["test_name"] = setup.test_name[epoch]
    #set counter per app
    plan["apps"][0][8][4]=setup.counter[epoch]["yolo3"]
    plan["apps"][1][8][4]=setup.counter[epoch]["irrigation"]
    plan["apps"][2][8][4]=setup.counter[epoch]["crop-monitor"]
    plan["apps"][3][8][4]=setup.counter[epoch]["short"]
    
    #verify node_name 
    if name!=node_name:
        logger.error('MAIN: Mismatch node name: actual= ' + node_name + ' assigned= ' + name)
        return 'Mismatch node name: actual= ' + node_name + ' assigned= ' + name
    #verify assigned ip
    if ip != node_IP:
        logger.error('Mismatch node ip: actual= ' + node_IP + ' assigned= ' + ip)
        return ""
    
    sender=plan["node_role"] #used in sending plan to peers
    logger.info(name + ' : ' + str(ip))
    #set local plan
    reply=pi_service('plan', 'INTERNAL', plan)
    
    if reply != "success":
        logger.error('INTERNAL interrupted and stopped')
        return "failed"
    
    reply_success=0
    #set peers plan, sequentially, including USB Meter connection
    for node in setup.nodes:
        position=node[0]
        name=node[1]
        ip=node[2]
        plan=setup.plan[name]
        #config for multi-test
        plan["test_name"] = setup.test_name[epoch]
        #set counter per app
        plan["apps"][0][8][4]=setup.counter[epoch]["yolo3"]
        plan["apps"][1][8][4]=setup.counter[epoch]["irrigation"]
        plan["apps"][2][8][4]=setup.counter[epoch]["crop-monitor"]
        plan["apps"][3][8][4]=setup.counter[epoch]["short"]
        
        if position is "PEER":
            logger.info('peers:' + name + ': ' + str(ip)) 
            try:
                response=requests.post('http://'+ip+':5000/pi_service/plan/' + sender, json=plan)
            except Exception as e:
                logger.error('peers: failed for ' + name + ":" + ip)
                logger.error('peers: exception:' + str(e))
                return
            if response.text=="success":
                logger.info(name + ' reply: ' + 'success')
                reply_success+=1
            else:
                logger.error('peers: request.text for ' + name + ' ' + str(response.text))
        
        
    #verify peers reply
    peers= len([node for node in setup.nodes if node[0]=="PEER"])
    if reply_success== peers:
        logger.info('all ' + str(peers) + ' nodes successful')
        
        #run local pi_service on
        logger.info('run all nodes pi_service')
        
        #internal
        thread_pi_service = threading.Thread(target= pi_service, args=('on', 'INTERNAL',))
        thread_pi_service.name = "pi-service"
        #it calls scheduler and deploys functions
        thread_pi_service.start()
        #wait for initial function deployment roll-out
        logger.info('function roll out wait ' + str(setup.function_creation_roll_out) + 's')
        time.sleep(setup.function_creation_roll_out)
        
        #set peers on sequentially
        reply_success=0
        for node in setup.nodes:
            position=node[0]
            name=node[1]
            ip=node[2]
            if position is "PEER":
                logger.info('pi_service on: peers:' + name + ': ' + str(ip)) 
                try:
                    response=requests.post('http://'+ip+':5000/pi_service/on/' + sender)
                except Exception as e:
                    logger.error('pi_service on: peers: failed for ' + name + ":" + ip)
                    logger.error('pi_service on: peers: exception:' + str(e))
                if response.text=="success":
                    logger.info('pi_service on:' + name + ' reply: ' + 'success')
                    reply_success+=1
                else:
                    logger.info('pi_service on:' + name + ' reply: ' + str(response.text))
        #verify peers reply
        peers= len([node for node in setup.nodes if node[0]=="PEER"])
        if reply_success== peers:
            logger.info('pi_service on: all ' + str(peers) + ' nodes successful')
        else:
            logger.info('pi_service on: only ' + str(reply_success) + ' of ' + str(peers))  
        
    else:
        logger.info('failed: only ' + str(reply_success) + ' of ' + str(len(setup.nodes)))
    logger.info('stop')
    
#scheduler 
def scheduler():
    global epoch
    global under_test
    global logger
    global debug
    global scheduling_interval
    global node_role
    global battery_cfg
    global workers
    global functions
    global max_cpu_capacity
    global log_path
    global history
    logger.info('start')

    
    #initialize workers and funcitons lists
    #default all functions' host are set to be placed locally
    workers, functions = initialize_workers_and_functions(setup.nodes, workers, functions,
                                                    battery_cfg, setup.plan, setup.zones)
    #history
    history["functions"]={}
    history["workers"]={}
        
    logger.info('after initialize_workers_and_functions:\n'
                + '\n'.join([str(worker) for worker in workers]))
    logger.info('after initialize_workers_and_functions:\n'
                + '\n'.join([str(function) for function in functions]))
    
    scheduling_round = 0
    while under_test:
        scheduling_round +=1
        logger.info('################################')
        logger.info('MAPE LOOP START: round #' + str(scheduling_round))
        #monitor: update Soc
        logger.info('monitor: call')
        workers = scheduler_monitor(workers, node_role)
        
        #ANALYZE (prepare for new placements)
        logger.info('analyzer: call')
        
        #definitions
        new_functions = copy.deepcopy(functions)
        
        #reset F's new location to null
        for new_function in new_functions:
            new_function[1] = []
        
        #reset nodes' capacity to max
        for worker in workers:
            worker[3] = setup.max_cpu_capacity
            
            
        #planner :workers set capacity, functions set hosts
        logger.info('planner: call: ' + str(setup.scheduler_name[epoch]))
        #Greedy
        if "greedy" in setup.scheduler_name[epoch]:
            workers, functions = scheduler_planner_greedy(workers, functions, new_functions,
                            setup.plan, setup.zones, setup.warm_scheduler,
                            setup.sticky, setup.stickiness[epoch], setup.scale_to_zero, debug)
        #Local
        elif "local" in setup.scheduler_name[epoch]:
            workers, functions = scheduler_planner_local(workers, new_functions, debug)
        #Default-Kubernetes
        elif "default" in setup.scheduler_name[epoch]:
            workers, functions = scheduler_planner_default(workers, new_functions, debug)
        #Random
        elif "random" in setup.scheduler_name[epoch]:
            workers, functions = scheduler_planner_random(workers, new_functions, debug)
        #Bin-Packing         
        elif "bin-packing" in setup.scheduler_name[epoch]:
            workers, functions = scheduler_planner_binpacking(workers, functions, new_functions, debug)
        #Optimal
        elif "optimal" in setup.scheduler_name[epoch]:
            pass
        else:
            logger.error('scheduler_name not found' + str(setup.scheduler_name[epoch]))
            return
        
        #EXECUTE
        logger.info('executor: call')
        #translate hosts to profile and then run helm command
        #return functions as it is modifying functions (i.e., profiles)
        functions = scheduler_executor(functions, setup.profile_chart,
                                       setup.profile_creation_roll_out,
                                       setup.function_chart, scheduling_round, log_path,
                                       setup.scheduler_name[epoch], workers, debug)

        
        #history
        history["functions"][scheduling_round] = copy.deepcopy(functions)
        history["workers"][scheduling_round] = copy.deepcopy(workers)
        
        #sliced interval in 1 minutes
        logger.info('MAPE LOOP (round #' + str(scheduling_round) + ') done: sleep for ' + str(scheduling_interval) + ' sec...')
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
    
    #save history
    
    #scheduler clean_up???    
    logger.info('stop')
        
        
#??? functions are received for only getting old_hosts. Only old_hosts can be sent to this planner
def scheduler_planner_greedy(workers, functions, new_functions, nodes_plan, zones,
                             warm_scheduler, sticky, stickiness, scale_to_zero, debug):
    global logger
    logger.info("scheduler_planner_greedy:start")
    logger.info('scheduler_planner_greedy:\n available Workers \n'
                + '\n'.join([str(worker) for worker in workers]))
    zone_name = {1:'rich', 2:'poor', 3: 'vulnerable', 4: 'dead'}
    #update zones
    for worker in workers:
        soc = worker[2]
        battery_max_cap = nodes_plan[worker[0]]["battery_cfg"][1]
        soc_percent = round(soc / battery_max_cap * 100)
        logger.info('soc percent: ' + str(soc_percent))
        new_zone = [*(zone[1] for zone in zones if soc_percent <= zone[2]
                  and soc_percent > zone[3])][0]
        worker[4]= new_zone

    logger.info('scheduler_planner_greedy:updated zones by Soc:\n'
                + '\n'.join([str(worker) for worker in workers]))
    
    #sort nodes by soc (large->small | descending)
    workers.sort(key=lambda x:x[2], reverse=True)
    logger.info('before showing : ' + str(workers))
    logger.info('scheduler_planner_greedy:sorted nodes by Soc (large->small):\n'
                + '\n'.join([str([worker,zone_name[worker[4]]]) for worker in workers]))
    logger.info('after showing : ' + str(workers))
    #sort functions: A: by priority of their owner's zone (small -> large | ascending)
    for i in range (len(new_functions)):
        lowest_value_index = i
        for j in range(i + 1, len(new_functions)):
            #find function's owner zone
            zone_j = [*(worker[4] for worker in workers if worker[0]==new_functions[j][0][0])][0]
            zone_lowest_value_index = [*(worker[4] for worker in workers if worker[0]==new_functions[lowest_value_index][0][0])][0]
            #compare zone priorities
            if zone_j < zone_lowest_value_index:
                lowest_value_index = j
        #swap
        new_functions[i], new_functions[lowest_value_index] = new_functions[lowest_value_index], new_functions[i]
    #end sort
    logger.info('scheduler_planner_greedy:sorted functions by owner\'s zone priority (small->large):\n'
                + '\n'.join([str(new_function[0]) for new_function in new_functions]))
    
    #B: sort functions in each zone (small to large for poor and vulnerable) opposite dead, for rich does not matter
    for i in range(len(new_functions)):
        lowest_value_index = i
        largest_value_index = i
        lowest, largest = False, False
        zone_i = [*(worker[4] for worker in workers if worker[0]==new_functions[i][0][0])][0]
        #rich or dead
        if zone_i == 1 or zone_i == 4:
            #largest first
            largest =True
        #poor or vulnerable
        else: lowest = True
        
        for j in range(i + 1, len(new_functions)):
            #get function's owner zone
            zone_j = [*(worker[4] for worker in workers if worker[0]==new_functions[j][0][0])][0]
            zone_lowest_value_index = [*(worker[4] for worker in workers if worker[0]==new_functions[lowest_value_index][0][0])][0]
            zone_largest_value_index = [*(worker[4] for worker in workers if worker[0]==new_functions[largest_value_index][0][0])][0]
            if zone_j == zone_lowest_value_index: #similar to say ==largest_value_index
                #get functions' owner soc
                soc_j = [*(worker[2] for worker in workers if worker[0]==new_functions[j][0][0])][0]
                soc_lowest_value_index = [*(worker[2] for worker in workers if worker[0]==new_functions[lowest_value_index][0][0])][0]
                soc_largest_value_index = [*(worker[2] for worker in workers if worker[0]==new_functions[largest_value_index][0][0])][0]
                #compare socs based on zones policy
                #if rich or dead , large to small
                if zone_largest_value_index == 1 or zone_largest_value_index == 4 :
                    if soc_j > soc_largest_value_index:
                        largest_value_index = j
                #if poor or vulnerable, small to large
                elif zone_lowest_value_index == 2 or zone_lowest_value_index == 3 :
                    if soc_j < soc_lowest_value_index:
                        lowest_value_index = j
        #swap
        if lowest:
            index = lowest_value_index
        else:
            index = largest_value_index
        new_functions[i], new_functions[index] = new_functions[index], new_functions[i]
    logger.info('scheduler_planner_greedy:sorted functions by soc in zones (poor and vulnerable small to large. Rich and dead opposite):\n'
                + '\n'.join([str(new_function[0]) for new_function in new_functions]))
    
    #so far, new_functions have [] as hosts, workers have full as capacity and both workers and new_functions are sorted now
    logger.info("scheduler_planner_greedy: start planning hosts for functions by priority")
    #PLAN
    #set hosts per function
    for new_function in new_functions:        
        #function's old_hosts: last placement scheme
        old_hosts = copy.deepcopy([*(function[1] for function in functions if function[0]==new_function[0])][0])
        
        #old_hosts have zone numbers and Soc based on last epoch and the hosts zone may have changed now, so update their zones based on new status
        for index, old_host in enumerate(old_hosts):
            #update host's zone, capacity and Soc based on current status
            old_hosts[index] = [*(worker for worker in workers if worker[0]==old_host[0])][0]
        logger.info('greedy: old_hosts\n' + str(old_hosts))
        
        #function's owner
        owner = [*(worker for worker in workers if worker[0]==new_function[0][0])][0]
        func_required_cpu_capacity = 0
            #exclude 'm'
        replica_cpu_limits = int(new_function[2][3].split('m')[0])
        func_max_replica = new_function[2][1]
        func_required_cpu_capacity = replica_cpu_limits * func_max_replica
        owner_zone = owner[4]
        logger.info('greedy: planning for *** ' + str(new_function[0][0]) + '-'
                    + str(new_function[0][1])+ ' *** ')
        #try to fill new hosts for new_function
        new_hosts = []
        #if new_function belongs to a rich node
        if owner_zone == 1:
            #place locally
            logger.info('greedy: ' + owner[0] + '-' + new_function[0][1] + ' ---> locally')
            for rep in range(func_max_replica):
                new_hosts.append(copy.deepcopy(owner))
        
        #if poor, vulnerable or dead
        else:               
            #if offloading
            #if setup.offloading == True:
            #if owners is dead, only offload if warm_scheduler is True; also if owner is poor or vulnerable, do the offloading
            if not (owner_zone == 4 and warm_scheduler == False):
                #Get rich and vulnerable (if the func is not vulnerable) workers
                volunteers = [*(worker for worker in workers if worker[4] == 1
                                or (worker[4]==3 and owner_zone != 3))]
                
                logger.info('greedy: call offloader: volunteers \n'
                            + '\n'.join([str(volunteer) for volunteer in volunteers]))
                            
                new_hosts = offloader(workers, functions, volunteers, new_function, sticky, stickiness,
                                      old_hosts, warm_scheduler,owner, func_max_replica,
                                      func_required_cpu_capacity, scale_to_zero, debug)

        # if not offloading was possible for fonctions owned by poor, vulnerable and dead nodes
        if new_hosts == []:
            #place locally
            logger.info('greedy: ' + owner[0] + '-' + new_function[0][1] + ' ---> locally')
            #how about functions belong to a dead node??? they are still scheduled locally
            for rep in range(func_max_replica):
                new_hosts.append(copy.deepcopy(owner))
                 
        #deduct function cpu requirement from worker's cpu capacity
        for new_host in new_hosts:
            #get selected worker index per replica
            index = workers.index([*(worker for worker in workers if worker[0]==new_host[0])][0])
            #deduct replica cpu requirement
            workers[index][3] -= replica_cpu_limits
            #update new_host, particulalrly its capacity
            new_host[3]= workers[index][3]

        #set new_function new hosts
        new_function[1] = new_hosts
        if debug: logger.info("scheduler_planner_greedy: new_hosts for ("
            + new_function[0][0] + "-" + new_function[0][1] + "):\n" + str(new_function[1]))

    #for loop: next new_function
        
    #replacad original functions with new_functions to apply new_hosts (placements)
    #functions = new_functions
    logger.info('scheduler_planner_greedy: done: functions:\n'
                + '\n'.join([str(new_function) for new_function in new_functions]))
    
    return workers, new_functions
 
#??? functions are received for only getting old_hosts. Only old_hosts can be sent to this planner
def scheduler_planner_binpacking(workers, functions, new_functions, debug):
    global logger
    logger.info("scheduler_planner_binpacking:start")
    logger.info('scheduler_planner_binpacking:\n available Workers \n'
                + '\n'.join([str(worker) for worker in workers]))
    
    #sort nodes by soc (large->small | descending)
    workers.sort(key=lambda x:x[2], reverse=True)

    logger.info('scheduler_planner_binpacking:sorted nodes by Soc (large->small):\n'
                + str(workers))

    #sort functions: by owner's soc (small -> large | ascending)
    for i in range (len(new_functions)):
        lowest_value_index = i
        for j in range(i + 1, len(new_functions)):
            #find function's owner soc
            soc_j = [*(worker[2] for worker in workers if worker[0]==new_functions[j][0][0])][0]
            soc_lowest_value_index = [*(worker[2] for worker in workers if worker[0]==new_functions[lowest_value_index][0][0])][0]
            #compare socs
            if soc_j < soc_lowest_value_index:
                lowest_value_index = j
        #swap
        new_functions[i], new_functions[lowest_value_index] = new_functions[lowest_value_index], new_functions[i]
    #end sort
    logger.info('scheduler_planner_binpacking:sorted functions by owner\'s soc(small->large):\n'
                + '\n'.join([str(new_function[0]) for new_function in new_functions]))
    
        
    #so far, new_functions have [] as hosts, workers have full as capacity and both workers and new_functions are sorted now
    logger.info("scheduler_planner_binpacking: start planning hosts for functions by soc")
    #PLAN
    #set hosts per function
    for new_function in new_functions:        
                
        #function's owner
        owner = [*(worker for worker in workers if worker[0]==new_function[0][0])][0]
        func_required_cpu_capacity = 0
            #exclude 'm'
        replica_cpu_limits = int(new_function[2][3].split('m')[0])
        func_max_replica = new_function[2][1]
        func_required_cpu_capacity = replica_cpu_limits * func_max_replica

        logger.info('binpacking: planning for *** ' + str(new_function[0][0]) + '-'
                    + str(new_function[0][1])+ ' *** \n Required_cpu_capacity: '
                    + str(func_required_cpu_capacity))
        #try to fill new hosts for new_function
        new_hosts = []
        #only functions belong to up nodes are scheduled. Those belong to dead nodes schedule locally
        min_battery_charge = battery_cfg[8]
        if owner[2] >= min_battery_charge:
            #pick the first possible option
            for index , worker in enumerate(workers):
                #if node is up
                if worker[2] >= min_battery_charge:
                    #if node has capacity
                    if worker[3] >= func_required_cpu_capacity:
                        for rep in range(func_max_replica):
                            new_hosts.append(copy.deepcopy(worker))
                #if set
                if new_hosts != []:
                    break

                            
        #dead node, schedule locally    
        else:
            logger.info('bin_packing: locally')
            for rep in range(func_max_replica):
                new_hosts.append(copy.deepcopy(owner))
                                
        #deduct function cpu requirement from worker's cpu capacity
        for new_host in new_hosts:
            #get selected worker index per replica
            index = workers.index([*(worker for worker in workers if worker[0]==new_host[0])][0])
            #deduct replica cpu requirement
            workers[index][3] -= replica_cpu_limits
            #update new_host, particulalrly its capacity
            new_host[3]= workers[index][3]
        logger.info('bin_packing: after deduction: new_hosts: ' + str(new_hosts))
        #set new_function new hosts
        new_function[1] = new_hosts
        if debug: logger.info("scheduler_planner_binpacking: new_hosts for ("
            + new_function[0][0] + "-" + new_function[0][1] + "):\n" + str(new_function[1]))

    #for loop: next new_function
        
    #replacad original functions with new_functions to apply new_hosts (placements)
    #functions = new_functions
    logger.info('scheduler_planner_binpacking: done: functions:\n'
                + '\n'.join([str(new_function) for new_function in new_functions]))
    
    return workers, new_functions


#scheduler_planner_local
def scheduler_planner_local(workers, new_functions, debug):
    global logger
    logger.info("scheduler_planner_local:start")
    #set hosts for new_functions and update workers capacity
    logger.info('scheduler_planner_local:\n available Workers \n'
                + '\n'.join([str(worker) for worker in workers]))
    #PLAN
    #set hosts per function
    for new_function in new_functions:
        #function's owner
        owner = [*(worker for worker in workers if worker[0]==new_function[0][0])][0]
        #func required cpu capacity
        func_required_cpu_capacity = 0
        #exclude 'm'
        replica_cpu_limits = int(new_function[2][3].split('m')[0])
        func_max_replica = new_function[2][1]
        func_required_cpu_capacity = replica_cpu_limits * func_max_replica
        
        #try to fill new hosts for new_function
        new_hosts = []
        
        #place locally
        #how about functions belong to a dead node??? they are still scheduled locally
        for rep in range(func_max_replica):
            new_hosts.append(copy.deepcopy(owner))
                 
        #deduct function cpu requirement from worker's cpu capacity per replica
        for new_host in new_hosts:
            #get selected worker index 
            index = workers.index([*(worker for worker in workers if worker[0]==new_host[0])][0])
            #deduct replica cpu requirement
            workers[index][3] -= replica_cpu_limits
            #apply worker's updated capacity to new_host as well
            new_host[3]= workers[index][3]  

        #set new_function new hosts
        new_function[1] = new_hosts
        if debug: logger.info("scheduler_planner_local: new_hosts for ("
            + new_function[0][0] + "-" + new_function[0][1] + "):\n" + str(new_function[1]))
    #for loop: next new_function
        
    logger.info('scheduler_planner_local: all done: functions:\n'
                + '\n'.join([str(new_function) for new_function in new_functions]))
    
    return workers, new_functions

#scheduler_planner_default
#provide all nodes for each function scheduling. Kubenretes does it by nodes' performance, only once.
#If a node is under pressure, kubernetes is free to reschedule any time.
def scheduler_planner_default(workers, new_functions, debug):
    global logger
    logger.info("scheduler_planner_default:start")
    #set hosts for new_functions and update workers capacity
    logger.info('scheduler_planner_default:\n available Workers \n'
                + '\n'.join([str(worker) for worker in workers]))
    #PLAN
    #set hosts per function
    for new_function in new_functions:
        #function's owner
        owner = [*(worker for worker in workers if worker[0]==new_function[0][0])][0]
        #func required cpu capacity
        func_required_cpu_capacity = 0
        #exclude 'm'
        replica_cpu_limits = int(new_function[2][3].split('m')[0])
        func_max_replica = new_function[2][1]
        func_required_cpu_capacity = replica_cpu_limits * func_max_replica
        
        #try to fill new hosts for new_function
        new_hosts = []
        
        #place anywhere you like Kubernetes
        #how about functions belong to a dead node??? they are still scheduled
        for worker in workers:
            new_hosts.append(copy.deepcopy(worker))
                 
        #deduct function cpu requirement from worker's cpu capacity per replica
        for new_host in new_hosts:
            #get selected worker index 
            index = workers.index([*(worker for worker in workers if worker[0]==new_host[0])][0])
            #deduct replica cpu requirement
            workers[index][3] -= replica_cpu_limits
            #apply worker's updated capacity to new_host as well
            new_host[3]= workers[index][3]  

        #set new_function new hosts
        new_function[1] = new_hosts
        if debug: logger.info("scheduler_planner_default: new_hosts for ("
            + new_function[0][0] + "-" + new_function[0][1] + "):\n" + str(new_function[1]))

    #for loop: next new_function
        
    logger.info('scheduler_planner_default: all done: functions:\n'
                + '\n'.join([str(new_function) for new_function in new_functions]))
    
    return workers, new_functions

#scheduler_planner_random
def scheduler_planner_random(workers, new_functions, debug):
    global logger
    logger.info("scheduler_planner_random:start")
    #set hosts for new_functions and update workers capacity
    logger.info('scheduler_planner_random:\n available Workers \n'
                + '\n'.join([str(worker) for worker in workers]))
    #PLAN
    #set hosts per function
    for new_function in new_functions:
        #function's owner
        owner = [*(worker for worker in workers if worker[0]==new_function[0][0])][0]
        #func required cpu capacity
        func_required_cpu_capacity = 0
        #exclude 'm'
        replica_cpu_limits = int(new_function[2][3].split('m')[0])
        func_max_replica = new_function[2][1]
        func_required_cpu_capacity = replica_cpu_limits * func_max_replica
        
        #try to fill new hosts for new_function
        new_hosts = []
        
        #place on a random node that has capacity
        #how about functions belong to a dead node??? they are still scheduled
        random_places = []
        while random_places == []:
            random_index = random.randint(0, len(workers)-1) #0 to 5
            #has enough capacity for all function replicas?
            if workers[random_index][3] >= func_required_cpu_capacity:
                #set place
                for rep in range(func_max_replica):
                    random_places.append(copy.deepcopy(workers[random_index]))

        new_hosts = random_places
                 
        #deduct function cpu requirement from worker's cpu capacity per replica
        for new_host in new_hosts:
            #get selected worker index 
            index = workers.index([*(worker for worker in workers if worker[0]==new_host[0])][0])
            #deduct replica cpu requirement
            workers[index][3] -= replica_cpu_limits
            #apply worker's updated capacity to new_host as well
            new_host[3]= workers[index][3]  

        #set new_function new hosts
        new_function[1] = new_hosts
        if debug: logger.info("scheduler_planner_random: new_hosts for ("
            + new_function[0][0] + "-" + new_function[0][1] + "):\n" + str(new_function[1]))
    #for loop: next new_function
        
    logger.info('scheduler_planner_random: all done: functions:\n'
                + '\n'.join([str(new_function) for new_function in new_functions]))
    
    return workers, new_functions


#scheduler_monitor
def scheduler_monitor(workers, node_role):
    global logger
    logger.info("scheduler_monitor: start")
    #MONITOR
    #Update SoC
    for worker in workers:
        ip=worker[1]
        success=False
        #retry
        while success == False:
            try:
                logger.info('scheduler_monitor: Soc req.: ' + worker[0])
                response=requests.get('http://' + ip + ':5000/pi_service/charge/'
                                      + node_role, timeout = 10)
            except Exception as e:
                logger.error('scheduler_monitor:request failed for ' + worker[0] + ":" + str(e))
                time.sleep(1)
            else:
                soc=round(float(response.text),2)
                index=workers.index(worker)
                workers[index][2]=soc
                logger.info('scheduler_monitor: Soc recv.: ' + worker[0] + ":" + str(soc) + "mWh")
                success=True
            
    logger.info('scheduler_monitor:\n' + '\n'.join([str(worker) for worker in workers]))
    logger.info("scheduler_monitor:done")
    return workers

#set initial workers and functions
def initialize_workers_and_functions(nodes, workers, functions, battery_cfg, nodes_plan, zones):
    global logger
    logger.info("initialize_workers_and_functions: start")
    #Set Workers & Functions
    for node in nodes:
        #worker = [name, ip, soc, capacity, zone]
        position = node[0]
        name = node[1]
        ip= node[2]
        soc= battery_cfg[3]#set current SoC
        capacity=nodes_plan[name]["max_cpu_capacity"] #set capacity as full
        #set zone
        battery_max_cap = battery_cfg[1]
        soc_percent = round(soc / battery_max_cap * 100)
        zone = [*(zone[1] for zone in zones if soc_percent <= zone[2] and soc_percent > zone[3])][0]
        #if node is involved in this tests
        if position == "PEER":
            #add worker
            worker =[name,ip, soc, capacity, zone]
            workers.append(worker)
            
            #add functions
            apps=nodes_plan[name]["apps"]
            for app in apps:
                if app[1]==True:
                    #function = [identity, hosts[], func_info, profile]
                    #set identity
                    worker_name=worker[0]
                    app_name=app[0]
                    identity = [worker_name, app_name]
                    #set hosts
                    hosts=[]
                    #set function info
                    func_info=app[8]
                    #create and set profile name in function info
                    func_info[13]=worker_name + '-' + app_name
                    #set profile
                    profile = app[9]
                    
                    function=[]
                    
                    #set local host per replicas and deduct cpu capacity from node
                    max_replica = func_info[1]
                    for rep in range (max_replica): 
                        #update host capacity
                        replica_cpu_limits = func_info[3]
                        #exclude 'm'
                        replica_cpu_limits = int(replica_cpu_limits.split('m')[0])
                        index=workers.index(worker)
                        workers[index][3]-=replica_cpu_limits
                        
                        #set host: default is local placement
                        hosts.append(worker)
                    #end for rep

                    #add function   
                    function = [identity, hosts, func_info, profile]
                    functions.append(function)
                    f_name= function[0][0]+ '-'+function[0][1]
            #end for app
    #end for node
    logger.info("initialize_workers_and_functions:stop")
    return workers, functions

#executor :set functions' profile using hosts, apply helm charts
def scheduler_executor(functions, profile_chart, profile_creation_roll_out,
                       function_chart, scheduling_round, log_path, scheduler_name, workers, debug):
    #1 set profile based on hosts= set function[3] by new updates on function[1]
    logger.info('scheduler_executor:start')
    logger.info("scheduler_executor:set_profile per function")
    duration = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    for function in functions:
        #if debug: logger.info('scheduler_executor: set_profile:before:\n' + str(function[3]))
        #get old profile
        old_profile=copy.deepcopy(function[3])
        
        #translate hosts and map them to profile and set new profile scheme
        function[3]=scheduler_executor_set_profile(function, scheduler_name, workers, debug)
        #compare profiles, profile = function[3] looks like this ["w1", "nothing", "nothing",....]
        if old_profile != function[3]:
            #if profile is changed, set version to force re-schedule function based on new profile config
            function[2][14] +=1
            logger.info('scheduler_executor: ' + str(function[0][0]) + '-' + str(function[0][1])
                        + ': version = ' + str(function[2][14]))

        #if debug: logger.info('scheduler_executor: set_profile:after:\n' + str(function[3]))
    #all new profiles
    logger.info('scheduler_executor: All new profiles \n'
        + '\n'.join([str(str(function[0]) + '--->'
        + str(function[3])) for function in functions]))
    #2 apply the new scheduling for functions by helm chart
    #if no change is profile happend, no re-scheduling is affected
    logger.info("scheduler_executor:apply all: call")
    scheduler_executor_apply(functions, profile_chart, profile_creation_roll_out,
                             function_chart, scheduling_round, log_path,
                             setup.auto_scaling, setup.auto_scaling_factor)
        
    duration= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp() - duration
    logger.info('scheduler_executor: done in ' + str(int(duration)) + 'sec')
    
    return functions


#offload 
def offloader(workers, functions, volunteers, new_function, sticky,stickiness, old_hosts,
    warm_scheduler,owner, func_max_replica,func_required_cpu_capacity, scale_to_zero, debug):
    
    global logger
    logger.info("offloader: start: " + str(new_function[0][0] +'-' + new_function[0][1]))
    new_hosts = []
    #??? assume that all replicas are always placed on 1 node
    #if sticky enabled and function was offloaded last time
    if owner[0] != old_hosts[0][0] and sticky:
        new_hosts = sticky_offloader(workers, functions, volunteers, stickiness, old_hosts,
                                     owner, func_max_replica,func_required_cpu_capacity,
                                     warm_scheduler, scale_to_zero)
    else:
        logger.info('offloader: skip sticky_offloader')
    #if sticky unsuccessful
    if new_hosts == []:
        #iterate over rich and vulnerables, already sorted by SoC (large -> small)
        for volunteer in volunteers:
            #if function belongs to a poor node
            if owner[4] == 2:
                if debug: logger.info('offloader: poor function')
                #if node is in rich zone
                volunteer_zone = volunteer[4]
                if volunteer_zone == 1:
                    if debug: logger.info('offloader: rich volunteer (' + volunteer[0] + ')')
                    #if enough capacity on volunteer node is available
                    if volunteer[3] >= func_required_cpu_capacity:
                        if debug: logger.info('offloader: rich volunteer has capacity')
                        #place this poor function on this rich volunteer per replica
                        for rep in range(func_max_replica):
                            new_hosts.append(copy.deepcopy(volunteer))
                            #volunteer capacity is deducted later on in main algorithm
                        return new_hosts
                    else:
                        if debug: logger.info('offloader: rich volunteer has NOT capacity')
                #OR volunteer node is in vulnerable zone
                if volunteer_zone == 3:
                    if debug: logger.info('offloader: vulnerable volunteer (' + volunteer[0] + ')')
                    #evaluate cpu reservation for the vulnerable node own functions
                    reserved_capacity = 0
                    available_capacity = 0
                    for function in functions:
                        #if function belongs to this vulnerable volunteer node
                        if function[0][0] == volunteer[0]:
                            #caclulate reserved cpu capacity per replica for the function
                            reserved_capacity += function[2][1] * int(function[2][3].split('m')[0])
                    #if already one has offloaded on this, that one is also included here as volunteer[3] is the result of full capacity minus offloaded (end of each offloading this is deducted)
                    available_capacity = volunteer[3] - reserved_capacity
                    
                    #if volunteer has enough cpu capacity, considering reservation
                    if available_capacity >= func_required_cpu_capacity:
                        if debug: logger.info('offloader: vulnerable volunteer has capacity + reservation')
                        #place functions belong to a poor node on volunteer per replica
                        for rep in range(func_max_replica):
                            new_hosts.append(copy.deepcopy(volunteer))
                        return new_hosts
                    else:
                        if debug: logger.info('offloader: vulnerable volunteer has NOT capacity + reservation')
            #if function belongs to a vulnerable zone    
            elif owner[4] == 3:
                if debug: logger.info('offloader: vulnerable function')
                #only if volunteer is in rich zone
                if volunteer[4] == 1:
                    if debug: logger.info('offloader: volunteer node\'s zone is rich (' + volunteer[0] + ')')
                    #and volunteer has cpu capacity for function
                    if volunteer[3] >= func_required_cpu_capacity:
                        logger.info('offloader: volunteer rich has capacity')
                        for rep in range(func_max_replica):
                            new_hosts.append(copy.deepcopy(volunteer))
                        return new_hosts
                    else:
                        if debug: logger.info('offloader: volunteer rich has NOT capacity')
                else:
                    if debug: logger.info('offloader: volunteer node\'s zone is NOT rich')
            #if function belongs to a dead node
            elif owner[4] == 4:
                if debug: logger.info('offloader: dead function')
                #if warm_scheduler on, otherwise functions belong to dead nodes are just placed locally
                if warm_scheduler == True:
                    if debug: logger.info('offloader: warm scheduler is True')
                    # if volunteer is in rich zone
                    if volunteer[4] == 1:
                        if debug: logger.info('offloader: rich volunteer (' + volunteer[0] + ')')
                        #if volunteer has cpu capacity
                        if volunteer[3] >= func_required_cpu_capacity:
                            if debug: logger.info('offloader: rich volunteer has capacity')
                            for rep in range(func_max_replica):
                                new_hosts.append(copy.deepcopy(volunteer))
                            return new_hosts
                        else:
                            if debug: logger.info('offloader: rich volunteer has NOT capacity')
                    else:
                        if debug: logger.info('offloader: volunteer is NOT rich (' + volunteer[0] + ')')
                        
                    #or not exist any rich and all volunteers are just vulnerable
                    rich_nodes = [*(worker for worker in workers if worker[4]==1)]
                    if len(rich_nodes)==0:
                        if debug: logger.info('offloader: not exist any rich node and all volunteers are vulnerable')
                        #if volunteer has cpu capacity
                        if volunteer[3] >= func_required_cpu_capacity:
                            if debug: logger.info('offloader: vulnerable volunteer has capacity')
                            for rep in range(func_max_replica):
                                new_hosts.append(copy.deepcopy(volunteer))
                            return new_hosts
                        #if no cpu capacity, if scale to zero on, do it ????
                        elif setup.scale_to_zero == True:
                            pass
                        else:
                            if debug: logger.info('offloader: vulnerable volunteer has NOT capacity')
                    else:
                        if debug: logger.info('offloader: unlukily, exist rich volunteer')
                else:
                    if debug: logger.info('offloader: warm scheduler is False')
        #end for volunteer
        if len(volunteers)==0:
            logger.info('offloader: skip offloading, no volunteer found')
            
    logger.info("offloader: done: " + str(new_function[0][0] +'-' + new_function[0][1])
                + ": new_hosts:\n"+ str(new_hosts) if new_hosts != [] else ": [ ]")                   
    return new_hosts

#sticky offloader   
def sticky_offloader(workers, functions, volunteers, stickiness, old_hosts, owner,
                     func_max_replica,func_required_cpu_capacity, warm_scheduler, scale_to_zero):

    global logger
    logger.info('sticky_offloader: start')
    new_hosts = []
    logger.info('sticky_offloader: old_hosts: ' + str(old_hosts))
    #apply sticky only if all replicas of the functions have been scheduled on only 1 zone???? how about per replica evaluation and letting each replica sticks to its last place
    old_hosts_zone = [host[4] for host in old_hosts]
    old_hosts_zone_set = list(set(old_hosts_zone))
    if len(old_hosts_zone_set) > 1:
        logger.error('sticky_offloader: all replicas are NOT on 1 node')
        logger.info('sticky_offloader: done' + str(new_hosts))
        return new_hosts
    
    logger.info('sticky_offloader: get best option')
    #Get best option for offloading, regardless of sticky
    #nodes (rich and vulnerable) already sorted by suitability
    best_option = []
    for volunteer in volunteers:
        #if function belongs to a poor node, and volunteer node is in vulnerable zone,
        #then because of undecided functions belonging to the node, consider node's own reservation
        available_capacity = 0
        if owner[4] == 2 and volunteer[4] == 3:
            #consider reservation to evaluate volunteer capacity
            #evaluate cpu reservation for the vulnerable node own functions
            reserved_capacity = 0
            
            for function in functions:
                #if function belongs to the volunteer node that is a vulnerable node
                if function[0][0] == volunteer[0]:
                    #caclulate reserved cpu capacity per replica for the function
                    reserved_capacity += function[2][1] * int(function[2][3].split('m')[0])
            #Note:if already one has offloaded on this, that one is also included here as volunteer[3] is the result of full capacity minus offloaded (end of each offloading this is deducted)
            available_capacity = volunteer[3] - reserved_capacity
        else:
            available_capacity = volunteer[3]
        #if node has capacity
        if available_capacity >= func_required_cpu_capacity:
            best_option = volunteer
            #the first answer, is the best option, do not continue
            break
    #end for
    logger.info('sticky_offloader: best option: ' + str(best_option))
    
    if best_option == []:
        logger.error('sticky_offloader: not a best option found, return null to offloader')
        logger.info('sticky_offloader: done' + str(new_hosts))
        return new_hosts
    
    #if old location of function (belonging to poor, vulnerable or (dead if warm is true)) is rich
    if old_hosts_zone[0] == 1:
        logger.info('sticky_offloader: old_host is rich')
        #if old node soc satisfies stickiness
        old_option_soc = old_hosts[0][2] 
        best_option_soc = best_option[2]
        if old_option_soc >= (best_option_soc - (best_option_soc * stickiness)):
            logger.info('sticky_offloader: old_host_soc satisfy stickiness')
            #if old has capacity
            if old_hosts[0][3] >= func_required_cpu_capacity:
                logger.info('sticky_offloader: old_host has capacity')
                new_hosts =copy.deepcopy(old_hosts)
                #function requried cpu is later deducted from the node capacity in main algorithm
                logger.info('sticky_offloader: done' + str(new_hosts))
                return new_hosts
            #old has no capacity, but if f belongs to a dead node, place and scale to 0 even if no resource
            elif owner[4] == 4:
                #if scale to zero on ???
                if scale_to_zero == True:
                    logger.info('sticky_offloader: old_host NOT capacity, but func is dead and scale_to_zero is on')
                    #??? it can be limited to only 1 zero function per node: if not exist any 0 already on this node
                    new_hosts = copy.deepcopy(old_hosts)
                    logger.info('sticky_offloader: done' + str(new_hosts))
                    return new_hosts
            else:
                logger.info('sticky_offloader: old_hosts has NOT capacity (or NOT a dead func + scale_to_zero=True)\n'
                            + 'func capacity = ' + str(func_required_cpu_capacity)
                            + ' old_host capacity= ' + str(old_hosts[0][3]))
        else:
            logger.info('sticky_offloader: old_host_soc NOT satisfy stickiness')
    #if old host is vulnerable and function belongs to a poor or dead node
    elif old_hosts_zone[0] == 3 and (owner[4]== 2 or owner[4] ==4):
        logger.info('sticky_offloader: old_host is vulnerable and func belongs to poor or dead node')
        #evaluate cpu reservation for the vulnerable node functions itself
        reserved_capacity = 0
        available_capacity = 0
        for function in functions:
            #if node name in function is equal to the old_host name, it is its local func
            if function[0][0] == old_hosts[0][0]:
                #caclulate reserved cpu capacity per replica for the function
                reserved_capacity += function[2][1] * int(function[2][3].split('m')[0])
        
        available_capacity = old_hosts[0][3] - reserved_capacity
            
        #if f belongs to a poor node and (no rich node exists || all are filled)
        #skip this part: and (best_option[4] != 1)
        if owner[4]==2 :
            logger.info('sticky_offloader: func belong to poor skipped(and (no rich or all riches are filled)')
            #if old host can satisfy stickiness, stick it
            #check stickiness
            old_option_soc = old_hosts[0][2] 
            best_option_soc = best_option[2]
            if old_option_soc >= (best_option_soc - (best_option_soc * stickiness)):
                logger.info('sticky_offloader: satisfy stickiness')
                #if old has capacity
                if available_capacity >= func_required_cpu_capacity:
                    logger.info('sticky_offloader: has capacity')
                    new_hosts =copy.deepcopy(old_hosts)
                    logger.info('sticky_offloader: done' + str(new_hosts))
                    return new_hosts
                else:
                    logger.info('sticky_offloader: has NOT capacity')
            else:
                logger.info('sticky_offloader: NOT satisfy stickiness')
        #OR if f belongs to a dead node & warm & no rich node exists
        elif (owner[4]==4 and warm_scheduler ==True and
            (len([*(worker for worker in workers if worker[4]==1)])==0)):
            logger.info('sticky_offloader: func belong to dead node and no rich node exist')
            #if enough capacity
            if available_capacity >= func_required_cpu_capacity:
                logger.info('sticky_offloader: has capacity')
                new_hosts=copy.deepcopy(old_hosts)
                logger.info('sticky_offloader: done' + str(new_hosts))
                return new_hosts
            else:
                logger.info('sticky_offloader: has NOT capacity')
            #if does not exist a dead already placed somewhere with scale to zero ???
            #else:
        else:
            logger.info('sticky: not happened: not being: \n'
            + 'f belongs to a poor node and (no rich node exists || all are filled)\n'
            + ' OR f belongs to a dead node & no rich node exists')
    logger.info('sticky_offloader: done' + str(new_hosts))           
    
    return new_hosts

#set ptofile
#it only works for 5 nodes and 3 replica???
def scheduler_executor_set_profile(function, scheduler_name, workers, debug):
    global logger
    nodeAffinity_required_filter1= "unknown"
    nodeAffinity_required_filter2 = "unknown"
    nodeAffinity_required_filter3 = "unknown"
    nodeAffinity_required_filter4 = "unknown"
    nodeAffinity_required_filter5 = "unknown"
    nodeAffinity_preferred_sort1 = "unknown"
    podAntiAffinity_preferred_functionName = "unknown"
    podAntiAffinity_required_functionName = "unknown"
    
    owner_name = function[0][0]
    app_name = function[0][1]
    function_name= owner_name + '-' + app_name
    hosts= function[1]
    #if debug: logger.info("scheduler_executor_set_profile:" + function_name + ":start")
    selected_nodes=[]
    for host in hosts:
        selected_nodes.append(host[0])
    #if selected_nodes=[w1,w2,w2] then selected_nodes_set result is [w1, w2]
    selected_nodes_set=list(set(selected_nodes))
    
    if ("greedy" in scheduler_name or
        "local" in scheduler_name or
        "random" in scheduler_name or
        "bin-packing" in scheduler_name):
        
        #place on 1 node #random is always 1
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
            logger.error('scheduler_set_profile:' + function_name + ': selected_nodes_set length = '
                         +str(len(selected_nodes_set)))
    #default-kubernetes scheduler
    elif "default" in scheduler_name:
        if len(selected_nodes_set) == len(workers):
            if len(selected_nodes_set)==4: #t????emporary code, both if else should be merged
                nodeAffinity_required_filter1 = selected_nodes_set[0]
                nodeAffinity_required_filter2 = selected_nodes_set[1]
                nodeAffinity_required_filter3 = selected_nodes_set[2]
                nodeAffinity_required_filter4 = selected_nodes_set[3]
                
            elif len(selected_nodes_set)==5: #????temporary code
                nodeAffinity_required_filter1 = selected_nodes_set[0]
                nodeAffinity_required_filter2 = selected_nodes_set[1]
                nodeAffinity_required_filter3 = selected_nodes_set[2]
                nodeAffinity_required_filter4 = selected_nodes_set[3]
                nodeAffinity_required_filter5 = selected_nodes_set[4]
        else:
            logger.error('scheduler_set_profile: not all workers are selected: (len=='
                         + str(len(selected_nodes_set)) + ')')
    else:
        logger.error('scheduler_set_profile: scheduler_name not found:' + scheduler_name)
            
    #if debug: logger.info("scheduler_executor_set_profile:" + function_name + ":done")
    #return
    return [nodeAffinity_required_filter1,
            nodeAffinity_required_filter2,
            nodeAffinity_required_filter3,
            nodeAffinity_required_filter4,
            nodeAffinity_required_filter5,
            nodeAffinity_preferred_sort1,
            podAntiAffinity_preferred_functionName,
            podAntiAffinity_required_functionName]

# scheduler_executor_apply   
def scheduler_executor_apply(functions, profile_chart, profile_creation_roll_out,
                             function_chart, scheduling_round, log_path,
                             auto_scaling, auto_scaling_factor):
    global logger
    logger.info('scheduler_executor_apply:start')
    logger.info('scheduler_executor_apply:profiles:start')
    prof_group = len(functions)
    
    #profile string
    prof_name=[]
    nodeAffinity_required_filter1=[]
    nodeAffinity_required_filter2=[]
    nodeAffinity_required_filter3=[]
    nodeAffinity_required_filter4=[]
    nodeAffinity_required_filter5=[]
    nodeAffinity_preferred_sort1=[]
    podAntiAffinity_preferred_functionName=[]
    podAntiAffinity_required_functionName=[]
    #get profiles
    for i in range (len(functions)):
        
        function = functions[i]
        prof_name.append(function[0][0] + '-' + function[0][1])
        profile = function[3]
        
        nodeAffinity_required_filter1.append(profile[0])
        nodeAffinity_required_filter2.append(profile[1])
        nodeAffinity_required_filter3.append(profile[2])
        nodeAffinity_required_filter4.append(profile[3])
        nodeAffinity_required_filter5.append(profile[4])
        nodeAffinity_preferred_sort1.append(profile[5])
        podAntiAffinity_preferred_functionName.append(profile[6])
        podAntiAffinity_required_functionName.append(profile[7])
    #run command
    helm_chart_name = profile_chart[0]
    helm_chart_path = profile_chart [1]
    
    cmd = ("helm upgrade --install " + helm_chart_name  + " " + helm_chart_path
    + " --wait --set-string \"profiles=" + str(prof_group) +","
    + "profile.name={" + ','.join(prof_name) + "},"
    + "profile.nodeAffinity.required.filter1={" + ','.join(nodeAffinity_required_filter1) + "},"
    + "profile.nodeAffinity.required.filter2={" + ','.join(nodeAffinity_required_filter2) + "},"
    + "profile.nodeAffinity.required.filter3={" + ','.join(nodeAffinity_required_filter3) + "},"
    + "profile.nodeAffinity.required.filter4={" + ','.join(nodeAffinity_required_filter4) + "},"
    + "profile.nodeAffinity.required.filter5={" + ','.join(nodeAffinity_required_filter5) + "},"
    + "profile.nodeAffinity.preferred.sort1={" + ','.join(nodeAffinity_preferred_sort1) + "},"
    + "profile.podAntiAffinity.preferred.functionName={" + ','.join(podAntiAffinity_preferred_functionName) + "},"
    + "profile.podAntiAffinity.required.functionName={" + ','.join(podAntiAffinity_required_functionName) + "}\""
    + " --skip-crds --wait")
    
    logger.info('scheduler_executor_apply:profiles:run cmd')
    #log
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    path = log_path + "/helm-commands"
    if not os.path.exists(path):
        os.makedirs(path)
    file_name = path + "/" + str(scheduling_round) + "_profiles.sim.cmd.log"
    log_cmd = cmd + " --dry-run > " + file_name
    logger.info('scheduler_executor_apply:log_cmd:profile:' + log_cmd)
    os.system(log_cmd)
    
    #actual cmd
    logger.info('scheduler_executor_apply:cmd:profile:' + cmd)
    out= os.system(cmd)
    logger.info('scheduler_executor_apply:cmd:profile:stdout:' + (str(out)))
    #wait to apply
    logger.info('scheduler_executor_apply:cmd:profile:rolling out (' + str(profile_creation_roll_out) + 's)')
    time.sleep(profile_creation_roll_out)
    logger.info('scheduler_executor_apply:profiles:done')
    
    #Functions Helm CHart
    #Get Functions String
    logger.info('scheduler_executor_apply:functions:start')
    func_group=len(functions)
    func_name = []
    func_image_name = []
    counter = []
    redisServerIp=[]
    redisServerPort=[]
    readTimeout = []
    writeTimeout = []
    execTimeout = []
    handlerWaitDuration = []
    scale_factor = []
    scale_min =[]
    scale_max = []
    requests_cpu = []
    limits_cpu = []
    profile_names = []
    queue_names = []
    linkerd = []
    version = []
    #get func_info
    for i in range (len(functions)):
        function = functions[i]
        #function name
        name = function[0][0] + "-" + function[0][1]
        func_name.append(name)
        #image
        func_image_name.append(function[0][1])
        
        #info
        func_info = function[2]
        
        scale_min.append(str(func_info[0]))
        scale_max.append(str(func_info[1]))
        #factor is unused and not mentioned in setup for apps????
        scale_factor.append("0" if auto_scaling is "hpa" else str(auto_scaling_factor))
        requests_cpu.append(func_info[2])
        limits_cpu.append(func_info[3])
        counter.append(func_info[4])
        redisServerIp.append(func_info[5])
        redisServerPort.append(func_info[6])
        readTimeout.append(func_info[7])
        writeTimeout.append(func_info[8])
        execTimeout.append(func_info[9])
        handlerWaitDuration.append(func_info[10])
        linkerd.append(func_info[11])
        queue_names.append(func_info[12])
        profile_names.append(func_info[13])
        version.append(func_info[14])

    #run command
    logger.info('scheduler_executor_apply:functions:cmd')
    helm_chart_name = function_chart[0]
    helm_chart_path = function_chart [1]
    cmd =("helm upgrade --install " + helm_chart_name + " " + helm_chart_path
          + " --set-string \"functions=" + str(func_group) + ","
          + "function.name={" + ','.join(func_name) + "},"
          + "function.imageName={" + ','.join(func_image_name) + "},"
          + "function.env.counter={" + ','.join(counter) + "},"
          + "function.env.redisServerIp={" + ','.join(redisServerIp) + "},"
          + "function.env.redisServerPort={" + ','.join(redisServerPort) + "},"
          + "function.env.execTimeout={" + ','.join(execTimeout) + "},"
          + "function.env.handlerWaitDuration={" + ','.join(handlerWaitDuration) + "},"
          + "function.env.readTimeout={" + ','.join(readTimeout) + "},"
          + "function.env.writeTimeout={" + ','.join(writeTimeout) + "},"
          + "function.scale.factor={" + ','.join(scale_factor) + "},"
          + "function.scale.min={" + ','.join(scale_min) + "},"
          + "function.scale.max={" + ','.join(scale_max) + "},"
          + "function.requests.cpu={" + ','.join(requests_cpu) + "},"
          + "function.limits.cpu={" + ','.join(limits_cpu) + "},"
          + "function.annotations.profile={" + ','.join(profile_names) + "},"
          + "function.annotations.queue={" + ','.join(queue_names) + "},"
          + "function.annotations.linkerd={" + ','.join(linkerd) + "},"
          + "function.env.version={" + ','.join([str(i) for i in version]) + "}\""
          + " --skip-crds --wait")
    
    #log
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    path = log_path + "/helm-commands"
    if not os.path.exists(path):
        os.makedirs(path)
    file_name = path + "/" + str(scheduling_round) + "_functions.sim.cmd.log"
    log_cmd = cmd + " --dry-run > " + file_name 
    logger.info('scheduler_executor_apply:log_cmd:functions:' + log_cmd)
    os.system(log_cmd)
    
    #actual cmd
    logger.info('scheduler_executor_apply:cmd:function:' + cmd)
    out = os.system(cmd)
    logger.info('scheduler_executor_apply:cmd:function:stdout:' + str(out))
    logger.info('scheduler_executor_apply:functions:done')
    
    logger.info('scheduler_executor_apply:stop')
       
@app.route('/workload', methods=['POST'])
def workload(my_app):
    time.sleep(1)  # Give enough time gap to create req to server to avoid connection error. or use sessions
    global logger
    global test_started
    global test_finished
    global apps
    global max_request_timeout
    global min_request_generation_interval
    logger.info('workload: started')
#[2] w type: "static" or "poisson" or "exponential-poisson"
#[3] workload: [[0]iteration [1]interval/exponential lambda(10=avg 8s)
                #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
#[4] func_name [5] func_data [6] created [7] recv
    
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
        if lmd_rate!=0:
            concurrently = np.random.poisson(lam=lmd_rate, size=iteration)
        else:#force 0, if lambda is 0
            concurrently = [0]*iteration
    elif workload_type == 'exponential-poisson':
        iteration = w_config[0]
        #interval
        #set seed
        seed = w_config[3]
        np.random.seed(seed)
        
        lmd_scale = w_config[1]
        if lmd_scale !=0:
            #random.exponential(scale=1.0, size=None)
            interval = np.random.exponential(scale=lmd_scale, size=iteration)
        else: #force 0, if lambda is 0
            interval = [0]*iteration
            
        #concurrently
        lmd_rate = w_config[2]
        if lmd_rate!=0:
            concurrently = np.random.poisson(lam=lmd_rate, size=iteration)
        else: #force 0 if lambda is 0
            concurrently = [0]*iteration
    elif workload_type == 'exponential': #dynamic interval, static concurrently
        iteration = w_config[0]
        #interval
        #set seed
        seed = w_config[3]
        np.random.seed(seed)
        
        lmd_scale = w_config[1]
        if lmd_scale!=0:
            #random.exponential(scale=1.0, size=None)
            interval = np.random.exponential(scale=lmd_scale, size=iteration)
        else: #force 0 if lambda is 0
            interval = [0]*iteration
            
        concurrently=w_config[2]
        
    func_name = my_app[4]
    func_data = my_app[5]
    #my_app[6] sensor created counter
    #my_app[7] actuation recv counter
    
    
    
    logger.info("workload: App {0} \n workload: {1} \n Iteration: {2} \n "
                "Interval Avg. {3} ({4}-{5}) \n"
                "Concurrently Avg. {6} ({7}--{8})\n"
                " Seed {9} \n function {10} data {11}\n---------------------------".format(
        func_name, workload_type, iteration,
        sum(interval)/len(interval) if "exponential" in workload_type else interval,
        min(interval) if "exponential" in workload_type else "--",
        max(interval) if "exponential" in workload_type else "--",
        sum(concurrently)/len(concurrently) if "poisson" in workload_type else concurrently,
        min(concurrently) if "poisson" in workload_type else "--",
        max(concurrently) if "poisson" in workload_type else "--",
        seed, func_name, func_data))
    
    generator_st = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()    
    #sensor counter
    created = 0
    #iterations
    for i in range(iteration):
        iter_started = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        
        #interarrival
        interarrival = (interval[i] if "exponential" in workload_type else interval)
        if interarrival < min_request_generation_interval:
            interarrival = min_request_generation_interval
            
        threads = []
        
        #concurrently
        con = (concurrently[i] if "poisson" in workload_type else concurrently)
        for c in range (con):
            created +=1
            thread_create_sensor = threading.Thread(target= create_sensor, args=(created,func_name, func_data, interarrival,))
            thread_create_sensor.name = "create_sensor" + "-" + func_name + "#" + str(created)
            threads.append(thread_create_sensor)
        
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
            logger.error('Workload: Iteration #' + str(i)
                + ' overlapped! (' + str(iter_elapsed) + ' elapsed) - next interval= ' + str(interarrival))
            print('Workload Iteration #' + str(i) + ' overlapped!')
            #???skip next intervals that are passed
    #break   
    now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    logger.info('workload: All Generated: ' + func_name +': in ' + str(round(now-test_started,2)) + ' sec')
    
    #set created
    apps[apps.index(my_app)][6] = created
    #????if some are dropped. they are not added to app[7], so this condition is always false
    #wait for all actuators of this app, or for timeout, then move
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: ' + my_app[4] + ' sleep 5 sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(5)
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: func: ' + my_app[4] + ' sleep 10sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(10)
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: func: ' + my_app[4] + ' sleep 15sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(15)
    if apps[apps.index(my_app)][7]< apps[apps.index(my_app)][6]:
        logger.info('workload: func: ' + my_app[4] + ' sleep ' + str(max_request_timeout-30+1) + 'sec: '
            + str(apps[apps.index(my_app)][6]) + ' > ' + str(apps[apps.index(my_app)][7])) 
        time.sleep(max_request_timeout-30+1)
        
    logger.info("Workload: done, func: " + my_app[4] + " created:" + str(my_app[6])
                + " recv:" + str(apps[apps.index(my_app)][7]))
    
    #App workload is finished, call pi_service if timer is not already stopped
    if under_test:
        pi_service('app_done','INTERNAL')
    logger.info('workload: func: ' + my_app[4] + ' stop') 
    return 'workload: Generator done'


def all_apps_done():
    global logger
    global apps
    global sensor_log
    global time_based_termination
    global test_finished # by the last app
    global node_role
    global peers
    global max_request_timeout
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
            #Have you finished creating?
            if app[6] != 0:
                #Have you finished receiving?
                if app[6] == app[7]:
                    #app is done
                    logger.info("all_apps_done: True: Func {0} done, recv {1} of {2}".format(
                        app[4], str(app[7]), str(app[6])))
                else:
                    #receiving in progress
                    logger.info('all_apps_done: False: func ' + app[4] + ' created < recv: ' + str(app[6]) + " < " + str(app[7]))
                    all_apps_done = False
                    break
            else:# creating in progres
                logger.info('all_apps_done:False: func ' + app[4] + ' not set created yet')
                all_apps_done = False
                break

                
    logger.info('all_apps_done: stop: ' +str(all_apps_done))
    return all_apps_done

    
def create_sensor(counter, func_name, func_data,admission_deadline):
    global pics_num
    global pics_folder
    global sensor_log
    global gateway_IP
    global node_IP
    global overlapped_allowed
    global debug
    global battery_cfg
    global sensor_admission_timeout
    global functions
    global boot_up_delay
    
    #one-off sensor
    sample_started = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    try:
        #random image name, pic names must be like "pic_1.jpg"
        n = random.randint(1,pics_num)
        if 'yolo3' in func_name:
            file_name ='pic_' + str(n) + '.jpg'
            file={'image_file': open(pics_folder + file_name, 'rb')}
    
        #create sensor id
        sensor_id= str(sample_started) + '#' + func_name + '-#' + str(counter) 
        #[0] func_name [1]created, [2]submitted/admission-dur, [3]queue-dur, [4]exec-dur,
        #[5] finished, [6]rt, [7] status, [8] repeat
        sensor_log[sensor_id]= [func_name, sample_started, 0, 0, 0, 0, 0, -1, 0]
        
        #drop if no energy on node (in battery sim mode only)
        if battery_cfg[0]==True:
            soc= battery_cfg[3]
            min_battery_charge = battery_cfg[8]
            if soc < min_battery_charge:
                if debug: logger.info('dropped 451 -- dead node')
                #drop and set code to 451
                sensor_log[sensor_id][7]=451
                #skip the rest of the thread
                return None
            #node come back to up, but not ready yet, drop it, except scheduler is warm
            elif (sample_started - battery_cfg[9])< boot_up_delay:
                if debug: logger.info('dropped 452 -- booting up')
                #drop and set code to 452
                sensor_log[sensor_id][7]=452
                #skip the rest of the thread
                return None
            
        # value: Send async req to yolo function along with image_file
        if func_data == 'value':
            #no response is received, just call back is received
            ##
            url = 'http://' + gateway_IP + ':31112/async-function/' + func_name
            header = {'X-Callback-Url':'http://' + node_IP + ':5000/actuator',
                          'Sensor-ID': sensor_id}
            img = (file if 'yolo3' in func_name else None)
            
            json_list = {}
            if 'crop-monitor' in func_name:
                json_list={"user":sensor_id, "temperature":"10", "humidity":"5",
                  "moisture":"3", "luminosity":"1"} 
            elif 'irrigation' in func_name:
                json_list={"user":sensor_id, "temperature":"10", "humidity":"5",
                  "soil_temperature":"3", "water_level":"1", "spatial_location":"1"}
            #send
            response=requests.post(url, headers=header, files=img, json=json_list, timeout=sensor_admission_timeout)

            
        #Pioss: Send the image to Pioss. Then, it notifies the yolo function.
        elif func_data == 'reference':
            url = 'http://' + node_IP + ':5000/pioss/api/write/' + func_name + '/' + file_name
            img = (file if 'yolo3' in func_name else None)
            header ={'Sensor-ID': sensor_id}
            response=requests.post(url, headers=header, timeout=sensor_admission_timeout, files=img)
            #no response is received
            # finished when next operation (sending actual requst to function) is done.
        else: #Minio
            pass
        
        #handle 404 error ?????                                 
        if response.status_code==202 or response.status_code==200:
            
            now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            sample_elapsed = now - sample_started
            if debug: logger.info('submitted (' + str(round(sample_elapsed,2)) + 's)')
            #Set admission duration
            sensor_log[sensor_id][2]= round(sample_elapsed, 2)
            if (sample_elapsed) >= admission_deadline:
                logger.warning('admission overlapped (' + str(sample_elapsed) + 's)')
                if not overlapped_allowed:
                    logger.error('admission overlapped (' + str(sample_elapsed) + 's)')
  
        else:
            logger.error(func_name + '#' + str(counter) +'\n' + str(response.status_code))
    except requests.exceptions.ReadTimeout as ee: 
        logger.error('ReadTimeout:' + func_name + '#' + str(counter) +'\n' + str(ee))                
    except requests.exceptions.RequestException as e:
        logger.error('RequestException:' + func_name + '#' + str(counter) +'\n' + str(e))
    except Exception as eee:
        logger.error('Exception:' + func_name + '#' + str(counter) +'\n' + str(eee))
   
#Pi Object Storage System (Pioss)
# API-level and Method-level route decoration
@app.route('/pioss/api/write/<func_name>/<file_name>', methods=['POST'], endpoint='write_filename')  
@app.route('/pioss/api/read/<func_name>/<file_name>', methods=['GET'], endpoint='read_filename')
def pioss(func_name, file_name):
    global file_storage_folder
    global logger
    global lock
    global gateway_IP
    global sensor_admission_timeout
    global debug
    #write operations
    if request.method == 'POST':
        if debug: logger.info('Pioss Write')
        try:
            with lock:
                try:
                    #get image
                    file = request.files['image_file']
                except:
                    logger.error('pioss: ' + func_name + ': ' + file_Name + ': unable to get')
                try:
                    #download
                    file.save(file_storage_folder + file_name)
                    if debug: logger.info('Pioss: write done - func:' + func_name + ' - ' + file_name)
                except:
                    logger.error('pioss: ' + func_name + ': ' + file_Name + ': unable to download')
                
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
                try:
                    response=requests.post(url, headers=header, timeout=sensor_admission_timeout)
                except:
                    logger.error('pioss: ' + func_name + ': ' + file_Name + ': sending failed')
                #no response is received
                if response.status_code== 200 or response.status_code==202:
                    if debug: logger.info('Pioss: Notification Sent: ' + url)
                else:
                    logger.error('Pioss: Failed')
                return "write&notification done"
        except:
            logger.error('Pioss: write failed')

            
    #read operation
    elif request.method == 'GET':
        if debug: logger.info('Pioss Read')
        #get file
        img = open(file_storage_folder + file_name, 'rb').read()
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
        if debug: logger.info('actuator: '
        + str(request.headers.get('Sensor-Id')) + ' - code: '
        + str(request.headers.get("X-Function-Status")) + ' - '
        + str(round(float(request.headers.get('X-Duration-Seconds')),2)
              if request.headers.get('X-Duration-Seconds') is not None
              and request.headers.get('X-Duration-Seconds') is not "" else "-0.0") + ' s')
        data=request.get_data(as_text=True)       
        
        #print('ID: ' + get_id)
        #id_temp=get_id.split("#")[1]
        #logger.info('Actuator #' + str(actuations) + ' Sensor #'+ id_temp)
        #logger.warning('--------------------------')
        #if debug and 'yolo3' in str(request.headers): logger.warning(str(request.headers))
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
            #if debug: logger.warning('Actuator - Sensor-ID=None| app: ' +request.headers.get("X-Function-Name") + '| code: ' + request.headers.get("X-Function-Status") +' for #' + str(actuations))
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
            sensor_log[get_id][4]= round(float(request.headers.get('X-Duration-Seconds')),3)
            #[5] finished time=now
            now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            sensor_log[get_id][5]= now
            #[6]set response time (round trip)=finished time- created time
            sensor_log[get_id][6]= round(sensor_log[get_id][5]-sensor_log[get_id][1], 3)
            #[3] queuing=response time - admission dur. and execution dur.
            sensor_log[get_id][3]=round(sensor_log[get_id][6]-sensor_log[get_id][2]-sensor_log[get_id][4], 3)
            if sensor_log[get_id][3]<0: sensor_log[get_id][3]=0
            #[7] status code
            sensor_log[get_id][7]=int(request.headers.get('X-Function-Status'))
            #[8] replies
            sensor_log[get_id][8]= sensor_log[get_id][8]+ 1
            #increment received
            c= [index for index, app in enumerate(apps) if app[4] == sensor_log[get_id][0]]
            apps[c[0]][7] +=1
            
            #if repetitious 
            if sensor_log[get_id][8] >1:
                logger.error('Actuator: a repetitious reply received: ' + str(sensor_log[get_id]))
                
    return 'Actuator Sample Done'


#---------------------------------------
def failure_handler():
    global logger
    global sensor_log
    global max_request_timeout
    global failure_handler_interval
    global suspended_replies
    global apps
    global under_test
    logger.info('failure_handler: start')
    #status codes:
    #404: happens in create_sensor: not submitted to gateway as function does not exist (already removed)
    #500: happens after submission: submitted but while executing, function started rescheduling to going down. Partial execution of task can happen here
    #502: happens after submission: submitted but function is in scheduling process and is not up yet
    #502: function timeout (especified in function yaml file)
    #503: gateway timeout (especified in gateway yaml by kubectl edit deploy/gateway -n openfaas
    #note: queue-worker timeout seems ineffective
    #function and gateway have timeout settings.
    wrap_up=max_request_timeout + (failure_handler_interval*2)
    
    while under_test or wrap_up > 0:
        #missed sensors
        missed_sensor_log = {}
        
        now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        #exist suspended replies, set on failed replies in owl_actuator
        if len(suspended_replies) > 0:
            #set missed sensors
            for key, sensor in sensor_log.items():
                #among those with no reply received by code
                if sensor[7]==-1:
                    #make sure it will not receive any reply
                    #and outdated (must have received a timeout reply at least, so it's missed)
                    if sensor[1] + max_request_timeout < now:
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
                        c= [index for index, app in enumerate(apps) if app[4] == missed_sensor[0]]
                        apps[c[0]][7] +=1
                        
                        #removal of the suspended reply
                        suspended_replies.remove(reply)
                        break
        time.sleep(failure_handler_interval)
        
        if not under_test:
            #only first time run
            if wrap_up ==max_request_timeout + (failure_handler_interval*2):
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
    logger.info('start')
    global monitor_interval
    global down_time
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
            response_time_accumulative.append(round(sum(response_time)/len(response_time),3))
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
            power_usage.append(read_power_meter())
        else:
            power_usage.append([-1,-1,-1,-1,-1,-1])
        
        time.sleep(monitor_interval)
        
    
    #close bluetooth connection
    if usb_meter_involved:
        sock.close()
    
    logger.info('done')

def read_power_meter():
    global lock
    global sock
    global logger
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
    
    output=temp
    
    return output

#connect to USB power meter
def usb_meter_connection():
    #python usbmeter --addr 00:15:A5:00:03:E7 --timeout 10 --interval 1 --out /home/pi/logsusb
    global sock
    global logger
    global bluetooth_addr
    sock=None
    addr = bluetooth_addr
    
    connected=False
    
    while True:
        try:
            sock = BluetoothSocket(RFCOMM)
        except Exception as e:
            logger.error(str(e))
            logger.error('Bluetooth driver might not be installed, or python is used instead of ***python3***')
        #sock.settimeout(10)
        try:
            logger.info("usb_meter_connection: Attempting connection...")
            res = sock.connect((addr, 1))
        except btcommon.BluetoothError as e:
            logger.warning("usb_meter_connection: attempt failed: " + str(e))
            connected = False
        except:
            logger.warning("usb_meter_connection: attempt failed2:" + addr)
            connected=False
        else:
            print("Connected OK")
            logger.info('usb_meter_connection: USB Meter Connected Ok (' + addr + ')')
            connected=True
            break
        time.sleep(3)

    #time.sleep(60)
    if connected==False:
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
    global metrics
    global node_name
    global apps
    global test_name
    global log_path
    global test_started
    global test_finished
    global sensor_log
    global node_role
    global snapshot_report
    global throughput
    global throughput2
    global down_time
    global functions
    global workers
    

    test_finished= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
    test_duration = round((test_finished - test_started)/60,0)

    metrics["info"] = {"test_name": test_name,
                       "test_duration": test_duration,
                       "test_started": test_started,
                       "test_finished": test_finished}
    #print logs
    logger.critical('save_reports: Test ' + test_name + ' lasted: '
                    + str(test_duration) + ' min')
    
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
        
        #sensors
        created = 0
        sent = 0
        recv = 0
        for app in apps: #???index based on apps order, in future if apps change, it changes
            if app[1]==True:
                created+=copy.deepcopy(app[6])
                recv+=copy.deepcopy(app[7])
                
        logger.critical('created {} recv {}'.format(created,recv))
        
        #replies
        #actuator/reply counter
        replies_counter = [0]*len(apps)
        #reply status
        replies_status = [[0]*6 for _ in range(len(apps))]#*len(apps) #status code of 200, 500, 502, 503, others
        #dropped sensors per app
        dropped_sensors = [0]*len(apps)
        #dropped due to boot up per app
        dropped_sensors_in_boot_up = [0]*len(apps)
#[0] func_name [1]created, [2]submitted/admission-dur, [3]queue-dur, [4]exec-dur. [5] finished, [6]rt
        sensor_data = []
    
        labels = ['func_name', 'created_at', 'admission', 'queue', 'exec', 'finished_at',
                  'round_trip', 'status', 'replies']
        sensor_data.append(labels)
        
        for sensor in sensor_log.values(): #consider failed ones ?????
            #Get app index
            c= [index for index, app in enumerate(apps) if app[4] == sensor[0]]
            app_index= apps.index(apps[c[0]])
                
            if sensor[7] != 451 and sensor[7] != 452:#dropped (not sent) sensors are not involved in response time and replies
                #time and durations
                admission_duration.append(sensor[2])
                if sensor[7]==200: #only success sensors contribute in response time????? weight of failed ones???
                    creation_time.append(sensor[1])
                    finished_time.append(sensor[5])
                    
                    queuing_duration.append(sensor[3])
                    execution_duration.append(sensor[4])
                    
                    response_time_sens.append(sensor[6])
                
                else:
                    useless_execution_duration.append(sensor[4])
                    
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
                    
                #sent
                sent +=1
                
            #dropped sensor
            else:
                if sensor[7]==451:
                    dropped_sensors[app_index]+=1
                elif sensor[7]==452:
                    dropped_sensors_in_boot_up[app_index]+=1
                else:
                    logger.error('unknown dropped_sensor')
                        
            
            #data list
            sensor_data.append([str(sensor[0]),str(sensor[1]),str(sensor[2]),
                                str(sensor[3]),str(sensor[4]), str(sensor[5]),
                                str(sensor[6]), str(sensor[7]), str(sensor[8])])
        
        #save sensor data
        log_index = log_path + "/" + node_name + "-sensors.csv"
        logger.critical('save_reports: ' + log_index)
        np.savetxt(log_index, sensor_data, delimiter=",", fmt="%s")
        
        
        #PRINT LOGS of METRICS
        logger.critical('METRICS: OVERALL****************************')
        
        #OVERALL created recv by replies (actuators)
        logger.critical('OVERALL: REQ. CREATED: ' +str(created)
        + '     RECV (by apps): ' + str(recv) + '     RECV (by sensor[8] counter): ' + str(sum(replies_counter)) )
        sent_percent = round(sent/created * 100,2) if created>0 else 0
        logger.critical('OVERALL: REQ. SENT: ' +str(sent) + ' (' + str(sent_percent) + ' %)')
        
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
        success_rate = (round((code200/sum([code200,code500,code502,code503,code_1,others]))*100,2)
                        if sum([code200,code500,code502,code503,code_1,others])>0 else 0)
    
        logger.critical("OVERALL: Success Rate (200/sent): {}%".format(success_rate))
        logger.critical("OVERALL: Success Rate (200/sent) new: {}%".format(round(code200/sent * 100,2) if sent>0 else 0))
        logger.critical("OVERALL: {0}{1}{2}{3}{4}{5}".format(
                    'CODE200=' + str(code200) if code200>0 else ' ',
                    ', CODE500=' + str(code500) if code500>0 else ' ',
                    ', CODE502=' + str(code502) if code502>0 else ' ',
                    ', CODE503=' + str(code503) if code503>0 else ' ',
                    ', CODE-1=' + str(code_1) if code_1>0 else ' ',
                    ', OTHERS=' + str(others) if others>0 else ' '))
        
        dropped_sensors_sum = sum(dropped_sensors)
        dropped_sensors_percent = round((sum(dropped_sensors)/created)*100,2) if created >0 else 0
        logger.critical("OVERALL: Dropped Sensors (created, not sent): sum "
                        + str(dropped_sensors_sum) + " --- percent " + str(dropped_sensors_percent) + " %")
        dropped_sensors_in_boot_up_sum = sum(dropped_sensors_in_boot_up)
        dropped_sensors_in_boot_percent = round((sum(dropped_sensors_in_boot_up)/created)*100,2) if created>0 else 0
        logger.critical("OVERALL: Dropped Sensors in boot up (created, not sent): "
            + "sum(" + str(dropped_sensors_in_boot_up_sum) + ") "
            + " --- percent " + str(dropped_sensors_in_boot_percent) + " %")

        
        #OVERALL response time
        admission_duration_avg = round(statistics.mean(admission_duration),2) if len(admission_duration) else 0
        admission_duration_max = round(max(admission_duration),2) if len(admission_duration) else 0
        queuing_duration_avg = round(statistics.mean(queuing_duration),2) if len(queuing_duration) else 0
        queuing_duration_max = round(max(queuing_duration),2) if len(queuing_duration) else 0
        
        execution_duration_avg = round(statistics.mean(execution_duration),2) if len(execution_duration) else 0
        execution_duration_max = round(max(execution_duration),2) if len(execution_duration) else 0
        
        response_time_sens_avg = round(statistics.mean(response_time_sens),2) if len(response_time_sens) else 0
        response_time_sens_max = round(max(response_time_sens),2) if len(response_time_sens) else 0
        
        useless_execution_duration_sum = round(sum(useless_execution_duration)) if len(useless_execution_duration) else 0
        
        logger.critical('OVERALL: avg. Adm. Dur. (sent only)---> ' + str(admission_duration_avg)
                                + '  (max= ' + str(admission_duration_max) + ')')
        logger.critical('OVERALL: avg. Q. Dur. (success only) ---> ' + str(queuing_duration_avg)
                                + '  (max= ' + str(queuing_duration_max) + ')')
        logger.critical('OVERALL: avg. Exec. +(scheduling) Dur. (success only) ---> '
                                + str(execution_duration_avg)
                                + '  (max= ' + str(execution_duration_max) + ')')
        logger.critical('OVERALL: avg. RT (soccess only) ---> ' + str(response_time_sens_avg)
                                + '  (max= ' + str(response_time_sens_max) + ')')
        logger.critical('OVERALL: sum Useless Exec. Dur. ---> ' + str(useless_execution_duration_sum))
        
        
        #Percentile
        percentiles = (np.percentile(response_time_sens, [0, 25, 50, 75, 90, 95, 99, 99.9, 100])if len(response_time_sens) else [0, 0, 0, 0, 0, 0, 0, 0, 0])
        percentiles = ([round(num,3) for num in percentiles])
        logger.critical('OVERALL: Percentiles (success only): ' + str(percentiles))
            
        #Throughput (every 30sec)
        throughput=[]
        throughput2=[]
        timer=test_started + 30
        
        
        while True:
            created_tmp=0
            for time in creation_time:
                if time < timer and time > timer - 30:
                    created_tmp+=1
                    
            finished=0
            for time in finished_time:
                if time < timer and time > timer - 30:
                    finished+=1
                    
            #avoid divided by zero
            if created_tmp==0:
                throughput.append(0)
            else:
                throughput.append((finished/created_tmp) * 100)
            throughput2.append(finished/ 30)
            
            if timer >= (test_finished):
                break
            else:
                timer+=30
        
        throughput_avg = round(statistics.mean(throughput),2) if len(throughput) else 0
        throughput_max = round(max(throughput),2) if len(throughput) else 0
        throughput2_avg = round(statistics.mean(throughput2),2) if len(throughput2) else 0
        throughput2_max = round(max(throughput2),2) if len(throughput2) else 0
        
        logger.critical('OVERALL:throughput (success only)---> ' + str(throughput_avg)
                                + '  (max= ' + str(throughput_max) + ')')
        logger.critical('OVERALL:throughput2 (success only)---> ' + str(throughput2_avg)
                                + '  (max= ' + str(throughput2_max) + ')')

        metrics["app_overall"] ={"created":created, "sent": {"sum":sent, "percent":sent_percent},
            "code200":{"sum":code200, "percent":success_rate},
            "code500":code500, "code502":code502, "code503":code503, "code-1":code_1, "others":others,
            "dropped":{"sum":dropped_sensors_sum, "percent":dropped_sensors_percent},
            "dropped_in_bootup":{"sum":dropped_sensors_in_boot_up_sum, "percent":dropped_sensors_in_boot_percent},
            "admission_dur":{"avg":admission_duration_avg, "max":admission_duration_max},
            "queue_dur":{"avg":queuing_duration_avg, "max":queuing_duration_max},
            "exec_dur":{"avg":execution_duration_avg, "max":execution_duration_max},
            "round_trip": {"avg":response_time_sens_avg, "max":response_time_sens_max},
            "useless_exec_dur":useless_execution_duration_sum,
            "percentiles":{"p0":percentiles[0],"p25":percentiles[1],"p50":percentiles[2],"p75":percentiles[3],
            "p90":percentiles[4],"p95":percentiles[5],"p99":percentiles[6],
            "p99.9":percentiles[7],"p100":percentiles[8]},
            "throughput2":{"avg":throughput2_avg, "max":throughput2_avg}}

        
        logger.critical('METRICS PER APP  ****************************')
        app_order = []
        
        
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
            dropped_sensor = 0
            dropped_sensor_in_boot_up = 0
            if app[1]== True:
                logger.critical('**************     ' + app[0] +   '     **************')
                
                sent = 0
                
                for sensor in sensor_log.values():
                    #check function name
                    if sensor[0] == app[4]:
                        #dropped sensors are not considered in response time and replies
                        if sensor[7] != 451 and sensor[7]!=452:
                            
                            sent +=1
                            
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
                        #if dropped sensor
                        else:
                            if sensor[7]==451:
                                dropped_sensor +=1
                            elif sensor[7]==452:
                                dropped_sensor_in_boot_up +=1
                            else:
                                logger.error('dropped sensor unknown')
                            
                #calculate metrics of this app

                #OVERALL created recv by replies (actuators)
                created = app[6]
                recv=app[7]
                
                app_name = app[0]
                app_order.append(app_name)
                
                logger.critical('APP('+app[4]+'): REQ. CREATED: '  +str(created)
                + ' RECV (by apps): ' + str(recv) + ' RECV (by counter): ' + str(reply) )
                sent_percent = round(sent/created * 100,) if created > 0 else 0
                logger.critical('APP('+app[4]+'): REQ. SENT: '  +str(sent) + ' (' + str(sent_percent) + ')')
                #status
                sum_s = sum([status[0],status[1],status[2],status[3],status[4],status[5]])
                success_rate = round(status[0]/sum_s * 100,2) if sum_s > 0 else 0
                logger.critical("APP("+app[4]+"): Success Rate (200/sent): {}%".format(success_rate))
                logger.critical("APP("+app[4]+"): Success Rate (200/sent) new: {}%".format(
                    round(status[0]/sent * 100,2) if sent > 0 else 0))
                logger.critical('APP('+app[4]+'): {0}{1}{2}{3}{4}{5}'.format(
                'CODE200=' + str(status[0]) if status[0]>0 else ' ',
                'CODE500=' + str(status[1]) if status[1]>0 else ' ',
                'CODE502=' + str(status[2]) if status[2]>0 else ' ',
                'CODE503=' + str(status[3]) if status[3]>0 else ' ',
                'CODE-1=' + str(status[4]) if status[4]>0 else ' ',
                'OTHERS=' + str(status[5]) if status[5]>0 else ' '))
                
                
                dropped_sensor_sum =  dropped_sensor
                dropped_sensor_percent = round((dropped_sensor / created ) * 100,2) if created > 0 else 0
                logger.critical("APP(" + app[4] + "): Dropped (created, not sent): {} - percent {}%".format(
                    dropped_sensor_sum, dropped_sensor_percent))
                
                dropped_sensor_in_boot_up_sum = dropped_sensor_in_boot_up
                dropped_sensor_in_boot_up_percent = round((dropped_sensor_in_boot_up_sum/ created) * 100,2) if created>0 else 0
                logger.critical("APP(" + app[4] + "): Dropped inboot up(created, not sent): {} - percent {}%".
                    format(dropped_sensor_in_boot_up_sum, dropped_sensor_in_boot_up_percent))
                


                #print per app: ???admission dur should only consider sent sensors, not createds
                admission_duration_avg = round(statistics.mean(admission_duration),2) if len(admission_duration) else 0
                admission_duration_max = round(max(admission_duration),2) if len(admission_duration) else 0
                queuing_duration_avg = round(statistics.mean(queuing_duration),2) if len(queuing_duration) else 0
                queuing_duration_max = round(max(queuing_duration),2) if len(queuing_duration) else 0
                execution_duration_avg = round(statistics.mean(execution_duration),2) if len(execution_duration) else 0
                execution_duration_max = round(max(execution_duration),2) if len(execution_duration) else 0
                response_time_sens_avg = round(statistics.mean(response_time_sens),2) if len(response_time_sens) else 0
                response_time_sens_max = round(max(response_time_sens),2) if len(response_time_sens) else 0
                useless_execution_duration_avg = round(statistics.mean(useless_execution_duration),2) if len(useless_execution_duration) else 0
            

                logger.critical('APP('+app[4]+'): Adm. Dur. (sent only): avg '
                + str(admission_duration_avg) + ' --- max ' + str(admission_duration_max))
                
                logger.critical('APP('+app[4]+'): Q. Dur. (success only): avg '
                    + str(queuing_duration_avg) + ' --- max ' + str(queuing_duration_max))
                logger.critical('APP('+app[4]+'): Exec. +(scheduling) Dur. (success only): avg '
                + str(execution_duration_avg) + ' --- max ' + str(execution_duration_max) )
                logger.critical('APP('+app[4]+'): RT (success only): avg '
                + str(response_time_sens_avg) + ' --- max ' + str(response_time_sens_max))

                logger.critical('APP('+app[4]+'): Useless Exec. Dur.: sum '
                + str(useless_execution_duration_avg))
                                
                #Percentile
                percentiles = (np.percentile(response_time_sens, [0, 25, 50, 75, 90, 95, 99, 99.9, 100])if len(response_time_sens) else [0, 0, 0, 0, 0, 0, 0, 0, 0])
                percentiles = ([round(num,3) for num in percentiles])
                logger.critical('APP('+app[4]+'): Percentiles (success only): '
                                + str(percentiles) )
                        
                #System Throughput (every 30sec)
                throughput=[]
                throughput2=[]
                timer=test_started + 30
                
                
                while True:
                    created_tmp=0
                    for time in creation_time:
                        if time < timer and time > timer - 30:
                            created_tmp+=1
                            
                    finished=0
                    for time in finished_time:
                        if time < timer and time > timer - 30:
                            finished+=1
                            
                    #avoid divided by zero
                    if created_tmp==0:
                        throughput.append(0)
                    else:
                        throughput.append((finished/created_tmp) * 100)
                    throughput2.append(finished/ 30)
                    
                    if timer >= (test_finished):
                        break
                    else:
                        timer+=30
                
                throughput_avg = round(statistics.mean(throughput),2) if len(throughput) else 0
                throughput_max = round(max(throughput),2) if len(throughput) else 0
                throughput2_avg = round(statistics.mean(throughput2),2) if len(throughput2) else 0
                throughput2_max = round(max(throughput2),2) if len(throughput2) else 0


                logger.critical('APP('+app[4]+'):throughput (success only) avg '
                + str(throughput_avg) + ' --- max ' + str(throughput_max))
                                
                logger.critical('APP('+app[4]+'): throughput2 (success only) avg '
                + str(throughput2_avg) + ' --- max' + str(throughput2_max))
                                
                                
                metrics[app_name]={"created":created, "sent": {"sum":sent, "percent":sent_percent},
                "code200":{"sum":status[0], "percent":success_rate},
                "code500":status[1], "code502":status[2], "code503":status[3],
                "code-1":status[4], "others":status[5],
                "dropped":{"sum":dropped_sensor_sum, "percent":dropped_sensor_percent},
                "dropped_in_bootup":{"sum":dropped_sensor_in_boot_up_sum, "percent":dropped_sensor_in_boot_up_percent},
                "admission_dur":{"avg":admission_duration_avg, "max":admission_duration_max},
                "queue_dur":{"avg":queuing_duration_avg, "max":queuing_duration_max},
                "exec_dur":{"avg":execution_duration_avg, "max":execution_duration_max},
                "round_trip": {"avg":response_time_sens_avg, "max":response_time_sens_max},
                "useless_exec_dur":useless_execution_duration_avg,
                "percentiles":{"p0":percentiles[0],"p25":percentiles[1],"p50":percentiles[2],"p75":percentiles[3],
                "p90":percentiles[4],"p95":percentiles[5],"p99":percentiles[6],
                "p99.9":percentiles[7],"p100":percentiles[8]},
                "throughput2":{"avg":throughput2_avg, "max":throughput2_max}}
                

        #end per app
        if len(app_order):
            app_order.insert(0,'app_overall')
        metrics["app_order"]= app_order
        
    #scheduler logs
    if node_role == "MASTER":
        #scheduler logs
        rescheduled_sum = 0
        rescheduled_per_worker = [0]*len(workers)
        rescheduled_per_func = [0]*len(functions)
        
        for function in functions:
            versions = int(function[2][14])
            #sum
            rescheduled_sum += versions
            #per worker
            index = 0
            for worker in workers:
                if worker[0]==function[0][0]:
                    index = workers.index(worker)
                    break
            rescheduled_per_worker[index] += versions
            #per functions
            rescheduled_per_func[functions.index(function)] += versions
        #print
        logger.critical('Scheduler Logs:\n rescheduling: \n '
                + 'Sum: ' + str(rescheduled_sum)
                + '\nPer Worker: ' + ' -- '.join([str(str(workers[index][0]) + ': '
                + str(rescheduled_per_worker[index])) for index in
                range(len(rescheduled_per_worker))])
                + '\nPer Function: ' + '\n'.join([str(str(functions[index][0][0]) + '-'
                + str(functions[index][0][1]) + ': '
                + str(rescheduled_per_func[index])) for index in
                range(len(rescheduled_per_func))]))
        
        per_worker = {workers[index][0]: rescheduled_per_worker[index] for index in
                       range(len(rescheduled_per_worker))}
        logger.info(per_worker)
        
        per_function = {functions[index][0][0] + '-' + functions[index][0][1]:
                rescheduled_per_func[index] for index in range(len(rescheduled_per_func))}
        #down per scheduling iterations
        down_counter ={worker[0]: 0 for worker in workers}
        #per scheduling_round
        for key, value in history["workers"].items():
            scheudling_round = key
            nodes = value
            #evaluate all nodes SoC one at a time
            for node in nodes:
                soc = node[2]
                min_battery_charge = battery_cfg[8]
                #if node is down, increment its down_counter
                if soc < min_battery_charge:
                    name = node[0]
                    down_counter[name]+=1
        
        metrics["scheduler"] ={"placements":{"sum":rescheduled_sum,
                                             "workers":per_worker,
                                             "functions":per_function},
                               "down_counter": down_counter}
                               
        logger.info(metrics["scheduler"])
        
       #save scheduler history to file
        # as numpy array
        #np.save(log_path + "/functions", history["functions"])
        #np.save(log_path + "/workers", history["workers"])
        #as json?????????
        with open(log_path + "/functions.txt", "w") as f:
            json.dump(history["functions"], f, indent=2)
        with open(log_path + "/workers.txt", "w") as w:
            json.dump(history["workers"], w, indent=2)
        #to read
        #functions = json.load(open(log_path + "/functions.txt", "r"))
        #workers = json.load(open(log_path + "/workers.txt", "r"))
   #else role is MONITOR
    
    log_index = log_path + "/" + node_name + "-monitor.csv"
    labels = ['time1', 'time2', 'rt_acc', 'battery', 'cpu_util', 'memory', 'disk',
        'cpu_temp','cpu_freq_curr', 'cpu_freq_min', 'cpu_freq_max', 'cpu_ctx_swt', 'cpu_inter', 'cpu_soft_inter',
        'io_read_count', 'io_write_count', 'io_read_bytes', 'io_write_bytes',
        'bw_pack_sent', 'bw_pack_rec', 'bw_bytes_sent', 'bw_bytes_rec', 'bw_bytes_dropin', 'bw_bytes_dropout']
    if usb_meter_involved:
        labels.extend(['mwh_new', 'mwh', 'mah', 'watts', 'amps', 'volts', 'temp'])
    
    monitor_data = []
    monitor_data.append(labels)
    #mwh
    mwh_sum=0
    mwh_first=power_usage[0][0]                    
    mwh_second=0
    
    #bw
    bw_usage_sum = [0]*len(bw_usage[0])
    bw_usage_first = bw_usage[0]
    bw_usage_second = [0]*len(bw_usage[0])
    if len(cpuUtil)!= len(power_usage):
        logger.error('len (cpuUtil)= ' + str(len(cpuUtil)) + ' len (power_usage)= ' + str(len(power_usage)))
    
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
        #bw usage new
        if i > 0:
            bw_usage_second=bw_usage[i]
            usage=[bw_usage_second[index] - bw_usage_first[index] for index in range(len(bw_usage[0]))]
            
            bw_usage_sum = [bw_usage_sum[index] + usage[index] for index in range(len(bw_usage[0]))]
            #exchange
            bw_usage_first = bw_usage_second
            
        curr_list.append(str(bw_usage_sum[0]))
        curr_list.append(str(bw_usage_sum[1]))
        curr_list.append(str(bw_usage_sum[2]))
        curr_list.append(str(bw_usage_sum[3]))
        curr_list.append(str(bw_usage_sum[4]))
        curr_list.append(str(bw_usage_sum[5]))
        
        if usb_meter_involved:
            #sometimes len power_usage is 1 index shorter than others ???
            if i < len(power_usage):
                #power usage new
                if i > 0:
                    #mwh
                    mwh_second=power_usage[i][0]
                    usage=mwh_second-mwh_first
                    if usage<0: #loop point
                        usage=(99999-mwh_first) + (mwh_second-97222)
                
                    mwh_sum+=usage
                    #exchange
                    mwh_first=mwh_second
                    
                curr_list.append(str(mwh_sum))
                
                curr_list.append(str(power_usage[i][0]))
                curr_list.append(str(power_usage[i][1]))
                curr_list.append(str(power_usage[i][2]))
                curr_list.append(str(power_usage[i][3]))
                curr_list.append(str(power_usage[i][4]))
                curr_list.append(str(power_usage[i][5]))
            else:
                logger.warning('save_reports: power_usage shorter than cpu_usage')
                curr_list.append(str(mwh_sum))
                
                curr_list.append(str(power_usage[i-1][0]))
                curr_list.append(str(power_usage[i-1][1]))
                curr_list.append(str(power_usage[i-1][2]))
                curr_list.append(str(power_usage[i-1][3]))
                curr_list.append(str(power_usage[i-1][4]))
                curr_list.append(str(power_usage[i-1][5]))
        
        monitor_data.append(curr_list)

    np.savetxt(log_index, monitor_data, delimiter=",", fmt="%s")
    
    
    logger.critical('Save_Reports: ' + log_index)
    if len(response_time)==0: response_time.append(1)
    logger.critical('METRICS********************')
    logger.critical('######Exec. time avg='
                    + str(round(sum(response_time)/len(response_time),2)))
    logger.critical('######Exec. time accumulative= '
                    + str(sum(response_time_accumulative)/len(response_time_accumulative)))
    cpuUtil_avg = round(statistics.mean(cpuUtil),2)
    cpuUtil_max = round(max(cpuUtil),2)
    logger.critical('######cpu= '
                    + str(round(sum(cpuUtil)/len(cpuUtil),2)) + ' max=' + str(max(cpuUtil)))
    
    min_battery_charge_percent =(battery_cfg[8]/ battery_cfg[1]) * 100
    cpuUtil_up = [cpuUtil[i] for i in range(len(cpuUtil)) if battery_charge[i] >= min_battery_charge_percent] 
    cpuUtil_up_avg = round(statistics.mean(cpuUtil_up),2) if len(cpuUtil_up) else 0
    cpuUtil_up_max = round(max(cpuUtil_up),2) if len(cpuUtil_up) else 0
    logger.critical('######cpu (up)= '
        + str(round(sum(cpuUtil_up)/len(cpuUtil_up),2) if cpuUtil_up != [] else 0)
        + ' max=' + str(max(cpuUtil_up) if cpuUtil_up != [] else 0))
    
    memory_avg = round(statistics.mean(memory),2) if len(memory) else 0
    memory_max = round(max(memory),2) if len(memory) else 0
    logger.critical('######memory='+ str(round(sum(memory)/len(memory),2))
                    + ' max=' + str(max(memory)))
    
    logger.critical('######disk_io_usage_Kbyte_read= '
                    + str(round((disk_io_usage[-1][2] - disk_io_usage[0][2])/1024,2)))
    logger.critical('######disk_io_usage_Kbyte_write= '
                    + str(round((disk_io_usage[-1][3] - disk_io_usage[0][3])/1024,2)))
    #logger.critical('######bw_packet_sent=' + str(round(bw_usage[-1][0] - bw_usage[0][0],2)))
    #logger.critical('######bw_packet_recv=' + str(round(bw_usage[-1][1]- bw_usage[0][1],2)))
    logger.critical('######bw_Kbytes_sent= '
                    + str(round((bw_usage[-1][2] - bw_usage[0][2])/1024,2)))
    logger.critical('######bw_Kbytes_recv= '
                    + str(round((bw_usage[-1][3] - bw_usage[0][3])/1024,2)))
    #power usage
    power_usage_incremental = mwh_sum
    #remover?
    mwh_sum=0
    mwh_first=power_usage[0][0]
    mwh_second=0
    usage = 0
    for row in power_usage[1:]:
        mwh_second=row[0]
        usage=mwh_second-mwh_first
        if usage<0: #loop point
            usage=(99999-mwh_first) + (mwh_second-97222)
    
        mwh_sum+=usage
        #exchange
        mwh_first=mwh_second
        
    logger.critical('######power_usage= '
                    + str(mwh_sum) + ' mWh --- inc. (' + str(power_usage_incremental)+ ')')
    
    #down_time
    down_time_minute = 0
    down_time_percent = 0
    if battery_cfg[0] == True:
        test_duration = test_finished - test_started
        logger.info('test_duration= ' + str(round(test_duration)) + ' sec ('
            + str(round(test_duration/60)) + ' min)')
        down_time_minute = round((down_time)/60,2) 
        down_time_percent = round(down_time/test_duration*100,0)
        logger.critical('######down_time= ' + str(down_time_minute)
                        + ' min  (=' + str(down_time_percent) + ' %)')
    
    #metrics
    metrics["node"] ={"role":node_role, "name":node_name, "ip":node_IP,
                "power_usage":power_usage_incremental,
                "down_time":{"minute":down_time_minute, "percent":down_time_percent},
                "cpu_usage": {"avg":cpuUtil_avg, "max":cpuUtil_max},
                "cpu_usage_up":{"avg":cpuUtil_up_avg, "max":cpuUtil_up_max},
                "memory_usage":{"avg":memory_avg, "max":memory_max},
                "bw_usage":{"sent_mb":round(bw_usage_sum[2]/1024/1024),
                            "recv_mb":round(bw_usage_sum[3]/1024/1024)}}

    #writing metrics to excel
    if node_role == 'LOAD_GENERATOR':
        #send to master
        metrics_sender(metrics)
    elif node_role == 'MASTER':
        #write locally using metrics_writer()
        cmd = 'metrics'
        sender = 'internal'
        pi_service(cmd, sender)
    else:
        logger.warning('skip metrics_sender()')
    
    #save metrics
    with open(log_path + "/metrics.txt", "w") as m:
        json.dump(metrics, m, indent=8)
                                
    if snapshot_report[0]=='True':
        begin=int(snapshot_report[1])
        end=int(snapshot_report[2])
        logger.critical('Snapshot: ' + str(begin) + ' to ' + str(end))
        
        logger.critical('######Exec. time avg='+ str(round(sum(response_time)/len(response_time),2)))
        logger.critical('######Exec. time accumulative='+ str(round(sum(response_time_accumulative)/len(response_time_accumulative)),2))
        logger.critical('######cpu=' + str(round(sum(cpuUtil[begin:end])/len(cpuUtil[begin:end]),2)))
        logger.critical('######memory='+ str(round(sum(memory[begin:end])/len(memory[begin:end]),2)))
        logger.critical('######bw_packet_sent=' + str(round(bw_usage[end][0] - bw_usage[begin][0])))
        logger.critical('######bw_packet_recv=' + str(round(bw_usage[end][1]- bw_usage[begin][1])))
        logger.critical('######bw_Kbytes_sent=' + str(round((bw_usage[end][2] - bw_usage[begin][2])/1024)))
        logger.critical('######bw_Kbytes_recv=' + str(round((bw_usage[end][3] - bw_usage[begin][3])/1024)))
        if usb_meter_involved:
            logger.critical('######power_usage=' + str(power_usage[end][0]- power_usage[begin][0]))
           
    

def metrics_sender(metrics):
    global logger
    global gateway_IP
    global node_name
    logger.info('metrics_sender: start')
    while True:
        try:
            #to avoid multiple write operations on a single file
            #time.sleep(random.randint(1,3))
            #specific to node name w1 w2 .... ????
            time.sleep(int(node_name.split('w')[1])*3)
            sender = node_name
            response=requests.post('http://'+gateway_IP+':5000/pi_service/metrics/' + sender, json=metrics)
        except Exception as e:
            logger.error('metrics_sender: exception:' + str(e))
        #if no exception   
        else:
            if response.text=="success":
                logger.info('metrics_sender: success')
                break
            else:
                logger.error('metrics_sender: failed')
                time.sleep(random.randint(1,3))
                logger.info('metrics_sender: retry')
    

@app.route('/pi_service/<cmd>/<sender>',methods=['POST', 'GET'])   
def pi_service(cmd, sender, plan={}):
    global epoch
    global test_name
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
    global max_request_timeout
    global monitor_interval
    global battery_charge
    logger.info('pi_service: cmd = '+ cmd + ', sender = ' + sender)
    
    if cmd=='plan':
        #ACTIONS BASED ON SENDER role or location
        #wait
        if under_test==True:            
            under_test=False
            cooldown()
            
        #reset times, battery_cfg(current SoC), apps (created/recv), monitor, free up resources,
        reset()
        
        if node_role == "MASTER":
            openfaas_clean_up()
            
        #plan
        #set plan for LOAD_GENERATOR, MONITOR, STANDALONE by master node
        if sender=='MASTER': 
            plan = request.json
                
            #verify plan
            if plan==None:
                logger.warning('pi_service:plan:master:no plan received, so default values are used')
            else:
                verified = apply_plan(plan)
                if verified == False:
                    return "failed to set plan"
        #set plan for coordinator (master or standalone) by itself
        elif sender=="INTERNAL": 
            if len(plan)>0:
                verified = apply_plan(plan)
                if verified == False:
                    return "failed to set plan"
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
        
        #get plan
        show_plan()
        
        #under test
        under_test=True
        
        #set start time
        test_started= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        
        #run pi_monitor
        thread_monitor= threading.Thread(target = pi_monitor, args=())
        thread_monitor.name = "pi_monitor"
        thread_monitor.start()
            
        #run battery_sim
        if battery_cfg[0]==True:
            if usb_meter_involved==False:
                logger.error('pi_service:on: USB Meter is needed for Battery Sim')
                return "pi_service:on: USB Meter is needed for Battery Sim"
            thread_battery_sim = threading.Thread(target = battery_sim, args=())
            thread_battery_sim.name = "battery_sim"
            thread_battery_sim.start()

        #run timer
        if time_based_termination[0]==True:
            thread_timer = threading.Thread(target = timer, args=())
            thread_timer.name = "timer"
            thread_timer.start()
                
        #run failuer handler
        if node_role=='LOAD_GENERATOR' or node_role=='STANDALONE':
            thread_failure_handler = threading.Thread(target = failure_handler, args=())
            thread_failure_handler.name = "failure_handler"
            thread_failure_handler.start()
            
        #run workload
        if node_role=="LOAD_GENERATOR" or node_role=='STANDALONE':
            #per apps
            for my_app in apps:
                if my_app[1] == True:
                    thread_app = threading.Thread(target = workload, args=(my_app,))
                    thread_app.name = "workload-" + my_app[0]
                    thread_app.start()
                    
                    
        #run scheduler
        if node_role=="MASTER":
            thread_scheduler = threading.Thread(target = scheduler, args=())
            thread_scheduler.name = "scheduler"
            thread_scheduler.start()
                
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
    
    #metrics write
    elif cmd == 'metrics':
        if 'internal' in sender:
            data = metrics
        else:
            data = request.json

        #write
    
        logger.info('call excel_writer.write')
        logger.info('data')
        logger.info(data)
        logger.info('excel_file_path')
        logger.info(setup.excel_file_path)
        result, row = excel_writer.write(data, setup.excel_file_path)
        logger.info('call excel_writer.write done in row #' + str(row) )
        #write avg of results if this is the last worker sending metrics, why by name????
        if data["node"]["name"] == "w5":
            logger.info('call excel_writer.avg')
            rows_count = 5
            row = excel_writer.write_avg(rows_count, setup.excel_file_path)
            logger.info('call excel_writer.avg done in row #' + str(row) )
        logger.info('write is done')
        return result
    
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
        logger.info('Test ' + test_name + ' is done!')
        
        #thread to start a new test
        if node_role == "MASTER":
            #epoch
            epoch += 1
            
            if epoch < len(setup.test_name):
                logger.info('Try another test ...')
                #clean up
                openfaas_clean_up()
            
                #cooldown
                cooldown(setup.intra_test_cooldown)
                
                node = [node for node in setup.nodes if node[0]=="COORDINATOR" and node[1]==socket.gethostname() and node[2]==node_IP][0]
                logger.info('node: '  + str(node))
                
                thread_launcher = threading.Thread(target= launcher, args=(node,))
                thread_launcher.name = "launcher"
                thread_launcher.start()
                
    #'charge'
    elif cmd=="charge":
        logger.info("pi_service:charge: req. from " + str(sender) + ": start")
        logger.info("pi_service:charge: return to "
                    + str(sender) + ": " + str(round(battery_cfg[3],2)) + " mwh")
        return str(battery_cfg[3])
        logger.info("pi_service:charge: sender:" + str(sender) + ": stop")
    else:
        logger.error('pi_service: unknown cmd')
        return 'failed'
    
    logger.info('pi_service: stop')
 
#clean up
def openfaas_clean_up():
    #clean up
    global logger
    logger.info('clean_up: start')
    try:
        #helm chart
        cmd = "helm delete " + setup.function_chart[0]
        logger.info('clean up function chart: ' + cmd)
        os.system(cmd)
        
        #nats 
        cmd= "kubectl rollout restart -n openfaas deployment/nats"
        logger.info('clean up nats: ' + cmd)
        os.system(cmd)
        
        #queue-worker ????? should get name of queues from a reliable variable
        if setup.multiple_queue:
            cmd= "kubectl rollout restart -n openfaas deployment/queue-worker-yolo3"
            logger.info('clean up queue-worker: ' + cmd)
            os.system(cmd)
            cmd= "kubectl rollout restart -n openfaas deployment/queue-worker-irrigation"
            logger.info('clean up queue-worker: ' + cmd)
            os.system(cmd)
            cmd= "kubectl rollout restart -n openfaas deployment/queue-worker-crop-monitor"
            logger.info('clean up queue-worker: ' + cmd)
            os.system(cmd)
            cmd= "kubectl rollout restart -n openfaas deployment/queue-worker-short"
            logger.info('clean up queue-worker: ' + cmd)
            os.system(cmd)
        else:
            cmd= "kubectl rollout restart -n openfaas deployment/queue-worker"
            logger.info('clean up queue-worker: ' + cmd)
            os.system(cmd)
    except Exception as e:
        logger.error('clean_up:\n' + str(e))
        
    logger.info('clean_up: done')
    
    
#cooldown
def cooldown(intra_test_cooldown = 0):
    global node_role
    global battery_cfg
    global monitor_interval
    global max_request_timeout
    global failure_handler_interval
    global apps
    global logger
    logger.info('cooldown:start')
    wait=0
    
    if node_role=="MONITOR" or node_role=="MASTER":
        if battery_cfg[0]==True:
            wait=sum([monitor_interval, battery_cfg[7]])
        else: wait=monitor_interval
        
    else: #node_role == "STANDALONE or LOAD_GENERATOR"
        if battery_cfg[0]==True:
            wait=sum([monitor_interval, battery_cfg[7], failure_handler_interval,max_request_timeout]) #sum get no more than 2 args
        else: wait=sum([monitor_interval, failure_handler_interval,max_request_timeout])
        #while any([True if app[1]==True and app[6]!=app[7] else False for app in apps ])==True:
        #    wait=3
        #    logger.info('cooldown: wait for ' + str(wait) + ' sec')
        #    time.sleep(wait)
    if wait < intra_test_cooldown:
        wait = intra_test_cooldown
    
    logger.info('cooldown: wait for ' + str(wait) + ' sec...')
    time.sleep(wait)
    
    logger.info('cooldown: stop')
    
def show_plan():   
    # 
    global test_name
    global node_name
    global debug
    global gateway_IP
    global bluetooth_addr
    global apps
    global battery_cfg
    global time_based_termination
    global max_request_timeout
    global min_request_generation_interval
    global sensor_admission_timeout
    global node_role
    global peers
    global monitor_interval
    global scheduling_interval
    global failure_handler_interval
    global usb_meter_involved
    global battery_operated
    global node_IP
    global socket
    global max_cpu_capacity
    global raspbian_upgrade_error
    global boot_up_delay
    global log_path
    #counters/variables
    global under_test
    global test_started
    global test_finished
    global sensor_log
    global workers
    global functions
    global history
    global suspended_replies
    global down_time
    
    logger.info('show_plan: start')
    show_plan= ("test_name: " + test_name
                + " node_name: " + str(socket.gethostname()) + " / " + str(node_name)
                + "\n IP: " + node_IP
                + "\n node_role: " + node_role
                + "\n gateway_IP: " + gateway_IP
                + "\n Debug: " + str(debug)
                + "\n bluetooth_addr: " + bluetooth_addr
                + "\n apps: " + '\n'.join([str(app) for app in apps])
                + "\n peers: " + str(peers)
                + "\n usb_meter_involved: " + str(usb_meter_involved)
                + "\n battery_operated: " + str(battery_operated)
                + "\n battery_cfg: " + str(battery_cfg)
                + "\n time_based_termination: " + str(time_based_termination)
                + "\n monitor_interval: " + str(monitor_interval)
                + "\n scheduling_interval: " + str(scheduling_interval)
                + "\n failure_handler_interval: " + str(failure_handler_interval)
                + "\n max_request_timeout: " + str(max_request_timeout)
                + "\n min_request_generation_interval: " + str(min_request_generation_interval)
                + "\n sensor_admission_timeout: " + str(sensor_admission_timeout)
                + "\n max_cpu_capacity: " + str(max_cpu_capacity)
                + "\n boot_up_delay: " + str(boot_up_delay)
                + "\n log_path: " + str(log_path)
                + "\n under_test: " + str(str(under_test))
                + "\n test_started: " + str(str(test_started))
                + "\n test_finished: " + str(str(test_finished))
                + "\n sensor_log: " + str(str(sensor_log))
                + "\n functions: " + str(str(functions))
                + "\n workers: " + str(str(workers))
                + "\n history: " + str(str(history))
                + "\n suspended_replies: " + str(str(suspended_replies))
                + "\n down_time: " + str(str(down_time))
                + "\n raspbian_upgrade_error: " + str(raspbian_upgrade_error))
    logger.info("show_plan: " + show_plan)
    
    logger.info('show_plan: stop')
    
def apply_plan(plan):
    global test_name
    global debug
    global gateway_IP
    global bluetooth_addr
    global apps
    global battery_cfg
    global time_based_termination
    global max_request_timeout
    global min_request_generation_interval
    global sensor_admission_timeout
    global node_role
    global peers
    global waitress_threads
    global monitor_interval
    global scheduling_interval
    global failure_handler_interval
    global usb_meter_involved
    global battery_operated
    global max_cpu_capacity
    global log_path
    global pics_folder
    global file_storage_folder
    global boot_up_delay
    global raspbian_upgrade_error
    logger.info('apply_plan: start')
    #create test_name
    test_name = socket.gethostname() + "_" + plan["test_name"]
    
    node_role = plan["node_role"]
    gateway_IP = plan["gateway_IP"]
    debug=plan["debug"]
    bluetooth_addr = plan["bluetooth_addr"]
    apps= plan["apps"]
    peers = plan["peers"]
    usb_meter_involved = plan["usb_meter_involved"]
    #Either battery_operated or battery_cfg should be True, if the second, usb meter needs enabling
    battery_operated=plan["battery_operated"]
    #Battery simulation
    battery_cfg = plan["battery_cfg"] #1:max,2:initial (and current) SoC, 3:renewable seed&lambda, 4:interval
    #NOTE: apps and battery_cfg values change during execution
    time_based_termination= plan["time_based_termination"] # end time-must be longer than actual test duration
    monitor_interval = plan["monitor_interval"]
    scheduling_interval=plan["scheduling_interval"]
    failure_handler_interval =plan["failure_handler_interval"]
    max_request_timeout=plan["max_request_timeout"]
    min_request_generation_interval= plan["min_request_generation_interval"]
    sensor_admission_timeout= plan["sensor_admission_timeout"]
    max_cpu_capacity =plan["max_cpu_capacity"]
    
    #get home directory
    home = expanduser("~")
    
    log_path = plan["log_path"]
    log_path = home + log_path + test_name
    #empty test_name folder (if not exist, ignore_errors)
    shutil.rmtree(log_path, ignore_errors=True)
    #create test_name folder
    if not os.path.exists(log_path): os.makedirs(log_path)
    
    
    #update logger fileHandler
    #default mode is append 'a' to existing log file. But, 'w' is write from scratch
    #change fileHandler file on the fly
    #another option: [%(funcName)s] ???
    formatter = logging.Formatter('%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s')
    fileHandler = logging.FileHandler(log_path + '/pi-agent.log', mode='w')
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.INFO)
    log = logging.getLogger() #root logger
    for hndlr in log.handlers[:]:#remove the existing file handlers
        log.removeHandler(hndlr)
    log.addHandler(fileHandler) #set the new handler
    
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    consoleHandler.setLevel(logging.INFO)

    logger.addHandler(consoleHandler) 
    
    pics_folder = home + plan["pics_folder"]
    if not os.path.exists(pics_folder):
        logger.error('apply_plan: no pics_folder directory found at ' + pics_folder )
        return False
    file_storage_folder = home + plan["file_storage_folder"]
    if not os.path.exists(file_storage_folder): os.makedirs(file_storage_folder)
    
    waitress_threads = plan["waitress_threads"]
    boot_up_delay = plan["boot_up_delay"]
    raspbian_upgrade_error = plan["raspbian_upgrade_error"]

    logger.info('apply_plan: stop')
    return True

#timer    
def timer():
    global monitor_interval
    global max_request_timeout
    global failure_handler_interval
    global time_based_termination
    global test_started
    global under_test
    logger.info('start')
    
    while under_test:
        now= datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        elapsed = now-test_started
        if elapsed>= time_based_termination[1]:
            break
        else:
            time.sleep(min(failure_handler_interval,monitor_interval, max_request_timeout))
    
    if under_test==True:
        #alarm pi_service
        thread_terminator= threading.Thread(target= pi_service, args=('stop', 'INTERNAL',))
        thread_terminator.name = "terminator"
        thread_terminator.start()
    logger.info('stop')
        
        
#terminate who is "me" or "others" or "all"
@app.route('/terminate/<who>', methods = ['GET', 'POST'])
def terminate(who):
    if who is "me":
        pi_service('stop','INTERNAL')
    elif who is "others":
        for node in setup.nodes:
            if node[0] is "PEER":
                ip = node[2]
                try:
                    response=requests.post('http://'+ip+':5000/pi_service/stop')
                except:
                    logger.error('terminator: failed for ' + ip )
    elif who is "all":
        pi_service('stop','INTERNAL')
        
        for node in setup.nodes:
            if node[0] is "PEER":
                ip = node[2]
                try:
                    response=requests.post('http://'+ip+':5000/pi_service/stop')
                except:
                    logger.error('terminator: failed for ' + ip )
    else:
        logger.info('terminator: who is unknown')
        return 'failed'
                    
    return "stopped"

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
    global down_time
    logger.info('Start')
    battery_max_cap = battery_cfg[1] #theta: maximum battery capacity in mWh
    
    renewable_type = battery_cfg[4]
    
    renewable_inputs = []
    start_time = 0
    
    #get poisson
    if renewable_type == "poisson":
        
        #Generate renewable energy traces
        np.random.seed(battery_cfg[5][0])
        renewable_inputs = np.random.poisson(lam=battery_cfg[5][1], size=10000) 
    #get real dataset
    elif renewable_type == "real":
        
        renewable_inputs = battery_cfg[6]
        
        start_time = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
        
    else:
        logger.error('renewable_type not found:' + str(renewable_type))
    
    previous_usb_meter = read_power_meter()[0]
    
    renewable_index = 0;
    renewable_input = 0
    interval = battery_cfg[7]
    
    while under_test:
        #GET
        soc = battery_cfg[3] #soc: previous observed SoC in Mwh
        last_soc = soc
        #renewable
        if renewable_type == "poisson":
            renewable_index +=1
            renewable_input = renewable_inputs[renewable_index]
        elif renewable_type == "real":
            #index and effect
            #index
            #hourly dataset, and scale 6 to 1, means each index is for 10 min
            now = datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            dur = now-start_time
            renewable_index = math.floor(dur/600) #if 601 sec, index = 1, if 200sec, index=0
            #if dataset finishs, it starts from the begining
            renewable_index = int(math.fmod(renewable_index,len(renewable_inputs)))
            #effect
            raw_input = renewable_inputs[renewable_index]
            #calculate the share for this interval
            #optimal
            optimal=1
            if node_name == "w4" or node_name=="w5":
                optimal = 1.15
            renewable_input = (raw_input/(600/interval)) * optimal
        else:
            logger.error('unknown renewable_type  --> ' + str(renewable_type))
            
           
        usb_meter = read_power_meter()[0]
        
        energy_usage = usb_meter - previous_usb_meter
        #fix USB meter loop in 99999 to 97223. NOTE: INTERVALS SHOULD NOT BE TOO LONG: > 2500mWH
        if usb_meter - previous_usb_meter < 0:
            energy_usage = (99999 - previous_usb_meter) + (usb_meter - 97222)
        #UPDATE
        #min to avoid overcharge. max to avoid undercharge
        soc= min(battery_max_cap, max(0, soc + renewable_input - energy_usage))
        
        battery_cfg[3] = soc
        
        #down_time
        #calculate down_time
        min_battery_charge = battery_cfg[8]
        if soc < min_battery_charge:
            down_time += interval
            if last_soc > min_battery_charge:
                logger.info('node went to dead mode!')
        
        #when it went to up
        if last_soc < min_battery_charge and soc > min_battery_charge:
            turned_up_at =  datetime.datetime.now(datetime.timezone.utc).astimezone().timestamp()
            battery_cfg[9] = turned_up_at
            logger.info('node is up back')
                    
        
        previous_usb_meter = usb_meter      
        
        time.sleep(interval)
    
    logger.info('Stop')
# ---------------------------------

@app.route('/reset',methods=['POST']) 
def reset():
    logger.info('reset:start')
    global test_name
    global metrics
    global under_test
    global gateway_IP
    global test_started
    global test_finished
    global sensor_log
    global battery_cfg
    global workers
    global functions
    global history
    global apps
    global failure_handler_interval
    global suspended_replies
    global down_time
    global boot_up_delay
    global log_path
    global min_request_generation_interval
    global max_request_timeout
    global sensor_admission_timeout
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
    test_name="no_name"
    metrics = {}
    under_test = False
    gateway_IP = ""
    test_started=None
    test_finished=None
    down_time = 0
    sensor_log ={}
    home = expanduser("~")
    log_path = home + "/" + test_name

    apps = []
    battery_cfg[3]=battery_cfg[2]#current =initial
    
    #scheudler
    workers = []
    functions = []
    history = {'functions':{}, 'workers': {}}
    suspended_replies = []
    boot_up_delay = 0
    #monitoring parameters
        #in owl_actuator
    response_time = []
    min_request_generation_interval = 0
    max_request_timeout = 30
    sensor_admission_timeout = 3
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

if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(threadName)s] [%(levelname)s] %(message)s')
    #default mode is append 'a' to existing log file. But, 'w' is write from scratch
    if not os.path.exists(log_path): os.makedirs(log_path)
    fileHandler = logging.FileHandler(log_path + '/pi-agent.log', mode='w')
    fileHandler.setFormatter(formatter)
    fileHandler.setLevel(logging.INFO)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    consoleHandler.setLevel(logging.INFO)

    logger.addHandler(fileHandler)
    logger.addHandler(consoleHandler)         

    #setup file exists?
    dir_path=os.path.dirname(os.path.realpath(__file__))
    if os.path.exists(dir_path + "/setup.py"):
        
        #run launcher if coordinator
        for node in setup.nodes:
            #find this node in nodes
            position=node[0]
            name=node[1]
            if name==socket.gethostname():
                #verify if this node's position is COORDINATOR
                if position=="COORDINATOR":
                    #just MASTER and STANDALONE are eligible to be a COORDINATOR
                    if setup.plan[name]["node_role"]== "MASTER" or setup.plan[name]["node_role"]== "STANDALONE":
                        logger.info('MAIN: Node position is coordinator')
                        thread_launcher = threading.Thread(target= launcher, args=(node,))
                        thread_launcher.name = "launcher"
                        thread_launcher.start()
                        break
                    else:
                        logger.error('MAIN: Node role in its plan must be MASTER or STANDALONE')
                else:
                    logger.info('MAIN: Node position is ' + position)
    else:
        logger.info('MAIN: No setup found, so wait for a coordinator')
    #threads=number of requests can work concurrently in waitress; exceeded requests wait for a free thread
    serve(app, host= '0.0.0.0', port='5000', threads= waitress_threads)
    
    