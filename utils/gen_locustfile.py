import os

directory = "./locustfiles"

replace_content = ("TweetGen", "WikiGen")
replace_name = "tweet", "wiki"


for filename in os.listdir(directory):
  if filename.endswith(".py") and replace_name[0] in filename:
    with open(os.path.join(directory, filename), "r") as f:
      contents = f.read()
    contents = contents.replace(*replace_content)
    new_filename = filename.replace(*replace_name)
    with open(os.path.join(directory, new_filename), "w") as f:
      f.write(contents)
