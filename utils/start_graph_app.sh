#! /bin/bash#! /bin/bash

docker run --name graph_set -d  -p 8080:8080 systemautoscaler/sebs-dynamic_html:0.0.1 uwsgi --http 0.0.0.0:8080 --master -p 15 -w web_server_graph_mst:app
docker run --name graph_quota -d  -p 8081:8080 systemautoscaler/sebs-dynamic_html:0.0.1 uwsgi --http 0.0.0.0:8080 --master -p 1 -w web_server_graph_mst:app