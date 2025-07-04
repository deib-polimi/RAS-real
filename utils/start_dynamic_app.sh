#! /bin/bash

 docker run --name dynamic_set -d  -p 8080:8080 systemautoscaler/sebs-dynamic_html:0.0.1 uwsgi --http 0.0.0.0:8080 --master -p 15 -w web_server_dynamic_html:app
 docker run --name dynamic_quota -d  -p 8081:8080 systemautoscaler/sebs-dynamic_html:0.0.1 uwsgi --http 0.0.0.0:8080 --master -p 1 -w web_server_dynamic_html:app
