import os
import re

directory = "./locustfiles"

replace_content = [
  (r'"controller"\s*:\s*\{[^}]*}[^}]*}', '''"controller" : {
        "class" : "OPTCTRL",
        "params" : {
            "period" : 1, 
            "init_cores" : 1, 
            "min_cores" : 0.5,
            "max_cores" : 16,
            "st" : 0.7
        }
    }''')
  ]

filematches = ["ct", "aws"]
replace_name = ("ct", "qn")


for filename in os.listdir(directory):
  if filename.endswith(".py") and all(match in filename for match in filematches):
    with open(os.path.join(directory, filename), "r") as f:
      contents = f.read()
  
    for c in replace_content:
      contents = re.sub(*c, contents, flags=re.DOTALL)
    
    new_filename = filename.replace(*replace_name)
    with open(os.path.join(directory, new_filename), "w") as f:
      f.write(contents)
    
