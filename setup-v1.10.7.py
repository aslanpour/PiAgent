#first run pi_Service on PEERs

#epoch driver
#test_name=["greedy2"]
test_name=[ "optimal1"]

test_duration= 240 * 60 #####
#[0] position (e.g.,COORDINATOR, PEER, or -) [1] node name [2] node ip
nodes=[["COORDINATOR","master","10.0.0.90"],
       ["PEER", "w1","10.0.0.91"],
       ["PEER", "w2","10.0.0.92"],
       ["PEER", "w3","10.0.0.93"],
       ["PEER", "w4","10.0.0.94"],
       ["PEER", "w5","10.0.0.95"]]
gateway_IP = "10.0.0.90"
#zonal categorization by Soc %
#[0] zone [1] priority [2] max Soc threshold [3] min Soc threshold
zones = [["rich", 1, 100, 60],
        ["vulnerable", 3, 60, 30],
        ["poor", 2, 30, 10],
        ["dead", 4, 10, -1]] #-1 means 0
#zones = [["rich", 1, 100, 75],
#        ["vulnerable", 3, 75, 25],
#        ["poor", 2, 25, 10],
#        ["dead", 4, 10, -1]] #-1 means 0
#if 1250=100%, then 937.5=75%, 312.5=25% and 125=10%

#local #default-kubernetes #random #bin-packing #greedy #g-sticky #g-warm #g-warm-sticky
#scheduler_name = ["greedy"]
scheduler_name = [ "greedy2", "greedy4"] #####

#==0 only if scheduler_name=="greedy" and warm_scheduler=True
#and should be limited just in case function is not locally placed. (not implemented yet this part), so it is applied all the time if used
#this time takes for newly up node to be ready to send_sensors
boot_up_delay = 0   ####
#scheduler_greedy_config
sticky = True # it requires offloading=True to be effective
stickiness = [0.2, 0.2, 0.2, 0.2, 0.2] #20% # it requires offloading=True to be effective #####
warm_scheduler = True # it requires offloading=True to be effective

scale_to_zero = False #(not implemented yet)

#auto-scaling:  "openfaas"  or "hpa" (hpa not implemented yet)
auto_scaling = "openfaas"
#factor: default is 20, if 0, if hpa, auto-scaling by hpa, otherwise openfaas scaling is disabled
auto_scaling_factor = 100
#yolo3, crop-monitor and irrigation and short
auto_scaling_min = {"yolo3": 2, "crop-monitor":2, "irrigation":2, "short":2}
auto_scaling_max = {"yolo3": 2, "crop-monitor":2, "irrigation":2, "short":2} ####

#"static" or "poisson" (concurrently) or "exponential" (interval) or "exponential-poisson"
Workload_type ="exponential-poisson"
seed = 5

#[0] iteration [1] [1]interval/exponential lambda (lambda~=avg)
#[2]concurrently/poisson lambda (lambda~=avg) [3] random seed (def=5)]
apps = {"yolo3": False, "irrigation":True, "crop-monitor": True, "short": True}

workload_cfg ={
"w1":[[1000, 60, 0.6,seed], [10000, 6, 1.9,seed], [10000, 5, 1.0,seed], [10000, 10, 1,seed]],
"w2":[[1000, 60, 0.6,seed], [10000, 20, 1.9,seed], [10000, 15, 1.0,seed], [10000, 10, 1,seed]],
"w3":[[1000, 60, 0.6,seed], [10000, 10, 1.9,seed], [10000, 8, 1.0,seed], [10000, 10, 1,seed]],
"w4":[[1000, 60, 0.6,seed], [10000, 10, 1.9,seed], [10000, 8, 1.0,seed], [10000, 10, 1,seed]],
"w5":[[1000, 60, 0.6,seed], [10000, 6, 1.9,seed],[10000, 5, 1.0,seed], [10000, 10, 1,seed]]}

#copy chart-latest and chart-profile folders to home directory of master
profile_chart = ["chart-profile", "~/charts/chart-profile"]
function_chart = ["chart-latest", "~/charts/chart-latest"]
excel_file_path = "/home/pi/logs/metrics.xlsx" # this file should already be there with a sheet named nodes
clean_up = True #####
profile_creation_roll_out = 30  ####
function_creation_roll_out = 120 
redis_server_ip= "10.43.242.161" #assume default port is selected as 3679
#NOTE if True, queues must be already created! and follow the name pattern as queue-worker-functionName
multiple_queue=True
#if true, Linkerd is required for OpenFaaS
service_mesh=False
#round 26-29
counter=[{"yolo3":"20", "irrigation":"75", "crop-monitor":"50", "short":"30"},
         {"yolo3":"20", "irrigation":"75", "crop-monitor":"50", "short":"30"},
         {"yolo3":"20", "irrigation":"75", "crop-monitor":"50", "short":"30"},
         {"yolo3":"20", "irrigation":"75", "crop-monitor":"50", "short":"30"},
         {"yolo3":"20", "irrigation":"75", "crop-monitor":"50", "short":"30"}]

monitor_interval=10
scheduling_interval=5 * 60 
failure_handler_interval=10
battery_sim_update_interval=30
min_request_generation_interval = 1
sensor_admission_timeout = 3
max_request_timeout = 30 #max timeout set for apps, used for timers, failure_handler, etc.

intra_test_cooldown = 10 * 60 #between each epoch to wait for workers 
debug=False #master always True
max_cpu_capacity = 3600  #### #actual capacity is 4000m millicpu (or millicores), but 10% is deducted for safety net.

initial_battery_charge = 0 
min_battery_charge = 125 #mwh equals battery charge 10%
max_battery_charge = 1250 #mwh full battery, 9376 - 20% and scale in 1/6: 1250mwh
#home dir will be attached before this path by pi-agent
#pics folder must be already filled with pics
pics_folder = "/pics/"
file_storage_folder = "/storage/" 
#home dir comes before
log_path = "/logs/"

#renewable_input type" real OR poisson
renewable_type = "real"
#renewable input by poisson: set lambda for each nodes
renewable_poisson = [0,0,0,0,0]
#renewable inputs by real dataset: Melbourne CBD in 2018
optimal=True

renewable_real={
    "w1":[0,0,0,0,0,67,252,486,694,877,1000,1068,1080,997,784,753,559,330,132,0,0,0,0,0],
    "w2":[0,0,0,0,0,68,239,448,701,882,999,1063,1051,557,689,249,72,338,134,0,0,0,0,0],
    "w3":[0,0,0,0,0,38,161,236,458,596,572,480,476,624,894,528,276,85,114,0,0,0,0,0],
    "w4":[0,0,0,0,0,19,76,101,525,164,679,588,282,484,362,349,269,65,41,0,0,0,0,0],
    "w5":[0,0,0,0,0,15,60,153,346,655,686,265,180,156,189,76,93,60,37,0,0,0,0,0]
} #####
#new-4
#"w3":[0,0,0,0,0,38,161,236,458,596,572,480,476,624,894,528,276,85,114,0,0,0,0,0]
#w3
#"w3":[0,0,0,0,0,59,243,470,686,349,828,144,419,382,272,342,323,275,143,0,0,0,0,0]

#new-6
#"w2":[0,0,0,0,0,68,239,448,701,882,999,1063,1051,557,689,249,72,338,134,0,0,0,0,0]
#w2
#"w2":[0,0,0,0,0,65,250,484,393,875,998,1068,1080,1035,868,757,383,186,91,0,0,0,0,0]

#default=4 not sure if effective by updating on the fly
waitress_threads = 10
#NOTE:function name and queue name pattern is "node_name-function_name" like "w1-irrigation"
#Node_role: #MASTER #LOAD_GENERATOR #STANDALONE #MONITOR

#scheduling is based on requests, not limits

#three replicas
#app_resource_limit = {"yolo3":["650m", "750m"],
#                    "irrigation": ["400m", "400m"],
#                      "crop-monitor": ["300m", "300m"],
#                    "short": ["100m", "100m"]}

#two replica
app_resource_limit = {"yolo3":["650m", "750m"],
                    "irrigation": ["400m", "600m"],
                      "crop-monitor": ["300m", "450m"],
                    "short": ["100m", "150m"]}

#one replica
#app_resource_limit = {"yolo3":["650m", "1300m"],
#                    "irrigation": ["400m", "1200m"],
#                      "crop-monitor": ["300m", "900m"],
#                    "short": ["100m", "300m"]}


#function_timeouts = {'yolo3':{'read':'15s', 'write':'15s', 'exec':'15s', 'handlerWait':'15s'},
#                     'irrigation':{'read':'15s', 'write':'15s', 'exec':'15s', 'handlerWait':'15s'},
#                     'crop-monitor':{'read':'15s', 'write':'15s', 'exec':'15s', 'handlerWait':'15s'},
#                     'short':{'read':'15s', 'write':'15s', 'exec':'15s', 'handlerWait':'15s'}}
#function_timeout['yolo3']['read'], function_timeout['yolo3']['write'],
#function_timeout['yolo3']['exec'],function_timeout['yolo3']['handlerWait']

#USB METERs: Pair before tests
usb_meter={"master":"",
           "w1":"00:15:A3:00:68:C4",
           "w2":"00:15:A5:00:03:E7",
           "w3":"00:15:A3:00:52:2B",
           "w4":"00:15:A3:00:19:A7",
           "w5":"00:15:A3:00:5A:6F"}
#broken USB meter: "00:15:A5:00:02:ED"

#Plan by node names
plan={
"master":{
    "test_name": "",
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"MASTER",
    "gateway_IP":gateway_IP,
    "debug":True,
    "bluetooth_addr":usb_meter["master"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload_cfg
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8]func_info -->[min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile, version
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', apps["yolo3"], Workload_type, workload_cfg["w1"][0], 'master-yolo3', 'reference', 0, 0,
           [auto_scaling_min["yolo3"], auto_scaling_max["yolo3"], app_resource_limit["yolo3"][0], app_resource_limit["yolo3"][1], counter[0]["yolo3"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-yolo3" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', apps["irrigation"], Workload_type, workload_cfg["w1"][1], 'master-irrigation', 'value', 0, 0,
           [auto_scaling_min["irrigation"], auto_scaling_max["irrigation"], app_resource_limit["irrigation"][0], app_resource_limit["irrigation"][1], counter[0]["irrigation"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-irrigation" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', apps["crop-monitor"], Workload_type, workload_cfg["w1"][2], 'master-crop-monitor', 'value', 0, 0,
           [auto_scaling_min["crop-monitor"], auto_scaling_max["crop-monitor"], app_resource_limit["crop-monitor"][0], app_resource_limit["crop-monitor"][1], counter[0]["crop-monitor"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-crop-monitor" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['short', apps["short"], Workload_type, workload_cfg["w1"][3], 'master-short', 'value', 0, 0,
           [auto_scaling_min["short"], auto_scaling_max["short"], app_resource_limit["short"][0], app_resource_limit["short"][1], counter[0]["short"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-short" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]]],
    "peers":[],
    "usb_meter_involved":False,
    "battery_operated":False,
    #1:max,2:initial #3current SoC,
    #4: renewable type, 5:poisson seed&lambda,6:dataset, 7:interval, 8 dead charge , 9 turned on at
    "battery_cfg":[False, max_battery_charge,initial_battery_charge, initial_battery_charge,
        renewable_type,[seed,renewable_poisson[0]], renewable_real["w1"],
        battery_sim_update_interval, min_battery_charge, 0],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "max_request_timeout":max_request_timeout,
    "min_request_generation_interval": min_request_generation_interval,
    "sensor_admission_timeout": sensor_admission_timeout,
    "max_cpu_capacity": max_cpu_capacity,
    "log_path": log_path,
    "pics_folder":pics_folder,
    "file_storage_folder":file_storage_folder,
    "waitress_threads": waitress_threads,
    "boot_up_delay": boot_up_delay,
    #only master is True
    "raspbian_upgrade_error":True,},
#w1
"w1":
{
    "test_name": "",
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "gateway_IP":gateway_IP,
    "debug":True,
    "bluetooth_addr":usb_meter["w1"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload_cfg
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile,version
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', apps["yolo3"], Workload_type, workload_cfg["w1"][0], 'w1-yolo3', 'reference', 0, 0,
           [auto_scaling_min["yolo3"], auto_scaling_max["yolo3"], app_resource_limit["yolo3"][0], app_resource_limit["yolo3"][1], counter[0]["yolo3"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-yolo3" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', apps["irrigation"], Workload_type, workload_cfg["w1"][1], 'w1-irrigation', 'value', 0, 0,
           [auto_scaling_min["irrigation"], auto_scaling_max["irrigation"], app_resource_limit["irrigation"][0], app_resource_limit["irrigation"][1], counter[0]["irrigation"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-irrigation" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', apps["crop-monitor"], Workload_type, workload_cfg["w1"][2], 'w1-crop-monitor', 'value', 0, 0,
           [auto_scaling_min["crop-monitor"], auto_scaling_max["crop-monitor"], app_resource_limit["crop-monitor"][0], app_resource_limit["crop-monitor"][1], counter[0]["crop-monitor"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-crop-monitor" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['short', apps["short"], Workload_type, workload_cfg["w1"][3], 'w1-short', 'value', 0, 0,
           [auto_scaling_min["short"], auto_scaling_max["short"], app_resource_limit["short"][0], app_resource_limit["short"][1], counter[0]["short"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-short" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC,
    #4: renewable type, 5:poisson seed&lambda,6:dataset, 7:interval, 8 dead charge, 9 turned on at 
    "battery_cfg":[True, max_battery_charge,initial_battery_charge, initial_battery_charge,
        renewable_type,[seed,renewable_poisson[0]], renewable_real["w1"],
        battery_sim_update_interval, min_battery_charge, 0],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "max_request_timeout":max_request_timeout,
    "min_request_generation_interval": min_request_generation_interval,
    "sensor_admission_timeout": sensor_admission_timeout,
    "max_cpu_capacity": max_cpu_capacity,
    "log_path": log_path,
    "pics_folder":pics_folder,
    "file_storage_folder":file_storage_folder,
    "waitress_threads": waitress_threads,
    "boot_up_delay": boot_up_delay,
    #only master is True
    "raspbian_upgrade_error":False,},

#w2
"w2":{
    "test_name": "",
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "gateway_IP":gateway_IP,
    "debug":True,
    "bluetooth_addr":usb_meter["w2"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload_cfg
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile,version
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', apps["yolo3"], Workload_type, workload_cfg["w2"][0], 'w2-yolo3', 'reference', 0, 0,
           [auto_scaling_min["yolo3"], auto_scaling_max["yolo3"], app_resource_limit["yolo3"][0], app_resource_limit["yolo3"][1], counter[0]["yolo3"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-yolo3" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', apps["irrigation"], Workload_type, workload_cfg["w2"][1], 'w2-irrigation', 'value', 0, 0,
           [auto_scaling_min["irrigation"], auto_scaling_max["irrigation"], app_resource_limit["irrigation"][0], app_resource_limit["irrigation"][1], counter[0]["irrigation"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-irrigation" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', apps["crop-monitor"], Workload_type, workload_cfg["w2"][2], 'w2-crop-monitor', 'value', 0, 0,
           [auto_scaling_min["crop-monitor"], auto_scaling_max["crop-monitor"], app_resource_limit["crop-monitor"][0], app_resource_limit["crop-monitor"][1], counter[0]["crop-monitor"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-crop-monitor" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['short', apps["short"], Workload_type, workload_cfg["w2"][3], 'w2-short', 'value', 0, 0,
           [auto_scaling_min["short"], auto_scaling_max["short"], app_resource_limit["short"][0], app_resource_limit["short"][1], counter[0]["short"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-short" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC,
    #4: renewable type, 5:poisson seed&lambda,6:dataset, 7:interval, 8 dead charge , 9 turned on at
    "battery_cfg":[True, max_battery_charge,initial_battery_charge, initial_battery_charge,
        renewable_type,[seed,renewable_poisson[1]], renewable_real["w2"],
        battery_sim_update_interval, min_battery_charge, 0],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "max_request_timeout":max_request_timeout,
    "min_request_generation_interval": min_request_generation_interval,
    "sensor_admission_timeout": sensor_admission_timeout,
    "max_cpu_capacity": max_cpu_capacity,
    "log_path": log_path,
    "pics_folder":pics_folder,
    "file_storage_folder":file_storage_folder,
    "waitress_threads": waitress_threads,
    "boot_up_delay": boot_up_delay,
    #only master is True
    "raspbian_upgrade_error":False,},

#w3
"w3":{
    "test_name": "",
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "gateway_IP":gateway_IP,
    "debug":True,
    "bluetooth_addr":usb_meter["w3"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload_cfg
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile,version
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', apps["yolo3"], Workload_type, workload_cfg["w3"][0], 'w3-yolo3', 'reference', 0, 0,
           [auto_scaling_min["yolo3"], auto_scaling_max["yolo3"], app_resource_limit["yolo3"][0], app_resource_limit["yolo3"][1], counter[0]["yolo3"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-yolo3" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', apps["irrigation"], Workload_type, workload_cfg["w3"][1], 'w3-irrigation', 'value', 0, 0,
           [auto_scaling_min["irrigation"], auto_scaling_max["irrigation"], app_resource_limit["irrigation"][0], app_resource_limit["irrigation"][1], counter[0]["irrigation"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-irrigation" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', apps["crop-monitor"], Workload_type, workload_cfg["w3"][2], 'w3-crop-monitor', 'value', 0, 0,
           [auto_scaling_min["crop-monitor"], auto_scaling_max["crop-monitor"], app_resource_limit["crop-monitor"][0], app_resource_limit["crop-monitor"][1], counter[0]["crop-monitor"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-crop-monitor" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['short', apps["short"], Workload_type, workload_cfg["w3"][3], 'w3-short', 'value', 0, 0,
           [auto_scaling_min["short"], auto_scaling_max["short"], app_resource_limit["short"][0], app_resource_limit["short"][1], counter[0]["short"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-short" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC,
    #4: renewable type, 5:poisson seed&lambda,6:dataset, 7:interval, 8 dead charge , 9 turned on at
    "battery_cfg":[True, max_battery_charge,initial_battery_charge, initial_battery_charge,
        renewable_type,[seed,renewable_poisson[2]], renewable_real["w3"],
        battery_sim_update_interval, min_battery_charge, 0],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "max_request_timeout":max_request_timeout,
    "min_request_generation_interval": min_request_generation_interval,
    "sensor_admission_timeout": sensor_admission_timeout,
    "max_cpu_capacity": max_cpu_capacity,
    "log_path": log_path,
    "pics_folder":pics_folder,
    "file_storage_folder":file_storage_folder,
    "waitress_threads": waitress_threads,
    "boot_up_delay": boot_up_delay,
    #only master is True
    "raspbian_upgrade_error":False,},

#w4
"w4":{
    "test_name": "",
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "gateway_IP":gateway_IP,
    "debug":True,
    "bluetooth_addr":usb_meter["w4"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload_cfg
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile,version
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', apps["yolo3"], Workload_type, workload_cfg["w4"][0], 'w4-yolo3', 'reference', 0, 0,
           [auto_scaling_min["yolo3"], auto_scaling_max["yolo3"], app_resource_limit["yolo3"][0], app_resource_limit["yolo3"][1], counter[0]["yolo3"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-yolo3" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],        
        ['irrigation', apps["irrigation"], Workload_type, workload_cfg["w4"][1], 'w4-irrigation', 'value', 0, 0,
           [auto_scaling_min["irrigation"], auto_scaling_max["irrigation"], app_resource_limit["irrigation"][0], app_resource_limit["irrigation"][1], counter[0]["irrigation"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-irrigation" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', apps["crop-monitor"], Workload_type, workload_cfg["w4"][2], 'w4-crop-monitor', 'value', 0, 0,
           [auto_scaling_min["crop-monitor"], auto_scaling_max["crop-monitor"], app_resource_limit["crop-monitor"][0], app_resource_limit["crop-monitor"][1], counter[0]["crop-monitor"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-crop-monitor" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['short', apps["short"], Workload_type, workload_cfg["w4"][3], 'w4-short', 'value', 0, 0,
           [auto_scaling_min["short"], auto_scaling_max["short"], app_resource_limit["short"][0], app_resource_limit["short"][1], counter[0]["short"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-short" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC,
    #4: renewable type, 5:poisson seed&lambda,6:dataset, 7:interval, 8 dead charge, 9 turned on at 
    "battery_cfg":[True, max_battery_charge,initial_battery_charge, initial_battery_charge,
        renewable_type,[seed,renewable_poisson[3]], renewable_real["w4"],
        battery_sim_update_interval, min_battery_charge, 0],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "max_request_timeout":max_request_timeout,
    "min_request_generation_interval": min_request_generation_interval,
    "sensor_admission_timeout": sensor_admission_timeout,
    "max_cpu_capacity": max_cpu_capacity,
    "log_path": log_path,
    "pics_folder":pics_folder,
    "file_storage_folder":file_storage_folder,
    "waitress_threads": waitress_threads,
    "boot_up_delay": boot_up_delay,
    #only master is True
    "raspbian_upgrade_error":False,},

#w5
"w5":{
    "test_name": "",
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "gateway_IP":gateway_IP,
    "debug":True,
    "bluetooth_addr":usb_meter["w5"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload_cfg
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile,version
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', apps["yolo3"], Workload_type, workload_cfg["w5"][0], 'w5-yolo3', 'reference', 0, 0,
           [auto_scaling_min["yolo3"], auto_scaling_max["yolo3"], app_resource_limit["yolo3"][0], app_resource_limit["yolo3"][1], counter[0]["yolo3"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-yolo3" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', apps["irrigation"], Workload_type, workload_cfg["w5"][1], 'w5-irrigation', 'value', 0, 0,
           [auto_scaling_min["irrigation"], auto_scaling_max["irrigation"], app_resource_limit["irrigation"][0], app_resource_limit["irrigation"][1], counter[0]["irrigation"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-irrigation" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', apps["crop-monitor"], Workload_type, workload_cfg["w5"][2], 'w5-crop-monitor', 'value', 0, 0,
           [auto_scaling_min["crop-monitor"], auto_scaling_max["crop-monitor"], app_resource_limit["crop-monitor"][0], app_resource_limit["crop-monitor"][1], counter[0]["crop-monitor"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-crop-monitor" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['short', apps["short"], Workload_type, workload_cfg["w5"][3], 'w5-short', 'value', 0, 0,
           [auto_scaling_min["short"], auto_scaling_max["short"], app_resource_limit["short"][0], app_resource_limit["short"][1], counter[0]["short"], redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-short" if multiple_queue else ""), "",0],
             ["unknown", "unknown","unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC,
    #4: renewable type, 5:poisson seed&lambda,6:dataset, 7:interval, 8 dead charge , 9 turned on at
    "battery_cfg":[True, max_battery_charge,initial_battery_charge, initial_battery_charge,
        renewable_type,[seed,renewable_poisson[4]], renewable_real["w5"],
        battery_sim_update_interval, min_battery_charge, 0],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "max_request_timeout":max_request_timeout,
    "min_request_generation_interval": min_request_generation_interval,
    "sensor_admission_timeout": sensor_admission_timeout,
    "max_cpu_capacity": max_cpu_capacity,
    "log_path": log_path,
    "pics_folder":pics_folder,
    "file_storage_folder":file_storage_folder,
    "waitress_threads": waitress_threads,
    "boot_up_delay": boot_up_delay,
    #only master is True
    "raspbian_upgrade_error":False}
}

#overall to make better sense:
#increase load impact by COUNTER
#Increase load impact than just battery by 2 replicas or better by hpa scaling

#To improve Greedy:
#Tune zone thresholds,
#Tune stickiness
#one line in sticky algorithm can be removed to apply more stickiness
#cover any zone, instead of only same zone to keep sticky
#boot_up_delay=0 to avoid processing more sensors than other algorithms that sleep for an extra 90s

#To weaken others do:
#all: as dead functions are unable to be scheduled, they should be excluded from scheduling
    #Or, scheduled locally, and when node is up, apply a delay in starting sens_sensor for the node
#random: schedule dead functions locally (to avoid warm scheduler which is our contribution)
#Bin-packing: schedule dead functions locally (to avoid warm scheduler which is our contribution)
