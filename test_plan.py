#first run pi_Service on PEERs

test_name="test"
#[0] position [1] node name [2] node ip
nodes=[["COORDINATOR","master","10.0.0.90"],
       ["PEER", "w1","10.0.0.91"],
       ["-", "w2","10.0.0.92"],
       ["-", "w3","10.0.0.93"],
       ["-", "w4","10.0.0.94"],
       ["-", "w5","10.0.0.95"]]

test_duration=5*60

#Node_role: #MASTER #LOAD_GENERATOR #STANDALONE #MONITOR

#USB METERs
usb_meter={"master":"00:15:A3:00:52:2B",
           "w1":"00:15:A3:00:68:C4",
           "w2":"00:15:A5:00:03:E7",
           "w3":"00:15:A5:00:02:ED",
           "w4":"00:15:A3:00:19:A7",
           "w5":"00:15:A3:00:5A:6F"}
#copy chart-latest and chart-profile folders to home directory
profile_chart = ["chart-profile", "~/chart-profile"]
function_chart = ["chart-latest", "~/chart-latest"]
profile_creation_roll_out = 15
function_creation_roll_out = 90
redis_server_ip= "10.43.242.161" #assume default port is selected as 3679
#NOTE if True, queues must be already created! and follow the name pattern as queue-worker-functionName
multiple_queue=True
service_mesh==False
COUNTER=str(20)
monitor_interval=10
scheduling_interval=60
failure_handler_interval=10
battery_sim_update_interval=10
debug=True #master always True
cpu_capacity = 3600 #actual capacity is 4000m millicpu (or millicores), but 10% is deducted for safety net.
#NOTE:function name and queue name pattern is "node_name-function_name" like "w1-irrigation"

#Plan by node names
plan={
"master":{
    "test_name": test_name,
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"MASTER",
    "debug":True,
    "bluetooth_addr":usb_meter["master"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload: [[0]iteration
                    #[1]interval/exponential lambda(10=avg 8s)
                    #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', False, 'static', [1, 1, 1, 5], 'master-yolo3', 'reference', 0, 0,
           ["1", "1", "750", "1500", COUNTER, redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-master-yolo3" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', False, 'static', [3, 1, 1, 5], 'master-crop-monitor', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-master-crop-monitor" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', False, 'static', [30, 1, 20, 5], 'master-irrigation', 'value', 0, 0,
           ["1", "3", "125", "250", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-master-irrigation" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]],
        ['short', False, 'static', [4, 2, 1, 5], 'master-short', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-master-short" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC, 4:renwable seed&lambda, 5:interval
    "battery_cfg":[True, 850,850, 850, [5,5], battery_sim_update_interval],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "request_timeout":30,
    "cpu_capacity": cpu_capacity,
    #only master is True
    "raspbian_upgrade_error":True,},
#w1
"w1":
{
    "test_name": test_name,
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "debug":True,
    "bluetooth_addr":usb_meter["w1"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload: [[0]iteration
                    #[1]interval/exponential lambda(10=avg 8s)
                    #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', True, 'static', [500, 30, 1, 5], 'w1-yolo3', 'reference', 0, 0,
           ["1", "1", "750", "1500", COUNTER, redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-w1-yolo3" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', True, 'static', [1500, 10, 1, 5], 'w1-crop-monitor', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w1-crop-monitor" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', True, 'static', [1000, 20, 1, 5], 'w1-irrigation', 'value', 0, 0,
           ["1", "3", "125", "250", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w1-irrigation" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]],
        ['short', False, 'static', [4, 2, 1, 5], 'w1-short', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w1-short" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC, 4:renwable seed&lambda, 5:interval
    "battery_cfg":[True, 850,850, 850, [5,5], battery_sim_update_interval],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "request_timeout":30,
    "cpu_capacity": cpu_capacity,
    #only master is True
    "raspbian_upgrade_error":False,},

#w2
"w2":{
    "test_name": test_name,
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "debug":True,
    "bluetooth_addr":usb_meter["w2"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload: [[0]iteration
                    #[1]interval/exponential lambda(10=avg 8s)
                    #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', True, 'static', [1, 1, 1, 5], 'w2-yolo3', 'reference', 0, 0,
           ["1", "1", "750", "1500", COUNTER, redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-w2-yolo3" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', True, 'static', [3, 1, 1, 5], 'w2-crop-monitor', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w2-crop-monitor" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', True, 'static', [30, 1, 20, 5], 'w2-irrigation', 'value', 0, 0,
           ["1", "3", "125", "250", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w2-irrigation" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]],
        ['short', False, 'static', [4, 2, 1, 5], 'w2-short', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w2-short" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC, 4:renwable seed&lambda, 5:interval
    "battery_cfg":[True, 850,850, 850, [5,5], battery_sim_update_interval],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "request_timeout":30,
    "cpu_capacity": cpu_capacity,
    #only master is True
    "raspbian_upgrade_error":False,},

#w3
"w3":{
    "test_name": test_name,
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "debug":True,
    "bluetooth_addr":usb_meter["w3"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload: [[0]iteration
                    #[1]interval/exponential lambda(10=avg 8s)
                    #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', True, 'static', [1, 1, 1, 5], 'w3-yolo3', 'reference', 0, 0,
           ["1", "1", "750", "1500", COUNTER, redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-w3-yolo3" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', True, 'static', [3, 1, 1, 5], 'w3-crop-monitor', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w3-crop-monitor" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', True, 'static', [30, 1, 20, 5], 'w3-irrigation', 'value', 0, 0,
           ["1", "3", "125", "250", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w3-irrigation" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]],
        ['short', False, 'static', [4, 2, 1, 5], 'w3-short', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w3-short" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC, 4:renwable seed&lambda, 5:interval
    "battery_cfg":[True, 850,850, 850, [5,5], battery_sim_update_interval],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "request_timeout":30,
    "cpu_capacity": cpu_capacity,
    #only master is True
    "raspbian_upgrade_error":False,},

#w4
"w4":{
    "test_name": test_name,
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "debug":True,
    "bluetooth_addr":usb_meter["w4"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload: [[0]iteration
                    #[1]interval/exponential lambda(10=avg 8s)
                    #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', True, 'static', [1, 1, 1, 5], 'w4-yolo3', 'reference', 0, 0,
           ["1", "1", "750", "1500", COUNTER, redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-w4-yolo3" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', True, 'static', [3, 1, 1, 5], 'w4-crop-monitor', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w4-crop-monitor" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', True, 'static', [30, 1, 20, 5], 'w4-irrigation', 'value', 0, 0,
           ["1", "3", "125", "250", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w4-irrigation" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]],
        ['short', False, 'static', [4, 2, 1, 5], 'w4-short', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w4-short" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC, 4:renwable seed&lambda, 5:interval
    "battery_cfg":[True, 850,850, 850, [5,5], battery_sim_update_interval],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "request_timeout":30,
    "cpu_capacity": cpu_capacity,
    #only master is True
    "raspbian_upgrade_error":False,},

#w5
"w5":{
    "test_name": test_name,
    #MONITOR #LOAD_GENERATOR #STANDALONE #SCHEDULER
    "node_role":"LOAD_GENERATOR",
    "debug":True,
    "bluetooth_addr":usb_meter["w5"],
    #[0]app name
    #[1] run/not
    #[2] w type: "static" or "poisson" or "exponential" or "exponential-poisson"
    #[3] workload: [[0]iteration
                    #[1]interval/exponential lambda(10=avg 8s)
                    #[2]concurrently/poisson lambda (15=avg 17reqs ) [3] random seed (def=5)]
    #[4] func_name [5] func_data [6] sent [7] recv
    #[8][min,max,requests,limits,env.counter, env.redisServerIp, env,redisServerPort,
    #read,write,exec,handlerWaitDuration,linkerd,queue,profile
    #[9]nodeAffinity_required_filter1,nodeAffinity_required_filter2,nodeAffinity_required_filter3,
        # nodeAffinity_preferred_sort1,podAntiAffinity_preferred_functionName,
        # podAntiAffinity_required_functionName
    "apps":[
        ['yolo3', True, 'static', [1, 1, 1, 5], 'w5-yolo3', 'reference', 0, 0,
           ["1", "1", "750", "1500", COUNTER, redis_server_ip, "3679","15s","15s","15s","15s",
            ("enabled" if service_mesh else "disabled") , ("queue-worker-w5-yolo3" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['crop-monitor', True, 'static', [3, 1, 1, 5], 'w5-crop-monitor', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w5-crop-monitor" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown"]],
        ['irrigation', True, 'static', [30, 1, 20, 5], 'w5-irrigation', 'value', 0, 0,
           ["1", "3", "125", "250", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w5-irrigation" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]],
        ['short', False, 'static', [4, 2, 1, 5], 'w5-short', 'value', 0, 0,
           ["1", "3", "50", "100", COUNTER, redis_server_ip, "3679","10s","10s","10s","10s",
            ("enabled" if service_mesh else "disabled"), ("queue-worker-w5-short" if multiple_queue else ""), "",],
             ["unknown", "unknown", "unknown", "unknown", "unknown", "unknown", "unknown",]]],
    "peers":[],
    "usb_meter_involved":True,
    "battery_operated":False,
    #1:max,2:initial #3current SoC, 4:renwable seed&lambda, 5:interval
    "battery_cfg":[True, 850,850, 850, [5,5], battery_sim_update_interval],
    "time_based_termination":[True, test_duration],
    "monitor_interval":monitor_interval,
    "scheduling_interval":scheduling_interval,
    "failure_handler_interval":failure_handler_interval,
    "request_timeout":30,
    "cpu_capacity": cpu_capacity,
    #only master is True
    "raspbian_upgrade_error":False}
}

#validation
