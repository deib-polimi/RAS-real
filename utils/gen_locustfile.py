import os
import re

directory = "./locustfiles"

replace_content = [
  ("dynamic_set", "graph_set"), 
  ("dynamic_quota", "graph_quota"),
  ("/function/dynamic_html", "/function/graph_mst"),
  (r'"data"\s*:\s*{.*?}', '"data" : { "size" : 25000 }')
  ]

replace_name = "aws", "aws-graph"


for filename in os.listdir(directory):
  if filename.endswith(".py") and replace_name[0] in filename:
    with open(os.path.join(directory, filename), "r") as f:
      contents = f.read()
    for c in replace_content:
      contents = re.sub(*c, contents)
    
    new_filename = filename.replace(*replace_name)
    with open(os.path.join(directory, new_filename), "w") as f:
      f.write(contents)
