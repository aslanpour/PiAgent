#!/bin/bash
for ip in $(seq 1 1 5)
do
  scp ~/pi-agent-v10-scheduler.py pi@10.0.0.9$ip:.
done
