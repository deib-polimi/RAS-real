### RAS - Real Experiment

- Run function
```docker run -p 8080:8080 systemautoscaler/sebs-dynamic_html:0.0.1 uwsgi --http 0.0.0.0:8080 --master -p <CORES> -w web_server_dynamic_html:app``
- Get container id with ```docker ps``` and add it to the experiment config file (in experiments/config)
- Run locust ```locust``` and run the experiment through [locust-ui](http://localhost:8089)
- Check cpu-quotas via ```docker inspect --format='{{json .HostConfig.CpuQuota}} {{json .HostConfig.CpuPeriod}}' <CONTAINER_ID>```