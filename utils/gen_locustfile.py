import os
import re

directory = "./locustfiles"

replace_content = [
  (r'"controller"\s*:\s*\{[^}]*}[^}]*}', '''"controller" : {
        "class" : "CTControllerScaleX",
        "params" : {
            "period" : 5, 
            "init_cores" : 2, 
            "min_cores" : 0.5,
            "max_cores" : 16,
            "BC" : 0.15, 
            "DC" :  0.25, 
            "st" : 0.7
        }
    }''')
  ]

replace_name = []

filematches = ["ct", "aws", "graph"]



for filename in os.listdir(directory):
  if filename.endswith(".py") and all(match in filename for match in filematches):
    with open(os.path.join(directory, filename), "r") as f:
      contents = f.read()
  
    for c in replace_content:
      contents = re.sub(*c, contents, flags=re.DOTALL)
    new_filename = filename
    for n in replace_name:
      new_filename = filename.replace(*n)
    with open(os.path.join(directory, new_filename), "w") as f:
      f.write(contents)
    
