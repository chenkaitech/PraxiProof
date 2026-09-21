#!/usr/bin/env bash
# Real end-to-end check: upload a compliant recording through the deployed pipeline with second_look enabled.
API=http://127.0.0.1:8090/api
id=$(curl -s -F manual_id=MAN-004 -F video=@$HOME/datasets/sop-server-fan/edited/Install_12_compliant.mp4 $API/pipelines | python3 -c "import sys,json;print(json.load(sys.stdin)[\"id\"])")
echo "pipeline $id"
while true; do s=$(curl -s $API/pipelines/$id | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[\"status\"], d.get(\"result\"), d.get(\"run_id\"))"); echo "$s"; case $s in done*|failed*) break;; esac; sleep 20; done
