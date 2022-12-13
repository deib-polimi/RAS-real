### RAS - Real Experiment

- Run function
```docker run --rm -it -p 80:80 yeasy/simple-web:latest```
- Get container id with ```docker ps``` and add it to the experiment config file (in experiments/config)
- Run locust ```locust``` and run the experiment through [locust-ui](http://localhost:8089)
- Check cpu-quotas via ```docker inspect --format='{{json .HostConfig.CpuQuota}} {{json .HostConfig.CpuPeriod}}' <CONTAINER_ID>```